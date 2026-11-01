import numpy as np
import pytest

from rfsig.carrier_tracking import constellation,evm_db,reference_evm_db
from rfsig.symbol_recovery import recover_snapshot
from rfsig.tx_waveforms import make_tx_waveform


@pytest.mark.parametrize("name",["BPSK","QPSK","16QAM"])
def test_finite_snapshot_recovers_known_symbols_with_guards_and_correct_phase(name):
    tx=make_tx_waveform(name,sample_rate_hz=128000,samples_per_symbol=8,
                        symbol_count=1024,seed=20,offset_hz=0,digital_peak_counts=256)
    start=513
    n=np.arange(2048)
    iq=tx.iq[(start+n)%len(tx.iq)]*np.exp(1j*(.3+2*np.pi*1234*n/128000))
    result=recover_snapshot(iq,128000,1234,name,samples_per_symbol=8,
                            timing_offset=(-start)%8)
    expected=tx.symbols[np.rint((start+result.sample_indices)/8).astype(int)%1024]
    assert result.sample_indices.min()>=40
    assert result.sample_indices.max()<len(iq)-40
    assert reference_evm_db(result.symbols,expected) < -35
    assert evm_db(result.symbols,constellation(name)) < -35


def test_default_timing_search_recovers_a_long_snapshot():
    tx=make_tx_waveform("QPSK",sample_rate_hz=128000,samples_per_symbol=8,
                        symbol_count=1024,seed=23,offset_hz=0,digital_peak_counts=256)
    x=np.roll(tx.iq,3)*np.exp(.4j)
    result=recover_snapshot(x,128000,0,"qpsk",samples_per_symbol=8)
    assert result.timing_offset==3
    assert evm_db(result.symbols,constellation("qpsk")) < -35


def test_undersized_snapshots_are_rejected_instead_of_using_filter_edges():
    with pytest.raises(ValueError,match="too short"):
        recover_snapshot(np.ones(1024),30_720_000,0,"bpsk")


@pytest.mark.parametrize("timing",[-1,128,1.3,True])
def test_invalid_known_timing_is_rejected(timing):
    with pytest.raises(ValueError):
        recover_snapshot(np.ones(4096),30_720_000,0,"bpsk",timing_offset=timing)
