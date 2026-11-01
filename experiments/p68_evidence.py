"""RAM evidence tar retrieval through the already owned RX shell."""
import hashlib,io,re,tarfile
from p26_retrieve_chunks import decode_payload
from p36_retrieve_file import CHUNK_BYTES,chunk_command,unpack_verified,validate_sizes

def archive(c,b,stage,names):
    names=tuple(names)
    if (not 1<=len(names)<=32 or len(set(names))!=len(names)
        or any(not re.fullmatch(r'[a-z0-9][a-z0-9.-]{0,63}',n) for n in names)):
        raise ValueError('bounded named evidence required')
    b.command('s='+stage);b.command('o=$s/data');b.command('f=')
    for name in names:b.command('f="$f '+name+'"')
    b.command('tar -cf $s/e.tar -C $o $f',timeout=20)
    b.command('gzip -1 -c $s/e.tar >$s/e.gz',timeout=20);b.command('gzip -t $s/e.gz')
    def count(path):
        b.command('v='+path)
        values=re.findall(r'^__N__(\d+)__E__\r?$',b.command('echo __N__$(wc -c <$v)__E__'),re.M)
        if len(values)!=1:raise ValueError('ambiguous byte size')
        return int(values[0])
    size,raw_size=count(stage+'/e.gz'),count(stage+'/e.tar');validate_sizes(size,raw_size)
    wanted,raw_wanted=c.digest(b,stage+'/e.gz'),c.digest(b,stage+'/e.tar')
    c.record['contract']=dict(remote=stage+'/e.gz',bytes=size,sha256=wanted,raw_bytes=raw_size,raw_sha256=raw_wanted);c.save()
    b.command('src='+stage+'/e.gz');pieces=[]
    for index,start in enumerate(range(0,size,CHUNK_BYTES)):
        expected=min(CHUNK_BYTES,size-start)
        h=re.findall(r'^([0-9a-f]{64})\s+-\r?$',b.command(chunk_command(index,'sha256sum'),timeout=20),re.M)
        if len(h)!=1:raise ValueError('chunk hash ambiguous')
        data=None
        for attempt in range(3):
            try:
                candidate=decode_payload(b.command(chunk_command(index,'base64'),timeout=20),expected)
                if hashlib.sha256(candidate).hexdigest()!=h[0]:raise ValueError('chunk hash mismatch')
                data=candidate;break
            except ValueError as e:c.record.setdefault('transfer_retries',[]).append(dict(index=index,attempt=attempt,error=repr(e)))
        if data is None:raise ValueError('chunk retries exhausted')
        pieces.append(data);c.record['chunks'].append(dict(index=index,bytes=len(data),sha256=h[0],verified=True));c.save()
        print('P68 archive '+str(index+1)+'/'+str((size+CHUNK_BYTES-1)//CHUNK_BYTES),flush=True)
    packed=b''.join(pieces);raw=unpack_verified(packed,size,wanted,raw_size,raw_wanted)
    (c.out/'evidence.tar.gz').write_bytes(packed);files=c.out/'files';files.mkdir()
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:') as tf:
        members=tf.getmembers()
        if len(members)!=len(names) or {m.name for m in members}!=set(names) or not all(m.isfile() for m in members):raise ValueError('unexpected tar members')
        for m in members:(files/m.name).write_bytes(tf.extractfile(m).read())
    if c.digest(b,stage+'/e.gz')!=wanted:raise ValueError('archive changed')
    c.record['files_sha256']={name:hashlib.sha256((files/name).read_bytes()).hexdigest() for name in names};c.save()
