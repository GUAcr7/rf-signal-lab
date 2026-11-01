import numpy as np
import pytest

from rfsig.carrier_tracking import (
    CONSTELLATIONS,
    constellation,
    evm_db,
    reference_evm_db,
    track_carrier,
)


def _symbols(name, count, seed, amplitude=1.0):
    rng = np.random.default_rng(seed)
    table = constellation(name)
    return amplitude * table[rng.integers(0, table.size, count)]


def test_constellations_have_unit_average_power():
    for name, table in CONSTELLATIONS.items():
        power = float(np.mean(np.abs(table) ** 2))
        assert power == pytest.approx(1.0, rel=1e-12), name


def test_constellation_names_are_case_and_alias_tolerant():
    assert constellation("BPSK") is constellation("bpsk")
    assert constellation("16QAM") is constellation("qam16")
    assert constellation("qam-16") is constellation("qam16")
    with pytest.raises(ValueError):
        constellation("16apsk")


def test_evm_of_a_clean_constellation_is_very_low():
    symbols = _symbols("qpsk", 512, seed=1)
    assert evm_db(symbols, constellation("qpsk")) < -100


def test_evm_is_gain_invariant():
    table = constellation("qam16")
    symbols = _symbols("qam16", 512, seed=2, amplitude=3.7)
    assert evm_db(symbols, table) == pytest.approx(evm_db(symbols / 3.7, table), abs=1e-9)


def test_evm_grows_with_noise():
    table = constellation("qpsk")
    clean = _symbols("qpsk", 4096, seed=3)
    rng = np.random.default_rng(4)
    noisy = clean + 0.1 * (rng.standard_normal(clean.size) + 1j * rng.standard_normal(clean.size))
    assert evm_db(clean, table) < evm_db(noisy, table)


def test_tracking_converges_onto_a_static_phase_offset():
    # EVM deliberately cannot see this: its gain fit is complex, so a constant
    # rotation scores as a perfect constellation. The loop phase is the right
    # observable for a static offset.
    table = constellation("bpsk")
    clean = _symbols("bpsk", 512, seed=5)
    offset = np.deg2rad(37.0)
    rotated = clean * np.exp(1j * offset)

    assert evm_db(rotated, table) < -100, "static rotation must not show in EVM"

    result = track_carrier(rotated, table, loop_bw=0.05)
    converged = np.degrees(result.phase_rad[-1])
    assert converged == pytest.approx(37.0, abs=1.0), f"converged to {converged:.2f} deg"


def test_tracking_beats_no_tracking_under_a_frequency_offset():
    # 0.01 rad/symbol is 240 Hz at 240 kHz symbol rate, the same order as the
    # residual left by the block carrier estimate on real captures.
    table = constellation("qpsk")
    clean = _symbols("qpsk", 512, seed=6)
    index = np.arange(clean.size)
    drifted = clean * np.exp(1j * 0.01 * index)

    before = evm_db(drifted, table)
    result = track_carrier(drifted, table, loop_bw=0.03)
    after = evm_db(result.corrected, table)

    assert before > -25
    assert after < before - 10, f"expected a big improvement, {before:.1f} -> {after:.1f}"


def test_tracking_improves_all_three_modulations():
    offsets = {"bpsk": 0.02, "qpsk": 0.02, "qam16": 0.02}
    for name, offset in offsets.items():
        table = constellation(name)
        clean = _symbols(name, 1024, seed=7)
        index = np.arange(clean.size)
        drifted = clean * np.exp(1j * offset * index)
        result = track_carrier(drifted, table, loop_bw=0.03)
        before, after = evm_db(drifted, table), evm_db(result.corrected, table)
        assert after < before - 8, f"{name}: {before:.1f} -> {after:.1f}"


def test_tracking_tolerates_noise():
    table = constellation("qpsk")
    clean = _symbols("qpsk", 2048, seed=8)
    rng = np.random.default_rng(9)
    noisy = clean + 0.05 * (rng.standard_normal(clean.size) + 1j * rng.standard_normal(clean.size))
    index = np.arange(noisy.size)
    drifted = noisy * np.exp(1j * 0.02 * index)
    result = track_carrier(drifted, table, loop_bw=0.02)
    assert evm_db(result.corrected, table) < evm_db(drifted, table) - 8


def test_tracking_outputs_have_the_expected_shapes_and_dtypes():
    table = constellation("bpsk")
    symbols = _symbols("bpsk", 256, seed=10)
    result = track_carrier(symbols, table)
    assert result.corrected.shape == symbols.shape
    assert result.phase_rad.shape == symbols.shape
    assert result.frequency_rad_per_symbol.shape == symbols.shape
    assert result.error_rad.shape == symbols.shape
    assert result.corrected.dtype == np.complex128
    assert np.isfinite(result.phase_rad).all()


def test_error_is_clipped_so_one_bad_symbol_cannot_break_lock():
    table = constellation("qpsk")
    symbols = _symbols("qpsk", 512, seed=11)
    symbols[100] = 50 + 0j        # a gross outlier

    clipped = track_carrier(symbols, table, loop_bw=0.02, max_error_rad=0.6)
    unclipped = track_carrier(symbols, table, loop_bw=0.02, max_error_rad=1e9)

    assert np.max(np.abs(clipped.error_rad)) <= 0.6 + 1e-12
    assert np.max(np.abs(unclipped.error_rad)) > 0.6
    # The clipped loop stays usable, which is the point of clipping.
    assert np.isfinite(clipped.phase_rad).all()


def test_tracking_rejects_bad_input():
    table = constellation("bpsk")
    with pytest.raises(ValueError):
        track_carrier(np.array([]), table)
    with pytest.raises(ValueError):
        track_carrier(np.array([[1 + 0j, 2 + 0j]]), table)
    with pytest.raises(ValueError):
        track_carrier(np.array([np.nan + 0j]), table)
    with pytest.raises(ValueError):
        track_carrier(np.array([1 + 0j]), np.array([]))
    with pytest.raises(ValueError):
        track_carrier(np.array([1 + 0j]), table, loop_bw=0.0)
    with pytest.raises(ValueError):
        track_carrier(np.array([1 + 0j]), table, loop_bw=0.6)
    with pytest.raises(ValueError):
        track_carrier(np.array([1 + 0j]), table, damping=0.0)


def test_evm_rejects_empty_input():
    with pytest.raises(ValueError):
        evm_db(np.array([]), constellation("bpsk"))


@pytest.mark.parametrize("name",["bpsk","qpsk","qam16"])
def test_tracking_phase_is_invariant_to_adc_gain(name):
    clean=_symbols(name,1024,seed=41)
    x=clean*np.exp(1j*(.1+.012*np.arange(len(clean))))
    low=track_carrier(x,constellation(name),loop_bw=.03)
    high=track_carrier(x*300,constellation(name),loop_bw=.03)
    np.testing.assert_allclose(low.phase_rad,high.phase_rad,atol=1e-10)
    np.testing.assert_allclose(low.corrected*300,high.corrected,atol=1e-9)


def test_reference_evm_is_rotation_invariant_but_decision_evm_need_not_be():
    expected=_symbols("qam16",1024,seed=42)
    rotated=expected*7.3*np.exp(1j*np.deg2rad(37))
    assert reference_evm_db(rotated,expected) < -100
    assert evm_db(rotated,constellation("qam16")) > -20


def test_reference_evm_exposes_wrong_symbol_order_even_with_perfect_constellation():
    expected=_symbols("qpsk",1024,seed=43)
    reordered=np.roll(expected,1)
    assert evm_db(reordered,constellation("qpsk")) < -100
    assert reference_evm_db(reordered,expected) > 0


@pytest.mark.parametrize("parameter",[{"loop_bw":float("nan")},{"damping":float("inf")},
                                      {"max_error_rad":-1},{"initial_phase":float("nan")}])
def test_tracking_rejects_nonfinite_or_invalid_loop_parameters(parameter):
    with pytest.raises(ValueError):
        track_carrier(np.ones(32),constellation("bpsk"),**parameter)
