"""Known-source snapshot metrology. Deliberately separate from blind inference."""
from dataclasses import dataclass
import numpy as np

from rfsig.capture_continuity import align_periodic_reference,ReferenceAlignment
from rfsig.carrier_tracking import constellation,reference_evm_db
from rfsig.symbol_recovery import recover_snapshot,RecoveredSymbols
from rfsig.tx_waveforms import TxWaveform


@dataclass(frozen=True)
class ReferenceMeasurement:
    alignment: ReferenceAlignment
    recovered: RecoveredSymbols
    expected_symbols: np.ndarray
    evm_db: float
    checked_symbols: int
    symbol_errors: int


def measure_known_snapshot(iq,transmitted: TxWaveform,carrier_hint_hz,*,dma_buffer_samples):
    """Compare RX with transmitted payload symbols at aligned source times.

    The stored TX waveform includes its nominal baseband offset. Remove THAT
    offset when building the source reference; remove the RECEIVED carrier from
    RX. They differ because the two radios have independent LOs. Filtering both
    raw passband waveforms by the received carrier is not a valid reference.

    One known DMA snapshot only. Carrier and source position use the full known
    sequence, while decision gain uses the first half of the recovered symbols.
    The second-half check is not an independent AI or BER test dataset.
    """
    x=np.asarray(iq,dtype=np.complex128)
    if isinstance(dma_buffer_samples,bool) or not isinstance(dma_buffer_samples,(int,np.integer)) or dma_buffer_samples<=0:
        raise ValueError("recorded DMA buffer size is required")
    if x.ndim!=1 or len(x)>dma_buffer_samples:
        raise ValueError("known-source metrology must not cross a recorded DMA boundary")
    meta=transmitted.reference
    if not transmitted.symbols.size:
        raise ValueError("reference must contain modulated payload symbols")
    fs=meta["sample_rate_hz"]
    sps=meta["samples_per_symbol"]
    ref=transmitted.iq*np.exp(-2j*np.pi*meta["offset_hz"]*np.arange(len(transmitted.iq))/fs)
    fit=align_periodic_reference(x,ref,fs,carrier_hint_hz)
    if fit.correlation<.99:
        raise ValueError("capture does not match the supplied source at usable confidence")
    recovered=recover_snapshot(x,fs,fit.frequency_hz,meta["modulation"],sps,
                                meta["rrc_rolloff"],meta["rrc_span_symbols"])
    indices=np.rint((fit.source_start+recovered.sample_indices)/sps).astype(int)%len(transmitted.symbols)
    expected=transmitted.symbols[indices]
    symbols=recovered.symbols
    split=len(symbols)//2
    gain=np.vdot(expected[:split],symbols[:split])/np.vdot(expected[:split],expected[:split])
    if abs(gain)==0: raise ValueError("no usable gain fit")
    checked=symbols[split:]/gain
    table=constellation(meta["modulation"])
    decisions=table[np.argmin(abs(checked[:,None]-table[None,:])**2,axis=1)]
    errors=int(np.count_nonzero(abs(decisions-expected[split:])>1e-9))
    return ReferenceMeasurement(fit,recovered,expected,reference_evm_db(symbols,expected),len(checked),errors)
