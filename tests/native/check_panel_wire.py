"""Differential wire-format corpus; only stdin/stdout, no serial device."""
import importlib.util,json,random,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
spec=importlib.util.spec_from_file_location('p63_wire_codec',ROOT/'src/rfsig/tjc_protocol.py')
codec=importlib.util.module_from_spec(spec);sys.modules[spec.name]=codec;spec.loader.exec_module(codec)

def main():
    binary,out=Path(sys.argv[1]),Path(sys.argv[2]);out.mkdir(exist_ok=False)
    rng=random.Random(20261025);frames=[]
    for code in sorted(codec._ONE_BYTE_CODES):frames.append(bytes([code])+codec.END)
    for page,component,edge in [(0,6,0),(0,7,1),(255,255,0),(1,5,0)]:
        frames.append(bytes([0x65,page,component,edge])+codec.END)
    for number in (0,1,0xffffff,0x7fffffff,0xffffffff):
        frames.append(b'\x71'+number.to_bytes(4,'little')+codec.END)
    frames += [b'\x70'+b'A'*size+codec.END for size in (0,1,127,128)]
    for i in range(400):
        kind=i%4
        if kind==0:frame=bytes([0x65,rng.randrange(256),rng.randrange(256),rng.randrange(2)])+codec.END
        elif kind==1:frame=b'\x71'+rng.getrandbits(32).to_bytes(4,'little')+codec.END
        elif kind==2:frame=b'\x70'+bytes(rng.randrange(32,127) for _ in range(rng.randrange(129)))+codec.END
        else:frame=bytes([0x66,rng.randrange(256)])+codec.END
        frames.append(frame)
    wire=b''.join(frames);parser=codec.ReturnParser();expected=[]
    # Arbitrary transport splitting includes splits inside the FF terminator.
    for start in range(0,len(wire),3):
        for event in parser.feed(wire[start:start+3]):
            expected.append(dict(mode='LOGIC_ONLY_NO_RF',code=event.code,payload=event.payload.hex()))
    text='\n'.join(wire[i:i+3].hex() for i in range(0,len(wire),3))+'\n'
    p=subprocess.run([str(binary),'--hex-replay'],input=text,text=True,capture_output=True,timeout=4)
    (out/'valid.hex').write_text(text);(out/'valid.stdout').write_text(p.stdout)
    actual=[json.loads(s) for s in p.stdout.splitlines()]
    assert p.returncode==0 and actual==expected
    bad=[b'\x99',b'\x65\x00\x06\x02'+codec.END,b'\x65\x00\x06\x00\xff\x00\xff',
         b'\x70'+b'A'*129+codec.END,b'\x71\x00\x00',b'\x01\xff']
    rows=[]
    for index,data in enumerate(bad):
        p=subprocess.run([str(binary),'--hex-replay'],input=data.hex()+'\n',text=True,capture_output=True,timeout=2)
        assert p.returncode==2,(index,p.returncode)
        rows.append(dict(case=index,hex=data.hex(),exit_code=p.returncode))
    for name,text in [('odd_nibble','a\n'),('bad_hex','zz\n')]:
        p=subprocess.run([str(binary),'--hex-replay'],input=text,text=True,capture_output=True,timeout=2)
        assert p.returncode==2;rows.append(dict(case=name,exit_code=2))
    p=subprocess.run([str(binary),'--device','/dev/ttyPS0'],capture_output=True,timeout=2)
    assert p.returncode==2
    report=dict(status='passed_P63_native_wire_differential_contract',valid_frames=len(frames),
                bytes=len(wire),malformed_or_truncated_refusals=rows,hardware_mode_rejected=True,
                UART_opened=False,RF_operations=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))

if __name__=='__main__':main()
