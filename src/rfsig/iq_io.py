"""读取 IIO Oscilloscope 导出的 I/Q CSV。"""

import csv
from pathlib import Path

import numpy as np
from numpy.typing import NDArray


def load_iq_csv(path: str | Path) -> NDArray[np.int16]:
    """返回形状为 (样本对数, 2) 的原始有符号整数。"""
    pairs = []

    with Path(path).open("r", encoding="utf-8-sig", newline="") as file:
        for line_number, row in enumerate(csv.reader(file), start=1):
            if not row or all(not cell.strip() for cell in row):
                continue
            if len(row) < 2 or any(cell.strip() for cell in row[2:]):
                raise ValueError(f"第 {line_number} 行列数不正确")

            try:
                i, q = int(row[0].strip()), int(row[1].strip())
            except ValueError as error:
                raise ValueError(f"第 {line_number} 行不是整数") from error

            if not all(-32768 <= value <= 32767 for value in (i, q)):
                raise ValueError(f"第 {line_number} 行超出有符号 16 位范围")
            pairs.append((i, q))

    if not pairs:
        raise ValueError("文件没有 I/Q 样本")
    return np.asarray(pairs, dtype=np.int16)


def load_iq_binary_s16(path: str | Path) -> NDArray[np.int16]:
    """Read interleaved little-endian signed 16-bit I/Q.

    This is what `iio_readdev cf-ad9361-lpc > seg.bin` writes on the board, and
    what the AD9361 RX channel format (`le:s12/16>>0`) looks like once dumped:
    12-bit samples sign-extended into 16 bits, interleaved I then Q.

    Returns a flat int16 array whose length must be even; the caller pairs it.
    """
    raw = Path(path).read_bytes()
    if not raw:
        raise ValueError("file is empty")
    if len(raw) % 4:
        raise ValueError(
            f"byte count {len(raw)} is not a multiple of 4 (one I/Q pair of int16)"
        )
    return np.frombuffer(raw, dtype="<i2")


def pairs_to_complex(words: NDArray[np.int16]) -> NDArray[np.complex128]:
    """Interleaved I,Q int16 words -> complex128 array."""
    array = np.asarray(words)
    if array.ndim != 1 or array.size == 0 or array.size % 2:
        raise ValueError("need a non-empty flat array with an even number of words")
    return array[0::2].astype(np.float64) + 1j * array[1::2].astype(np.float64)


def decode_iq_dma_s16(
    raw: bytes,
    channels: int = 4,
    i_index: int = 0,
    q_index: int = 1,
) -> NDArray[np.complex128]:
    """Decode a CF-AD9361 DMA dump into one complex stream.

    Measured on the TLZ7xH-EVM: `iio_readdev -s N cf-ad9361-lpc` writes
    ``N * channels * 2`` bytes, with ``channels = 4`` because both RX1 and RX2
    are interleaved (I1, Q1, I2, Q2). Each channel is ``le:S12/16>>0``, i.e. two
    bytes holding a 12-bit signed sample.

    Pairing the raw little-endian int16 words two at a time — as one would for a
    two-channel device — silently produces half the samples with interleaved
    channels, so the channel count must be stated rather than assumed.
    """
    if not raw:
        raise ValueError("capture is empty")
    if isinstance(channels, bool) or not isinstance(channels, (int, np.integer)):
        raise ValueError("channels must be an integer")
    if channels < 2:
        raise ValueError("channels must be at least 2")
    if not (0 <= i_index < channels) or not (0 <= q_index < channels):
        raise ValueError("channel indices must be within range")
    if i_index == q_index:
        raise ValueError("i_index and q_index must differ")
    width = channels * 2
    if len(raw) % width:
        raise ValueError(
            f"byte count {len(raw)} is not a multiple of {width} "
            f"({channels} channels x 2 bytes)"
        )
    frames = np.frombuffer(raw, dtype="<i2").reshape(-1, channels)
    return frames[:, i_index].astype(np.float64) + 1j * frames[:, q_index].astype(np.float64)


def load_iq_dma_s16(
    path: str | Path,
    channels: int = 4,
    i_index: int = 0,
    q_index: int = 1,
) -> NDArray[np.complex128]:
    """Read a CF-AD9361 DMA dump from disk; see :func:`decode_iq_dma_s16`."""
    return decode_iq_dma_s16(Path(path).read_bytes(), channels, i_index, q_index)
