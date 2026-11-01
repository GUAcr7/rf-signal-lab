"""Extract boot partition facts and selected vendor driver source, read-only inputs."""
from datetime import datetime,timezone
import difflib,hashlib,json,re,shutil,struct,subprocess,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p64-boot-source-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    original=Path('D:/FPGA natch/pluto/BOOT.bin');shutil.copy2(original,out/'BOOT.bin')
    binary=original.read_bytes();u32=lambda offset:struct.unpack_from('<I',binary,offset)[0]
    if u32(0x20)!=0xaa995566 or u32(0x24)!=0x584c4e58:raise ValueError('Wrong Zynq boot header')
    # Bootgen independently interprets the same tables; verify all fields below.
    p=subprocess.run(['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/bootgen.bat','-arch','zynq','-read','BOOT.bin'],
                     cwd=out,capture_output=True,timeout=30)
    (out/'bootgen-read.stdout').write_bytes(p.stdout);(out/'bootgen-read.stderr').write_bytes(p.stderr)
    text=p.stdout.decode(errors='replace')
    if 'PARTITION HEADER TABLE (u-boot.elf.0)' not in text or '[ERROR]' in text or 'ERROR:' in text:
        raise ValueError('Bootgen read failed')
    partitions=[];pht=u32(0x9c)
    for index,label in enumerate(('fsbl','PL','uboot')):
        fields=struct.unpack_from('<16I',binary,pht+64*index)
        if sum(fields)&0xffffffff!=0xffffffff:raise ValueError('Partition header checksum')
        length=fields[1]*4;offset=fields[5]*4
        if offset+length>len(binary) or length<=0:raise ValueError('Partition bounds')
        target=out/(label+'.bin');target.write_bytes(binary[offset:offset+length])
        partitions.append(dict(label=label,header_offset=pht+64*index,offset=offset,length=length,
            load=fields[3],entry=fields[4],attributes=fields[6],sha256=sha(target)))
    strings=re.findall(rb'[ -~]{5,}',(out/'uboot.bin').read_bytes())
    selected=[s.decode() for s in strings if any(k in s.lower() for k in (b'loadb',b'fpga',b'bootcmd',b'u-boot 20'))]
    (out/'uboot-command-strings.txt').write_text('\n'.join(selected)+'\n',encoding='utf-8')
    baseline=Path('E:/FPGA_Tools/Work/p06-pzp201-20261011c/hdl/projects/pzp201/pzp201.gen/sources_1/bd/system/ip/system_sys_ps7_0/ps7_init.c')
    candidate=ROOT/'results/p201-uart-route-20261024T024517Z/ps7_init.c'
    seq=lambda p:re.findall(r'EMIT_[A-Z]+\([^\n]*',p.read_text())
    a,b=seq(baseline),seq(candidate)
    (out/'ps7-command.diff').write_text('\n'.join(difflib.unified_diff(a,b,fromfile='baseline-init',tofile='UART-init',lineterm=''))+'\n')
    r=dict(status='reviewing_local_sources',board_operations=False,BOOT_sha256=sha(original),
           partitions=partitions,PS_init_sources=dict(baseline=str(baseline),baseline_sha256=sha(baseline),
           candidate=str(candidate),candidate_sha256=sha(candidate)),
           baseline_only_commands=sorted(set(a)-set(b)),candidate_only_commands=sorted(set(b)-set(a)),
           source_members=[])
    archive=Path('D:/FPGA natch/plutosdr-fw.tar');stat=archive.stat();before=(stat.st_size,stat.st_mtime_ns)
    print(out,flush=True)
    wanted=('drivers/tty/serial/xilinx_uartps.c','drivers/clk/zynq/clkc.c',
            'drivers/fpga/zynqpl.c','configs/zynq_pluto_defconfig','configs/zynq_pzp201_defconfig')
    with tarfile.open(archive,'r:') as tar:
        for item in tar:
            if item.isfile() and any(item.name.endswith(v) for v in wanted) and item.size<1000000:
                contents=tar.extractfile(item).read();target=out/'vendor'/item.name
                target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(contents)
                r['source_members'].append(dict(archive_member=item.name,bytes=len(contents),sha256=sha(target)))
    after=archive.stat()
    if before!=(after.st_size,after.st_mtime_ns):raise ValueError('Archive changed')
    r.update(status='collected_P64_boot_partition_init_and_vendor_source_evidence',
             archive_path=str(archive),archive_size=stat.st_size,archive_whole_SHA_rechecked_this_run=False)
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8');print(r['status'],flush=True)
if __name__=='__main__':main()
