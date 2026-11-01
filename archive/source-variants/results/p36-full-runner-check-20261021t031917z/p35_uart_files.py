"""Hash-verified UART upload using an already identified, exclusively held shell."""
import base64
import hashlib
import re
import time

def upload(board,remote,data):
    if not re.fullmatch(r'/tmp/p35-[A-Za-z0-9_./-]+',remote) or '..' in remote:
        raise ValueError('upload only into a unique P35 RAM experiment directory')
    if len(data)>8*1024*1024:
        raise ValueError('upload exceeds reviewed UART limit')
    command='echo __P35_DATA__; base64 -d > '+remote
    if len(command)>72:raise ValueError('upload command too long')
    board.command('test ! -e '+remote)
    decoder=False
    board.port.write(b'stty -echo\r')
    board.record['stages'].append(dict(stage='upload_echo_off',output=board.read(.4)))
    try:
        board.port.write((command+'\r').encode('ascii'));decoder=True
        banner=board.read(5,r'^__P35_DATA__\r?$')
        board.record['stages'].append(dict(stage='upload_banner',path=remote,output=banner));board.save()
        if not re.search(r'^__P35_DATA__\r?$',banner,re.M):raise RuntimeError('decoder banner absent')
        encoded=base64.b64encode(data)
        lines=[encoded[n:n+76] for n in range(0,len(encoded),76)]
        start=time.monotonic();sent=0;last_notice=start
        for index in range(0,len(lines),16):
            block=b'\n'.join(lines[index:index+16])+b'\n'
            board.port.write(block);sent+=len(block)
            if board.port.in_waiting:board.port.read(board.port.in_waiting)
            delay=sent/9000-(time.monotonic()-start)
            if delay>0:time.sleep(delay)
            if time.monotonic()-last_notice>30:
                print('Verified-shell upload in progress: '+str(round(100*sent/(len(encoded)+len(lines))))+'%',flush=True)
                last_notice=time.monotonic()
        board.port.write(b'\n\x04')
        tail=board.read(12,r'(?:^|\n)[^\r\n]*#\s*$')
        board.record['stages'].append(dict(stage='upload_tail',path=remote,output=tail));board.save()
        if not re.search(r'(?:^|\n)[^\r\n]*#\s*$',tail):raise RuntimeError('decoder did not exit')
        decoder=False
    finally:
        if decoder:
            # This process owns this decoder and proved idle before uploading.
            board.port.write(b'\x03\r');board.read(.5)
        board.port.write(b'stty echo\r')
        board.record['stages'].append(dict(stage='upload_echo_restored',output=board.read(.4)))
    digest=hashlib.sha256(data).hexdigest()
    actual=board.command('sha256sum '+remote)
    if not re.search(r'^'+digest+r'\s',actual,re.M):raise RuntimeError('uploaded hash mismatch')
    return digest
