from pathlib import Path
import sys
from types import SimpleNamespace

import numpy as np
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/"experiments"))
import p25_continuity_check as checker
from p26_retrieve_chunks import decode_payload


def test_failed_middle_window_is_not_compared_as_an_adjacent_window(monkeypatch):
    monkeypatch.setattr(checker, "load_iq_dma_s16", lambda *a, **k: np.ones(96, dtype=complex))
    monkeypatch.setattr(checker, "initial_frequency", lambda x: 0.)
    fits = iter([10, None, 74])
    def align(*args, **kwargs):
        start = next(fits)
        if start is None:
            raise ValueError("no confident alignment")
        return SimpleNamespace(source_start=start, correlation=.999, nmse_db=-25., frequency_hz=0.)
    monkeypatch.setattr(checker, "align_periodic_reference", align)
    result = checker.check(Path("unused.bin"), 32, np.ones(128))
    assert result["assessment"]["status"] == "inconclusive"
    assert result["signed_modulo_gaps"] == [None, None]


def test_partial_window_is_rejected_before_analysis(monkeypatch):
    monkeypatch.setattr(checker, "load_iq_dma_s16", lambda *a, **k: np.ones(65, dtype=complex))
    with pytest.raises(ValueError, match="whole DMA"):
        checker.check(Path("unused.bin"), 32, np.ones(128))


def test_weak_alignment_is_unverified_not_a_jump(monkeypatch):
    monkeypatch.setattr(checker, "load_iq_dma_s16", lambda *a, **k: np.ones(64, dtype=complex))
    monkeypatch.setattr(checker, "initial_frequency", lambda x: 0.)
    monkeypatch.setattr(checker, "align_periodic_reference", lambda *a, **k:
                        SimpleNamespace(source_start=10, correlation=.1, nmse_db=20., frequency_hz=0.))
    result = checker.check(Path("unused.bin"), 32, np.ones(128))
    assert result["assessment"]["status"] == "inconclusive"
    assert result["cells_with_abs_gap_gt_1"] == 0


def test_chunk_decoder_recovers_only_payload_and_checks_length():
    import base64
    raw = bytes(range(256))*21
    encoded = base64.encodebytes(raw).decode().replace("\n", "\r\n")
    trace = "root@board:~# dd if=$p | base64\r\n"+encoded+"root@board:~# echo __P22_RC__:$?\r\n__P22_RC__:0\r\n"
    assert decode_payload(trace, len(raw)) == raw
    with pytest.raises(ValueError):
        decode_payload(trace, len(raw)+1)
    with pytest.raises(ValueError):
        decode_payload(trace.replace(encoded.splitlines()[1], ""), len(raw))
