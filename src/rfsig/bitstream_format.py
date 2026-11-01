"""Strict Xilinx .bit container extraction for checked build artifacts.

This only verifies container structure and the Zynq loader's initial sync window.
It does not establish a compatible FPGA design, license, timing, or safe pairing.
"""
from dataclasses import dataclass


@dataclass(frozen=True)
class BitPayload:
    data: bytes
    offset: int
    fields: dict[str, str]


def validate_raw_sync(data: bytes) -> None:
    # The supplied Zynq 4.9 loader searches its first 52 bytes. Require the
    # native .bin byte order used by this project, with word-aligned sync.
    window = data[:52]
    if len(data) < 52 or len(data) % 4:
        raise ValueError("raw payload must contain whole words and a sync window")
    if not any(window[pos:pos + 4] == b"\xaa\x99\x55\x66"
               for pos in range(0, 49, 4)):
        raise ValueError("native raw configuration sync is absent in first 52 bytes")


def extract_bit_payload(container: bytes) -> BitPayload:
    position = 0

    def take(count: int) -> bytes:
        nonlocal position
        if count < 0 or position + count > len(container):
            raise ValueError("truncated .bit container")
        result = container[position:position + count]
        position += count
        return result

    def number(count: int) -> int:
        return int.from_bytes(take(count), "big")

    if number(2) != 9 or take(9) != b"\x0f\xf0\x0f\xf0\x0f\xf0\x0f\xf0\x00":
        raise ValueError("not a supported Xilinx .bit header")
    if number(2) != 1:
        raise ValueError("invalid first tag length")
    fields = {}
    for tag in b"abcd":
        if take(1) != bytes([tag]):
            raise ValueError("unexpected or duplicated .bit metadata tag")
        text = take(number(2))
        if not text or text[-1:] != b"\0" or b"\0" in text[:-1]:
            raise ValueError("invalid .bit metadata string")
        fields[chr(tag)] = text[:-1].decode("ascii", errors="strict")
    if take(1) != b"e":
        raise ValueError("configuration payload tag missing")
    length = number(4)
    offset = position
    payload = take(length)
    if position != len(container):
        raise ValueError("trailing bytes after configuration payload")
    validate_raw_sync(payload)
    return BitPayload(payload, offset, fields)
