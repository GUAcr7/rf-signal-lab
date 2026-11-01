"""Pair the TTL33 candidate with its unique firmware name; native PC FDT only."""
import argparse
import ctypes
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess
from p30_display_profile import properties
from p32_session import ROOT

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def apply(library,base_data,payload):
    source=ctypes.create_string_buffer(base_data)
    overlay=ctypes.create_string_buffer(payload)
    base=ctypes.create_string_buffer(len(base_data)+len(payload)*2+65536)
    if library.fdt_check_full(source,len(base_data)) or library.fdt_check_full(overlay,len(payload)):
        raise RuntimeError('invalid input FDT')
    if library.fdt_open_into(source,base,len(base)) or library.fdt_overlay_apply(base,overlay) or library.fdt_pack(base):
        raise RuntimeError('native FDT application failed')
    size=struct.unpack_from('>I',base.raw,4)[0]
    if library.fdt_check_full(base,size):raise RuntimeError('invalid combined FDT')
    return base.raw[:size]

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-result',type=Path,required=True)
    args=parser.parse_args()
    project=json.loads(args.project_result.read_text('utf-8'))
    if project['status']!='passed_BD_and_source_contract_not_synthesized' or not project['source_unchanged']:
        raise RuntimeError('successful TTL candidate required')
    work=Path(project['work'])
    bd=work/'project/combined.srcs/sources_1/bd/system/system.bd'
    if sha(bd)!=project['candidate_hashes'][str(bd.relative_to(work))]:
        raise RuntimeError('candidate BD changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p33-paired-overlay-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    old=ROOT/'fpga/integration/rf-display-p32-pwm2.dts'
    source=out/'rf-display-p33-ttl33.dts'
    text=old.read_text('utf-8')
    if text.count('firmware-name = "rf-display-p32.bin";')!=1:
        raise RuntimeError('unexpected prior firmware contract')
    text=text.replace('firmware-name = "rf-display-p32.bin";','firmware-name = "rf-display-p33.bin";')
    text='// P33: TTL-only initial 33MHz, PWM2. No bitstream or deployment yet.\n'+text
    source.write_text(text,encoding='utf-8',newline='\n')
    tools=Path(json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'))['bin'])
    report=dict(status='building',checks=[],stages=[],project_result=str(args.project_result.resolve()),
        candidate_project=str(work),candidate_BD_sha256=sha(bd),board_operations=False,
        bitstream_generated=False,merged_hardware_verified=False,prior_dts_sha256=sha(old))
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def check(name,ok):
        report['checks'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise RuntimeError(name)
    try:
        library=ctypes.CDLL(str(tools/'libfdt-1.dll'))
        library.fdt_open_into.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
        library.fdt_overlay_apply.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        library.fdt_check_full.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        library.fdt_pack.argtypes=[ctypes.c_void_p]
        combined=[]
        base_data=(ROOT/'results/p31-board-contract-20261019T135528Z/boot-base.dtb').read_bytes()
        for label,path in [('prior',old),('p33',source)]:
            blob=out/(label+'.dtbo')
            command=[str(tools/'dtc.exe'),'-@','-I','dts','-O','dtb','-o',str(blob),str(path)]
            result=subprocess.run(command,capture_output=True,timeout=25)
            (out/(label+'-dtc.stdout')).write_bytes(result.stdout)
            (out/(label+'-dtc.stderr')).write_bytes(result.stderr)
            report['stages'].append(dict(command=command,exit_code=result.returncode))
            check(label+' native DTC compile',result.returncode==0)
            data=apply(library,base_data,blob.read_bytes())
            (out/(label+'-combined.dtb')).write_bytes(data)
            combined.append(properties(data))
        before,after=combined
        changed=[k for k in set(before)|set(after) if before.get(k)!=after.get(k)]
        check('only combined property change is unique firmware name',changed==['/fpga-full/firmware-name'])
        check('P33 firmware name',after['/fpga-full/firmware-name']['strings']==['rf-display-p33.bin'])
        check('PWM2 retained',after['/backlight/pwms']['u32'][1:]==[2,50000])
        check('no LVDS ports in BD',not any('lvds' in k for k in json.loads(bd.read_text('utf-8'))['design']['ports']))
        destination=ROOT/'fpga/integration/rf-display-p33-ttl33.dts'
        if destination.exists():raise RuntimeError('do not overwrite prior P33 candidate')
        destination.write_bytes(source.read_bytes())
        report.update(status='passed_native_PC_FDT_pair_not_deployed',changed_properties=changed,
            source=str(destination),source_sha256=sha(destination),dtbo=str(out/'p33.dtbo'),
            dtbo_sha256=sha(out/'p33.dtbo'),preserved_properties=len(before)-1)
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        save();print(out);print(report['status'])
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
