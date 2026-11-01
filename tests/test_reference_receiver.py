import numpy as np
import pytest

from rfsig.reference_receiver import measure_known_snapshot
from rfsig.tx_waveforms import make_tx_waveform


@pytest.mark.parametrize("name",["BPSK","QPSK","16QAM"])
def test_known_reference_uses_tx_offset_and_rx_carrier_separately(name):
    tx=make_tx_waveform(name,sample_rate_hz=128000,samples_per_symbol=8,symbol_count=1024,
                        offset_hz=1000,digital_peak_counts=256,seed=26)
    ref=tx.iq*np.exp(-2j*np.pi*1000*np.arange(len(tx.iq))/128000)
    n=np.arange(2048)
    iq=ref[(7813+n)%len(ref)]*np.exp(1j*(.7+2*np.pi*1234.5*n/128000))
    result=measure_known_snapshot(iq,tx,1234,dma_buffer_samples=2048)
    assert result.alignment.source_start==7813
    assert result.alignment.frequency_hz==pytest.approx(1234.5,abs=.1)
    assert result.evm_db < -35
    assert result.symbol_errors==0


def test_known_reference_rejects_multibuffer_input():
    tx=make_tx_waveform("QPSK",sample_rate_hz=128000,samples_per_symbol=8,symbol_count=1024)
    with pytest.raises(ValueError,match="DMA boundary"):
        measure_known_snapshot(np.ones(4096),tx,0,dma_buffer_samples=2048)
