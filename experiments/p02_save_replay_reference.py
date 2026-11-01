"""Check a lossless NumPy I/Q save-and-replay round trip with known samples."""

from pathlib import Path
from tempfile import TemporaryDirectory

import numpy as np


def main() -> None:
    original = np.array([1 + 2j, -3 + 4j, -1j], dtype=np.complex128)

    with TemporaryDirectory() as folder:
        path = Path(folder) / "iq.npy"
        np.save(path, original, allow_pickle=False)
        replay = np.load(path, allow_pickle=False)

        np.testing.assert_array_equal(replay, original)
        assert replay.dtype == original.dtype
        print("样本数：", len(replay))
        print("数据类型：", replay.dtype)
        print("回放校验：通过")


if __name__ == "__main__":
    main()
