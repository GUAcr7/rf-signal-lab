import numpy as np
import pytest

from rfsig.carrier_tracking import constellation, refine_snapshot_carrier, reference_evm_db


@pytest.mark.parametrize("name", ["bpsk", "qpsk", "qam16"])
@pytest.mark.parametrize("slope", [-.0015, .0015])
def test_batch_recovers_injected_frequency_without_discarding_symbols(name, slope):
    rng = np.random.default_rng(712)
    table = constellation(name)
    ref = table[rng.integers(0, len(table), 502)]
    noise = .004*(rng.normal(size=len(ref))+1j*rng.normal(size=len(ref)))
    received = 17*(ref+noise)*np.exp(1j*(.64+slope*np.arange(len(ref))))
    result = refine_snapshot_carrier(received, table)
    assert len(result.corrected) == len(ref)
    assert result.residual_frequency_rad_per_symbol == pytest.approx(slope, abs=8e-6)
    assert reference_evm_db(result.corrected, ref) < -43


def test_batch_fit_does_not_make_noise_a_good_constellation():
    rng = np.random.default_rng(714)
    noise = rng.normal(size=502)+1j*rng.normal(size=502)
    from rfsig.carrier_tracking import evm_db
    assert evm_db(refine_snapshot_carrier(noise, constellation("qam16")).corrected, constellation("qam16")) > -15


@pytest.mark.parametrize("bad", [0, 11, True, 1.2])
def test_batch_rejects_invalid_iteration_counts(bad):
    with pytest.raises(ValueError):
        refine_snapshot_carrier(np.ones(32), constellation("bpsk"), iterations=bad)
