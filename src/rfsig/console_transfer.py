"""Bounded binary upload to known RAM paths through an owned Linux console.

No port discovery or RF operations. Caller must establish board identity,
ownership and a tmpfs directory, then verify the remote SHA before using data.
"""
import base64
import hashlib
import re
import time
import uuid


def upload_uudecode(board, payload, destination, *, time_limit=180):
    if not isinstance(payload, bytes) or not 0 < len(payload) <= 4*1024*1024:
        raise ValueError('Upload requires 1..4 MiB bytes')
    if (not isinstance(destination,str)
            or not re.fullmatch(r'/tmp/p35-[A-Za-z0-9TZ-]+/[A-Za-z0-9][A-Za-z0-9_.-]*',destination)
            or '..' in destination or len('u='+destination)>72):
        raise ValueError('One validated temporary file path required')
    if not 1<=time_limit<=180:raise ValueError('Upload timeout must be 1..180 s')
    token=uuid.uuid4().hex[:8];ready='__UR'+token+'__';done='__UD'+token+'__'
    decoder=False;tty_saved=False
    encoded=base64.b64encode(payload);lines=[encoded[i:i+76] for i in range(0,len(encoded),76)]
    board.command('command -v uudecode')
    board.command('u='+destination)
    board.command('u5r='+ready);board.command('u5d='+done)
    try:
        board.command('u5tty=$(stty -g)');tty_saved=True
        board.command('stty -echo')
        board.port.write(b'echo $u5r; uudecode -o $u; echo $u5d:$?\r');decoder=True
        answer=board.read(3,r'^'+ready+r'\r?$')
        if not re.search(r'^'+ready+r'\r?$',answer,re.M) or done in answer:
            raise RuntimeError('Decoder readiness not confirmed')
        board.port.write(b'begin-base64 600 payload.bin\n')
        begin=time.monotonic()
        for offset in range(0,len(lines),16):
            if board.port.in_waiting:
                early=board.read(.01)
                if done in early:raise RuntimeError('Decoder exited before payload completed')
            board.port.write(b'\n'.join(lines[offset:offset+16])+b'\n')
            if time.monotonic()-begin>time_limit:raise TimeoutError('Console upload exceeded bound')
            time.sleep(.02)
        board.port.write(b'====\n')
        tail=board.read(15,r'^'+done+r':\d+\r?$')
        if not re.search(r'^'+done+r':0\r?$',tail,re.M):raise RuntimeError('Decoder exit not confirmed successful')
        decoder=False
        return dict(transport='Linux_console_uudecode',payload_bytes=len(payload),
                    payload_sha256=hashlib.sha256(payload).hexdigest(),
                    protocol_complete=True,remote_SHA_verified_by_this_function=False)
    finally:
        if decoder:
            board.port.write(b'\x03\r')
            board.read(2,r'^'+done+r':\d+\r?$')
        if tty_saved:board.command('stty "$u5tty"')
