"""Every stored padding pattern must decode to the same signed RX12 value."""
import importlib.util
from pathlib import Path
import sys

import numpy as np


def test_all_packed_words_ignore_padding_and_preserve_signed_rx12():
    experiments = Path(__file__).resolve().parents[1] / 'experiments'
    sys.path.insert(0, str(experiments))
    try:
        spec = importlib.util.spec_from_file_location('p37_review_archives', experiments / 'p37_review_archives.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        sys.path.remove(str(experiments))
    # Exhaust all 65,536 packed words, including every high4 padding pattern.
    words = np.arange(65536, dtype=np.uint32).astype('<u2')
    decoded = module.decode_rx12(words.tobytes()).reshape(-1)
    expected = np.tile(np.concatenate((np.arange(2048), np.arange(-2048, 0))), 16)
    np.testing.assert_array_equal(decoded, expected)
