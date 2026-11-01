import struct
import pytest
from rfsig.bitstream_format import extract_bit_payload, validate_raw_sync


def container(name=b"design\0"):
    raw = b"\xff" * 32 + b"\x00\x00\x00\xbb\x11\x22\x00\x44" + b"\xff" * 4 + b"\xaa\x99\x55\x66" + b"\x00" * 16
    header = b"\x00\x09\x0f\xf0\x0f\xf0\x0f\xf0\x0f\xf0\0\0\x01"
    for tag, value in zip(b"abcd", [name, b"7z100ffg900\0", b"2026/10/21\0", b"00:00:00\0"]):
        header += bytes([tag]) + struct.pack(">H", len(value)) + value
    return header + b"e" + struct.pack(">I", len(raw)) + raw, raw


def test_variable_header_length_and_payload_integrity():
    first, raw = container()
    second, _ = container(b"much-longer-name;COMPRESS=TRUE\0")
    a, b = extract_bit_payload(first), extract_bit_payload(second)
    assert a.data == b.data == raw
    assert a.offset != b.offset
    assert b.fields["a"] == "much-longer-name;COMPRESS=TRUE"


@pytest.mark.parametrize("mutate", [lambda x: x[:-1], lambda x: x + b"x", lambda x: b"\x01" + x[1:], lambda x: x.replace(b"\xaa\x99\x55\x66", b"\x66\x55\x99\xaa")])
def test_rejects_bad_length_header_sync_or_byte_order(mutate):
    data, _ = container()
    with pytest.raises((ValueError, UnicodeDecodeError)):
        extract_bit_payload(mutate(data))


def test_refuses_container_as_raw_or_raw_as_container():
    data, raw = container()
    validate_raw_sync(raw)
    with pytest.raises(ValueError):
        validate_raw_sync(data)
    with pytest.raises(ValueError):
        extract_bit_payload(raw)
