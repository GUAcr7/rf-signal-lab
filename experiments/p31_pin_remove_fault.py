"""Match the saved Oops instructions to supplied kernel bytes, then disassemble."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import struct
import subprocess
import zlib

ROOT=Path(__file__).resolve().parents[1]
OBJDUMP=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin/arm-linux-gnueabihf-objdump')


def posix(path):
    text=path.resolve().as_posix()
    return '/mnt/'+text[0].lower()+text[2:]


def main():
    identity=ROOT/'results/p31-kernel-image-20261019T144415Z/report.json'
    info=json.loads(identity.read_text('utf-8'))
    image=Path(info['source']).read_bytes()
    if hashlib.sha256(image).hexdigest()!=info['sha256']:
        raise RuntimeError('supplied image changed')
    raw=zlib.decompress(image[info['banners'][0]['gzip_offset']:],31)
    origin=ROOT/'results/p31-rf-driver-test-20261019T141834Z/report.json'
    failure=json.loads(origin.read_text('utf-8'))
    text=next(s['output'] for s in failure['stages'] if 'PC is at axiadc_remove' in s.get('output',''))
    code=re.search(r'Code: ([^\r\n]+)',text)[1]
    words=re.findall(r'[0-9a-f]{8}',code)
    pattern=b''.join(struct.pack('<I',int(word,16)) for word in words)
    if len(words)!=5 or raw.count(pattern)!=1:
        raise RuntimeError('fault instruction sequence must have one exact binary match')
    index=raw.index(pattern)
    pc=int(re.search(r'pc : \[<([0-9a-f]+)>\]',text)[1],16)
    offset,size=[int(n,16) for n in re.search(r'PC is at axiadc_remove\+0x([0-9a-f]+)/0x([0-9a-f]+)',text).groups()]
    start=index+16-offset
    function=raw[start:start+size]
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p31-remove-fault-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out/'axiadc_remove.bin').write_bytes(function)
    (out/'oops-fragment.txt').write_text(text,encoding='utf-8',newline='\n')
    command=['wsl.exe','--exec',posix(OBJDUMP),'-D','-b','binary','-m','arm','--adjust-vma='+hex(pc-offset),posix(out/'axiadc_remove.bin')]
    result=subprocess.run(command,capture_output=True,timeout=20)
    (out/'objdump.txt').write_bytes(result.stdout)
    (out/'objdump.stderr').write_bytes(result.stderr)
    disassembly=result.stdout.decode('utf-8',errors='replace')
    instruction=next((line for line in disassembly.splitlines() if re.match(r'\s*'+f'{pc:x}'+r':',line)), '')
    accepted=result.returncode==0 and 'e5930008' in instruction and 'ldr' in instruction and '[r3, #8]' in instruction
    report=dict(status='fault_instruction_matched_and_disassembled' if accepted else 'failed',
        failure=str(origin),image_identity=str(identity),image_sha256=info['sha256'],
        unique_20_byte_sequence_match=True,image_sequence_offset=index,
        fault_pc=hex(pc),fault_function_offset=offset,function_size=size,
        fault_instruction=instruction,saved_r3='00000000',fault_address='00000008',
        function_sha256=hashlib.sha256(function).hexdigest(),objdump_sha256=hashlib.sha256(OBJDUMP.read_bytes()).hexdigest(),
        command=command,exit_code=result.returncode,board_operations=False,
        conclusion='Saved Oops executes ldr r0,[r3,#8] with r3=0; the prior instruction loads driver from device+0x50. This matches the supplied ADC remove source driver->owner access.',
        limitations=['Binary sequence and build banner match; exact dirty source tree/configuration still not reproduced',
            'No kernel fix compiled or loaded; no claim that a NULL check alone fixes provider/consumer lifetime'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)
    print(report['status'])
    print(instruction)
    return 0 if accepted else 1


if __name__=='__main__':raise SystemExit(main())
