import pytest
from rfsig.tjc_protocol import END, ProtocolError, ReturnParser, get_number, set_number, set_text


def test_official_get_and_touch_examples_byte_exact():
    assert get_number('n0') == b'get n0.val\xff\xff\xff'
    events = ReturnParser().feed(bytes.fromhex('65 00 02 01 ff ff ff'))
    assert len(events) == 1
    assert events[0].kind == 'touch' and events[0].payload == bytes([0, 2, 1])
    number = ReturnParser().feed(bytes.fromhex('71 66 00 00 00 ff ff ff'))[0]
    assert number.numeric_u32 == 102


@pytest.mark.parametrize('value', [0, 102, 0x00FFFFFF, 0xFFFFFFFF, 0xFF0000FF])
def test_binary_values_containing_terminator_are_not_split(value):
    raw = b'\x71' + value.to_bytes(4, 'little') + END
    parser = ReturnParser(); events = []
    for byte in raw:
        events += parser.feed(bytes([byte]))
    assert [event.numeric_u32 for event in events] == [value]
    assert parser.buffer == b''


def test_coalesced_events_and_partial_tail():
    parser = ReturnParser()
    events = parser.feed(b'\x01' + END + b'\x65\x00\x02\x00' + END + b'\x71\x66')
    assert [event.kind for event in events] == ['status', 'touch']
    assert parser.feed(b'\x00\x00\x00' + END)[0].numeric_u32 == 102


def test_byte_by_byte_string_followed_by_page():
    parser = ReturnParser(); events = []
    for byte in b'\x70READY' + END + b'\x66\x00' + END:
        events += parser.feed(bytes([byte]))
    assert [(event.kind, event.payload) for event in events] == [('text', b'READY'), ('page', b'\x00')]


@pytest.mark.parametrize('bad', [b'\xaa', b'\x65\x00\x02\x09' + END,
                               b'\x71\x01\x00\x00\x00\xff\x00\xff'])
def test_unknown_and_malformed_frames_fail_closed(bad):
    parser = ReturnParser()
    with pytest.raises(ProtocolError):
        parser.feed(bad)
    assert parser.buffer == b''
    assert parser.feed(b'\x88' + END)[0].code == 0x88


def test_oversized_text_is_bounded():
    parser = ReturnParser(max_text_bytes=4)
    assert parser.feed(b'\x70ABCD' + END)[0].payload == b'ABCD'
    with pytest.raises(ProtocolError):
        parser.feed(b'\x70' + b'x' * 10000)
    assert parser.buffer == b''


def test_status_commands_are_short_and_numeric_bounds_explicit():
    assert set_text('t0', 'READY') == b't0.txt="READY"' + END
    assert set_number('n0', 15) == b'n0.val=15' + END
    for value in (-1, 0x80000000, True, 1.5):
        with pytest.raises(ProtocolError):
            set_number('n0', value)


@pytest.mark.parametrize('name,text', [('n0;rest', 'READY'), ('n0', 'READY";rest'),
                                     ('n0', 'line\nnext'), ('n0', 'bad\\escape')])
def test_command_injection_and_unverified_escapes_rejected(name, text):
    with pytest.raises(ProtocolError):
        set_text(name, text)
