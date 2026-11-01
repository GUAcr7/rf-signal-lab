import numpy as np
import pytest

from rfsig.carrier_tracking import align_rotation,constellation,evm_db


def test_qam_fourth_moment_has_a_meaningful_ensemble_phase():
    table=constellation("qam16")
    assert np.mean(table**4)==pytest.approx(-.68+0j)
    assert np.mean((table/abs(table))**4)==pytest.approx(-.36+0j)
    theta=.41
    moment=np.mean((table*np.exp(1j*theta))**4)
    assert np.angle(moment/np.mean(table**4))/4==pytest.approx(theta)


@pytest.mark.parametrize("name",["bpsk","qpsk","qam16"])
@pytest.mark.parametrize("angle",[0.,17.3,42.5,88.0])
def test_rotation_removes_residual_gain_phase_not_only_optimises_evm(name,angle):
    table=constellation(name)
    x=np.tile(table,32)*3.7*np.exp(1j*np.deg2rad(angle))
    corrected,estimate=align_rotation(x,table)
    assert estimate==pytest.approx(angle,abs=1e-6)
    # A complex-fit EVM alone would allow a remaining global rotation. Checking
    # physical orientation catches that plateau in the old implementation.
    np.testing.assert_allclose(corrected/3.7,np.tile(table,32),atol=1e-10)
    assert evm_db(corrected,table) < -100


@pytest.mark.parametrize("option",[{"step_deg":np.nan},{"step_deg":np.inf},
                                   {"symmetry_deg":np.inf},{"symmetry_deg":0.}])
def test_invalid_rotation_search_parameters_are_rejected(option):
    with pytest.raises(ValueError): align_rotation(np.ones(32),constellation("bpsk"),**option)


def test_quadrature_ratio_is_not_rotation_invariant():
    bpsk=np.tile(constellation("bpsk"),64)
    rotated=bpsk*np.exp(1j*np.pi/4)
    assert np.mean(bpsk.imag**2)==0
    assert np.mean(rotated.real**2)==pytest.approx(np.mean(rotated.imag**2))
