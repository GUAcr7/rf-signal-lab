"""Offline periodic TX fixtures; no device access or RF power assumptions.

The project's vendor TX HDL consumes ``dma_data[15:4]``. Therefore logical
signed 12-bit DAC samples are stored as signed 16-bit words shifted left by
four bits. This module does not imply a transmit port power in dBm.
"""

from dataclasses import dataclass
from numbers import Real
from typing import Any

import numpy as np
from numpy.typing import NDArray

from rfsig.bpsk import map_bpsk
from rfsig.modulation import map_qam16, map_qpsk
from rfsig.pulse_shaping import rrc_taps


MAX_SAMPLE_COUNT = 1_048_576
DAC_BITS = 12
STORAGE_SHIFT = 4


@dataclass(frozen=True)
class TxWaveform:
    """One complete cyclic buffer and the information needed to reproduce it.

    ``iq`` contains integer-valued complex128 logical DAC components.
    ``storage_iq`` contains the same components multiplied by 16. Neither is
    a complex-valued integer NumPy dtype (NumPy has no such standard dtype).
    ``reference`` is JSON-serializable; bits, symbols and taps are separate
    arrays so callers may save them without losing numerical precision.
    """

    iq: NDArray[np.complex128]
    storage_iq: NDArray[np.complex128]
    bits: NDArray[np.uint8]
    symbols: NDArray[np.complex128]
    taps: NDArray[np.float64]
    reference: dict[str, Any]


def _integer(value: int, name: str, minimum: int, maximum: int) -> int:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, (int, np.integer)):
        raise ValueError(f"{name} must be an integer")
    result = int(value)
    if not minimum <= result <= maximum:
        raise ValueError(f"{name} must be in [{minimum}, {maximum}]")
    return result


def _real(value: float, name: str) -> float:
    if isinstance(value, (bool, np.bool_)) or not isinstance(value, Real):
        raise ValueError(f"{name} must be a finite real number")
    try:
        result = float(value)
    except (OverflowError, ValueError) as exc:
        raise ValueError(f"{name} must be a finite real number") from exc
    if not np.isfinite(result):
        raise ValueError(f"{name} must be a finite real number")
    return result


def circular_shape_symbols(symbols, taps, samples_per_symbol: int) -> NDArray[np.complex128]:
    """Centered periodic FIR convolution of a repeated symbol sequence.

    For odd length L and delay D=(L-1)/2, the result is
    y[n] = sum(h[k] * u[(n+D-k) mod N]), where u has a symbol every sps
    samples and N=symbol_count*sps. Taps longer than a period are folded
    correctly. Repeating this output has no artificial zero-filled FIR tail.
    """
    sps = _integer(samples_per_symbol, "samples_per_symbol", 1, MAX_SAMPLE_COUNT)
    values = np.asarray(symbols, dtype=np.complex128)
    coeffs = np.asarray(taps, dtype=np.float64)
    if values.ndim != 1 or not values.size or not np.isfinite(values).all():
        raise ValueError("symbols must be a nonempty finite one-dimensional array")
    count = int(values.size) * sps
    if count > MAX_SAMPLE_COUNT:
        raise ValueError("sample_count exceeds the offline buffer limit")
    if (coeffs.ndim != 1 or not coeffs.size or coeffs.size % 2 != 1
            or coeffs.size > MAX_SAMPLE_COUNT or not np.isfinite(coeffs).all()):
        raise ValueError("taps must be finite, odd-length and within the buffer limit")
    impulses = np.zeros(count, dtype=np.complex128)
    impulses[::sps] = values
    kernel = np.zeros(count, dtype=np.float64)
    delay = (coeffs.size - 1) // 2
    np.add.at(kernel, (np.arange(coeffs.size) - delay) % count, coeffs)
    with np.errstate(over="ignore", invalid="ignore"):
        shaped = np.fft.ifft(np.fft.fft(impulses) * np.fft.fft(kernel))
    if not np.isfinite(shaped).all():
        raise ValueError("periodic convolution overflowed")
    return shaped


def pack_tx_iq_le16(iq) -> bytes:
    """Pack logical signed-12 I/Q as I0,Q0,I1,Q1 little-endian int16 words.

    Logical range is [-2048, 2047]. The signed word is logical_code*16, so
    its low four bits are zero. Fractional, nonfinite and out-of-range input
    is rejected rather than clipped or wrapped.
    """
    values = np.asarray(iq, dtype=np.complex128)
    if values.ndim != 1 or not values.size or values.size > MAX_SAMPLE_COUNT:
        raise ValueError("iq must be nonempty, one-dimensional and within the buffer limit")
    if not np.isfinite(values).all():
        raise ValueError("iq must be finite")
    for component in (values.real, values.imag):
        if (np.any(component < -2048) or np.any(component > 2047)
                or np.any(component != np.rint(component))):
            raise ValueError("iq components must be integer signed-12 DAC codes")
    packed = np.empty((values.size, 2), dtype="<i2")
    packed[:, 0] = values.real.astype(np.int32) * (1 << STORAGE_SHIFT)
    packed[:, 1] = values.imag.astype(np.int32) * (1 << STORAGE_SHIFT)
    return packed.tobytes(order="C")


def make_tx_waveform(
    modulation: str,
    *,
    sample_rate_hz: int,
    samples_per_symbol: int = 8,
    symbol_count: int = 1024,
    seed: int = 20261016,
    offset_hz: float = 0,
    digital_peak_counts: int = 512,
    rolloff: float = 0.35,
    span_symbols: int = 10,
) -> TxWaveform:
    """Build a bin-coherent tone or cyclic RRC BPSK/QPSK/16QAM buffer.

    N=symbol_count*samples_per_symbol for all modes. The carrier must have
    an integer number of cycles per N-sample period. At least one FFT bin
    separates the theoretical occupied support from either Nyquist edge.
    The finite RRC has leakage beyond its infinite-filter theoretical
    support; that support is not a measured 99% occupied bandwidth.

    ``digital_peak_counts`` is the peak absolute *individual I or Q DAC
    component*, 1..2047, not complex magnitude, ADC counts or RF dBm.
    Rounding is NumPy nearest/ties-to-even and no component is clipped.
    """
    if not isinstance(modulation, str) or modulation.upper() not in {"TONE", "BPSK", "QPSK", "16QAM"}:
        raise ValueError("modulation must be tone, BPSK, QPSK or 16QAM")
    mode = modulation.upper()
    fs = _integer(sample_rate_hz, "sample_rate_hz", 1, 2**53 - 1)
    sps = _integer(samples_per_symbol, "samples_per_symbol", 1, MAX_SAMPLE_COUNT)
    symbols_n = _integer(symbol_count, "symbol_count", 1, MAX_SAMPLE_COUNT)
    count = sps * symbols_n
    if not 2 <= count <= MAX_SAMPLE_COUNT:
        raise ValueError("sample_count must be in [2, 1048576]")
    random_seed = _integer(seed, "seed", 0, 2**32 - 1)
    peak = _integer(digital_peak_counts, "digital_peak_counts", 1, 2047)
    offset = _real(offset_hz, "offset_hz")
    beta = _real(rolloff, "rolloff")
    if not 0 <= beta <= 1:
        raise ValueError("rolloff must be in [0, 1]")
    span = _integer(span_symbols, "span_symbols", 1, MAX_SAMPLE_COUNT)
    if span * sps + 1 > MAX_SAMPLE_COUNT:
        raise ValueError("RRC tap count exceeds the offline buffer limit")
    # Check bounds before multiplying by count, avoiding huge-float overflow.
    if abs(offset) >= fs / 2:
        raise ValueError("offset_hz must be strictly inside the Nyquist interval")
    cycles = offset / fs * count
    nearest_cycles = int(round(cycles))
    if abs(cycles - nearest_cycles) > 1e-9:
        raise ValueError("offset_hz must complete an integer number of cycles per buffer")
    coherent_offset = nearest_cycles * fs / count
    bin_hz = fs / count
    half_support = 0.0 if mode == "TONE" else (1 + beta) * fs / (2 * sps)
    if abs(coherent_offset) + half_support > fs / 2 - bin_hz + fs * 1e-14:
        raise ValueError("theoretical support needs at least one FFT bin of Nyquist margin")

    if mode == "TONE":
        bits = np.empty(0, dtype=np.uint8)
        symbols = np.empty(0, dtype=np.complex128)
        taps = np.empty(0, dtype=np.float64)
        baseband = np.ones(count, dtype=np.complex128)
        bits_per_symbol = 0
    else:
        bits_per_symbol = {"BPSK": 1, "QPSK": 2, "16QAM": 4}[mode]
        rng = np.random.default_rng(random_seed)
        bits = rng.integers(0, 2, symbols_n * bits_per_symbol, dtype=np.uint8)
        mapper = {"BPSK": map_bpsk, "QPSK": map_qpsk, "16QAM": map_qam16}[mode]
        symbols = mapper(bits).astype(np.complex128)
        taps = rrc_taps(beta, span, sps)
        baseband = circular_shape_symbols(symbols, taps, sps)
    # Integer bin index makes the conceptual period exactly coherent. Floating
    # roundoff is small; the quantizer produces integer-valued logical codes.
    phase = 2 * np.pi * nearest_cycles * np.arange(count, dtype=np.float64) / count
    shifted = baseband * np.exp(1j * phase)
    float_component_peak = float(max(np.max(np.abs(shifted.real)), np.max(np.abs(shifted.imag))))
    if not np.isfinite(float_component_peak) or float_component_peak <= 0:
        raise ValueError("waveform must have finite positive peak")
    scale = peak / float_component_peak
    logical = np.rint(shifted.real * scale) + 1j * np.rint(shifted.imag * scale)
    # Packing performs the same strict bounds/integer validation used at the
    # byte boundary; do not silently cast overflowing arrays to int16.
    pack_tx_iq_le16(logical)
    reference: dict[str, Any] = {
        "schema": "rfsig.cyclic-tx.v1",
        "modulation": "tone" if mode == "TONE" else mode,
        "sample_rate_hz": fs,
        "sample_count": count,
        "period_seconds": count / fs,
        "samples_per_symbol": sps if mode != "TONE" else None,
        "symbol_count": symbols_n if mode != "TONE" else None,
        "symbol_rate_hz": fs / sps if mode != "TONE" else None,
        "bits_per_symbol": bits_per_symbol,
        "seed": random_seed,
        "offset_hz": coherent_offset,
        "carrier_cycles_per_buffer": nearest_cycles,
        "frequency_bin_hz": bin_hz,
        "nyquist_margin_hz": fs / 2 - abs(coherent_offset) - half_support,
        "rrc_rolloff": beta if mode != "TONE" else None,
        "rrc_span_symbols": span if mode != "TONE" else None,
        "rrc_tap_count": int(taps.size),
        "rrc_convolution": "centered periodic circular" if mode != "TONE" else None,
        "theoretical_rrc_support_hz": [coherent_offset - half_support, coherent_offset + half_support] if mode != "TONE" else None,
        "support_definition": "infinite-RRC theoretical support; finite-tap leakage exists; not measured 99% OBW" if mode != "TONE" else "one coherent tone bin before integer quantization",
        "digital_peak_counts": peak,
        "digital_peak_definition": "maximum absolute individual I or Q logical DAC component",
        "logical_dac_bits": DAC_BITS,
        "storage_bits": 16,
        "storage_left_shift": STORAGE_SHIFT,
        "storage_peak_counts": peak * (1 << STORAGE_SHIFT),
        "packing": "little-endian signed int16, interleaved I0,Q0,I1,Q1; low 4 bits zero",
        "quantizer": "nearest ties-to-even, no clipping",
        "logical_counts_per_float_unit": scale,
        "logical_mean_i2_plus_q2": float(np.mean(logical.real**2 + logical.imag**2)),
        "rf_power_dbm": None,
        "rf_power_note": "digital DAC codes do not specify RF output power; board-specific calibration is required",
    }
    return TxWaveform(logical, logical * (1 << STORAGE_SHIFT), bits, symbols, taps, reference)
