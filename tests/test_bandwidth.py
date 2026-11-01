import numpy as np
import pytest

from rfsig.bandwidth import occupied_bandwidth, rrc_occupied_bandwidth_hz


def test_uniform_density_has_hand_calculated_equal_tail_edges():
    result = occupied_bandwidth(np.arange(10)+0.5, np.ones(10), (0, 10), rf_lo_hz=2_400_000_000)
    assert result.lower_hz == pytest.approx(0.05)
    assert result.upper_hz == pytest.approx(9.95)
    assert result.bandwidth_hz == pytest.approx(9.9)
    assert result.center_baseband_hz == pytest.approx(5)
    assert result.center_rf_hz == pytest.approx(2_400_000_005)
    assert result.effective_region_power == 10


def test_partial_bins_at_roi_edges_are_integrated_by_actual_width():
    result = occupied_bandwidth(np.arange(10)+0.5, np.ones(10), (2.25, 7.75))
    assert result.effective_region_power == 5.5
    assert result.lower_hz == pytest.approx(2.2775)
    assert result.upper_hz == pytest.approx(7.7225)
    assert result.bandwidth_hz == pytest.approx(5.445)


def test_known_cumulative_edges_land_on_cell_boundaries():
    result = occupied_bandwidth([0, 1, 2], [0.5, 99, 0.5], (-0.5, 2.5))
    assert result.lower_hz == pytest.approx(0.5)
    assert result.upper_hz == pytest.approx(1.5)
    assert result.bandwidth_hz == pytest.approx(1)


def test_single_active_bin_uses_explicit_uniform_cell_interpolation():
    result = occupied_bandwidth([0, 1, 2], [0, 100, 0], (-0.5, 2.5))
    assert result.lower_hz == pytest.approx(0.505)
    assert result.upper_hz == pytest.approx(1.495)
    assert result.bandwidth_hz == pytest.approx(0.99)


def test_known_noise_floor_removal_recovers_hand_spectrum_and_preserves_input():
    f = np.arange(5)+0.5
    density = np.array([2., 3., 5., 3., 2.])
    before = density.copy()
    result = occupied_bandwidth(f, density, (0, 5), noise_floor_psd=2)
    expected = occupied_bandwidth(f, [0, 1, 3, 1, 0], (0, 5))
    assert result.lower_hz == pytest.approx(expected.lower_hz)
    assert result.upper_hz == pytest.approx(expected.upper_hz)
    assert result.observed_region_power == 15
    assert result.effective_region_power == 5
    np.testing.assert_array_equal(density, before)


def test_zero_or_fully_subtracted_power_returns_no_measurement():
    for density, floor in ([0, 0, 0], 0), ([1, 1, 1], 2):
        result = occupied_bandwidth([0, 1, 2], density, (-0.5, 2.5), noise_floor_psd=floor)
        assert result.status == "no_effective_power"
        assert result.lower_hz is result.upper_hz is result.bandwidth_hz is None
        assert result.center_baseband_hz is result.center_rf_hz is None


def test_explicit_power_threshold_returns_status_instead_of_fake_edges():
    result = occupied_bandwidth([0, 1, 2], [1, 1, 1], (-0.5, 2.5), min_effective_power=3)
    assert result.status == "below_power_threshold"
    assert result.effective_region_power == 3
    assert result.bandwidth_hz is None


def test_scale_invariance_and_frequency_translation():
    f, density = np.arange(10)+0.5, np.array([0, 1, 3, 5, 1, 1, 2, 1, 0, 0])
    first = occupied_bandwidth(f, density, (0, 10))
    scaled = occupied_bandwidth(f, density*4, (0, 10))
    moved = occupied_bandwidth(f+1000, density, (1000, 1010))
    assert scaled.lower_hz == pytest.approx(first.lower_hz)
    assert scaled.upper_hz == pytest.approx(first.upper_hz)
    assert moved.bandwidth_hz == pytest.approx(first.bandwidth_hz)
    assert moved.center_baseband_hz == pytest.approx(first.center_baseband_hz+1000)


def test_full_fraction_uses_first_and_last_nonzero_cell_edges():
    result = occupied_bandwidth(np.arange(5), [0, 2, 0, 3, 0], (-0.5, 4.5), occupied_fraction=1)
    assert result.lower_hz == 0.5
    assert result.upper_hz == 3.5
    assert result.bandwidth_hz == 3


def test_asymmetric_distribution_center_is_not_peak_bin_or_weighted_mean():
    result = occupied_bandwidth(np.arange(4), [1, 9, 1, 3], (-0.5, 3.5))
    assert not np.isclose(result.center_baseband_hz, 1)
    assert not np.isclose(result.center_baseband_hz, 20/14)


@pytest.mark.parametrize("kwargs", [
    {"occupied_fraction": 0}, {"occupied_fraction": 1.1}, {"occupied_fraction": np.nan},
    {"noise_floor_psd": -1}, {"min_effective_power": -1}, {"rf_lo_hz": -1},
    {"analysis_band_hz": (1, 0)}, {"analysis_band_hz": (-1, 2.5)},
    {"analysis_band_hz": (0, 3)}, {"analysis_band_hz": (0, np.inf)},
    {"analysis_band_hz": (0, 1, 2)}, {"occupied_fraction": True},
])
def test_rejects_invalid_band_options(kwargs):
    options = dict(analysis_band_hz=(-0.5, 2.5))
    options.update(kwargs)
    with pytest.raises(ValueError):
        occupied_bandwidth([0, 1, 2], [1, 1, 1], **options)


@pytest.mark.parametrize("f,density", [
    ([0], [1]), ([0, 0, 1], [1, 1, 1]), ([0, 1, 3], [1, 1, 1]),
    ([0, 1, 2], [1, -1, 1]), ([0, 1, 2], [1, np.nan, 1]),
    ([0, np.inf, 2], [1, 1, 1]), ([0, 1, 2], [1, 2]),
    ([0, 1, 2], [1j, 1j, 1j]), ([[0, 1, 2]], [1, 1, 1]),
])
def test_rejects_invalid_frequency_or_linear_psd(f, density):
    with pytest.raises(ValueError):
        occupied_bandwidth(f, density, (0, 1))


# --- analytic RRC occupied bandwidth -------------------------------------
#
# The independent expectation below integrates the raised-cosine PSD directly,
# which is a different method from the closed form under test.

def _rc_numeric_obw(fraction, beta, rs, n=2_000_001):
    a = (1 - beta) * rs / 2
    roll = beta * rs
    half = (1 + beta) * rs / 2
    f = np.linspace(0.0, half, n)
    density = np.where(f <= a, 1.0,
                       np.where(f <= half, 0.5 * (1 + np.cos(np.pi * (f - a) / roll)), 0.0))
    cdf = np.cumsum(density) * (half / (n - 1))
    # Two-sided fraction inside +/-x equals the one-sided fraction of E(x)/E(half).
    return float(2 * f[int(np.searchsorted(cdf, fraction * cdf[-1]))])


@pytest.mark.parametrize("fraction", [0.5, 0.65, 0.8, 0.9, 0.95, 0.99, 0.999])
def test_rrc_occupied_bandwidth_matches_direct_integration(fraction):
    closed = rrc_occupied_bandwidth_hz(fraction, 240_000, 0.35)
    assert closed == pytest.approx(_rc_numeric_obw(fraction, 0.35, 240_000), abs=1.0)


def test_rrc_occupied_bandwidth_at_flat_region_edge():
    # Fraction inside the flat part is exactly (1-beta), where the width is (1-beta)*Rs.
    assert rrc_occupied_bandwidth_hz(0.65, 240_000, 0.35) == pytest.approx(156_000, abs=1e-6)


def test_rrc_occupied_bandwidth_full_fraction_is_the_support():
    # Rs*(1+beta) is the support, reached only as the contained fraction approaches 1.
    assert rrc_occupied_bandwidth_hz(1.0, 240_000, 0.35) == pytest.approx(324_000, abs=1e-6)


def test_rrc_occupied_bandwidth_99_is_narrower_than_the_support():
    # The distinction that matters: at beta=0.35 the 99% width is about 280 kHz,
    # 13% below the 324 kHz support. Conflating the two would look like a bug.
    value = rrc_occupied_bandwidth_hz(0.99, 240_000, 0.35)
    assert value == pytest.approx(279_997.7, abs=0.5)
    assert value < 240_000 * 1.35


def test_rrc_occupied_bandwidth_zero_rolloff_is_rectangular():
    # beta=0 gives a rectangular Rs-wide spectrum, so containment scales linearly.
    assert rrc_occupied_bandwidth_hz(0.99, 240_000, 0.0) == pytest.approx(237_600, abs=1e-6)


def test_rrc_occupied_bandwidth_is_monotonic_and_bounded():
    values = [rrc_occupied_bandwidth_hz(f, 240_000, 0.35) for f in np.linspace(0.1, 1.0, 40)]
    assert np.all(np.diff(values) > 0)
    assert values[-1] == pytest.approx(324_000, abs=1e-6)
    assert max(values) <= 240_000 * 1.35 + 1e-6


@pytest.mark.parametrize("kwargs", [
    {"occupied_fraction": 0}, {"occupied_fraction": 1.1}, {"occupied_fraction": np.nan},
    {"occupied_fraction": True}, {"symbol_rate_hz": 0}, {"symbol_rate_hz": -1},
    {"symbol_rate_hz": np.inf}, {"rolloff": -0.1}, {"rolloff": 1.1}, {"rolloff": np.nan},
])
def test_rrc_occupied_bandwidth_rejects_invalid_options(kwargs):
    options = dict(occupied_fraction=0.99, symbol_rate_hz=240_000, rolloff=0.35)
    options.update(kwargs)
    with pytest.raises(ValueError):
        rrc_occupied_bandwidth_hz(**options)
