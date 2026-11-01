"""Small, IO-free TJC command/return codec, based on archived official docs.

No device detection, UART opens, screen flashing or RF control happens here.
Unsupported/malformed data fails closed; consumers must handle reconnect/arming.
"""
from dataclasses import dataclass
import re

END = b'\xff\xff\xff'
_ONE_BYTE_CODES = {0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x09,
                   0x11, 0x12, 0x1A, 0x1B, 0x1C, 0x1D, 0x1E, 0x1F,
                   0x20, 0x23, 0x24, 0x86, 0x87, 0x88, 0x89, 0xFD, 0xFE}


class ProtocolError(ValueError):
    pass


def _name(value):
    if not isinstance(value, str) or not re.fullmatch(r'[A-Za-z][A-Za-z0-9_]{0,14}', value):
        raise ProtocolError('A simple component name is required')
    return value


def _command(text):
    return text.encode('ascii') + END


def set_number(component, value):
    if type(value) is not int or not 0 <= value <= 0x7FFFFFFF:
        raise ProtocolError('Expected nonnegative signed-32-bit value')
    return _command(_name(component) + '.val=' + str(value))


def get_number(component):
    return _command('get ' + _name(component) + '.val')


def set_text(component, text):
    # Initial control panel uses short plain ASCII labels. No guessed escape or
    # multibyte font conventions are introduced before the HMI is compiled.
    if (not isinstance(text, str) or len(text) > 32
            or any(not 32 <= ord(ch) <= 126 or ch in ('"', '\\') for ch in text)):
        raise ProtocolError('Expected at most 32 plain ASCII characters')
    return _command(_name(component) + '.txt="' + text + '"')


@dataclass(frozen=True)
class Event:
    kind: str
    code: int
    payload: bytes

    @property
    def numeric_u32(self):
        if self.kind != 'number':
            raise ProtocolError('Not a numeric return')
        return int.from_bytes(self.payload, 'little', signed=False)


class ReturnParser:
    """Bounded fragmented/coalesced return parser; no implicit command routing.

    Numeric and touch frames have fixed lengths. Their binary payload can contain
    FF FF FF, so splitting every frame at that sequence would corrupt valid data.
    Text payload stays bytes until the actual project encoding is established.
    """
    def __init__(self, max_text_bytes=128):
        if type(max_text_bytes) is not int or not 1 <= max_text_bytes <= 256:
            raise ProtocolError('Text bound must be 1..256')
        self.max_text_bytes = max_text_bytes
        self.buffer = bytearray()

    def reset(self):
        self.buffer.clear()

    def feed(self, data):
        if not isinstance(data, (bytes, bytearray)):
            raise TypeError('Expected bytes')
        events = []
        # Bound the buffer even when one incoming chunk contains excessive junk.
        try:
            for value in data:
                self.buffer.append(value)
                code = self.buffer[0]
                if code == 0x70:
                    size = self.buffer.find(END, 1)
                    if size < 0:
                        if len(self.buffer) > self.max_text_bytes + 3:
                            raise ProtocolError('Text return exceeded bound')
                        continue
                    size += 3
                    if size - 4 > self.max_text_bytes:
                        raise ProtocolError('Text payload exceeded bound')
                    kind = 'text'
                else:
                    if code in _ONE_BYTE_CODES:
                        size, kind = 4, 'status'
                    elif code == 0x65:
                        size, kind = 7, 'touch'
                    elif code == 0x66:
                        size, kind = 5, 'page'
                    elif code == 0x71:
                        size, kind = 8, 'number'
                    else:
                        raise ProtocolError('Unsupported return header')
                    if len(self.buffer) < size:
                        continue
                if self.buffer[size - 3:size] != END:
                    raise ProtocolError('Malformed frame terminator')
                payload = bytes(self.buffer[1:size - 3])
                if kind == 'touch' and payload[2] not in (0, 1):
                    raise ProtocolError('Invalid touch event')
                events.append(Event(kind, code, payload))
                del self.buffer[:size]
        except ProtocolError:
            self.reset()
            raise
        return events
