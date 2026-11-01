"""Build a PC-only TTL33 overlay for explicitly preconfigured FPGA fabric.

Delete the firmware-only FPGA-region fragment from the P33 paired source.
The supplied 4.9 FPGA-region notifier rejects an empty region overlay unless
external-fpga-config is present. Removing that fragment avoids a second FPGA
configuration request and retains the RF/display device descriptions unchanged.
No serial, board, boot-file, or FPGA operations occur here.
"""
import argparse
import ctypes
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import struct
import subprocess

from p30_display_profile import properties
from p31_build_overlay import remove_node

ROOT=Path(__file__).resolve().parents[1]

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def native_apply(library, base_data, payload):
    original=ctypes.create_string_buffer(base_data)
    overlay=ctypes.create_string_buffer(payload)
    base=ctypes.create_string_buffer(len(base_data)+len(payload)*2+65536)
    calls=[]
    def call(name,*args):
        rc=getattr(library,name)(*args)
        calls.append(dict(function=name,exit_code=rc))
        if rc:
            raise RuntimeError(name+' failed '+str(rc))
    call('fdt_check_full',original,len(base_data))
    call('fdt_check_full',overlay,len(payload))
    call('fdt_open_into',original,base,len(base))
    call('fdt_overlay_apply',base,overlay)
    call('fdt_pack',base)
    size=struct.unpack_from('>I',base.raw,4)[0]
    call('fdt_check_full',base,size)
    return base.raw[:size],calls

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--paired-report',type=Path,default=ROOT/'results/p33-paired-overlay-20261020T114656Z/report.json')
    args=parser.parse_args()
    paired=json.loads(args.paired_report.read_text('utf-8'))
    if paired['status']!='passed_native_PC_FDT_pair_not_deployed':
        raise RuntimeError('accepted P33 TTL33 pairing required')
    source=Path(paired['source'])
    bd=Path(paired['candidate_project'])/'project/combined.srcs/sources_1/bd/system/system.bd'
    if sha(source)!=paired['source_sha256'] or sha(bd)!=paired['candidate_BD_sha256']:
        raise RuntimeError('paired source or BD changed')
    destination=ROOT/'fpga/integration/rf-display-p35-explicit.dts'
    if destination.exists():
        raise RuntimeError('refusing to overwrite existing P35 candidate')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-explicit-overlay-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report=dict(schema='rfsig.p35_explicit_overlay.v1',status='preparing',
        board_operations=False,FPGA_operations=False,boot_files_modified=False,
        exact_hang_cause_proven=False,hardware_verified=False,
        paired_report=str(args.paired_report.resolve()),paired_report_sha256=sha(args.paired_report),
        source=str(source),source_sha256=sha(source),candidate_BD=str(bd),candidate_BD_sha256=sha(bd),
        checks=[],stages=[],limitations=[
            'Requires explicit matching raw-bin programming before any overlay device probe',
            'Only valid for the paired TTL33/PWM2 merged fabric, not the factory fabric',
            'No hot overlay removal or FPGA reconfiguration underneath drivers',
            'PC FDT application proves structure only, not kernel or parallel RF/display behavior'])
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def check(name,passed):
        report['checks'].append(dict(name=name,passed=bool(passed)))
        if not passed:
            raise RuntimeError(name)
    save()
    (out/'executed-script.py').write_bytes(Path(__file__).read_bytes())
    (out/'source-p33.dts').write_bytes(source.read_bytes())
    (out/'paired-report.json').write_bytes(args.paired_report.read_bytes())
    try:
        text=source.read_text('utf-8')
        check('unique firmware fragment',text.count('target = <&fpga_full>;')==1 and
            text.count('firmware-name = "rf-display-p33.bin";')==1)
        removed=remove_node(text,'fragment@3')
        check('remove complete FPGA-region fragment',removed!=text and 'target = <&fpga_full>;' not in removed)
        check('no implicit FPGA firmware request', 'firmware-name' not in removed)
        removed=removed[removed.index('/dts-v1/;'):]
        candidate=out/'rf-display-p35-explicit.dts'
        candidate.write_text('// P35: TTL33/PWM2 device overlay; FPGA must already be configured.\n'
            '// No firmware-name or FPGA-region fragment: explicit load is required.\n'
            '// PC-only candidate; no root-cause or parallel-hardware acceptance.\n'+removed,
            encoding='utf-8',newline='\n')
        tools=Path(json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'))['bin'])
        library=ctypes.CDLL(str(tools/'libfdt-1.dll'))
        library.fdt_open_into.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
        library.fdt_overlay_apply.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        library.fdt_check_full.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        library.fdt_pack.argtypes=[ctypes.c_void_p]
        base=ROOT/'results/p31-board-contract-20261019T135528Z/boot-base.dtb'
        report['base_dtb_sha256']=sha(base)
        report['native_library_sha256']=sha(tools/'libfdt-1.dll')
        combined=[]
        for label,path in [('p33',source),('p35',candidate)]:
            blob=out/(label+'.dtbo')
            argv=[str(tools/'dtc.exe'),'-@','-I','dts','-O','dtb','-o',str(blob),str(path)]
            result=subprocess.run(argv,capture_output=True,timeout=30)
            (out/(label+'-dtc.stdout')).write_bytes(result.stdout)
            (out/(label+'-dtc.stderr')).write_bytes(result.stderr)
            report['stages'].append(dict(label=label,argv=argv,exit_code=result.returncode))
            check(label+' compile success',result.returncode==0)
            payload,calls=native_apply(library,base.read_bytes(),blob.read_bytes())
            report['stages'].append(dict(label=label,native_calls=calls))
            (out/(label+'-combined.dtb')).write_bytes(payload)
            combined.append(properties(payload))
        before,after=combined
        # Bytewise property equality also checks all final phandle values and
        # cross-references. No broad exclusion hides a changed data property.
        changed=sorted(k for k in set(before)|set(after)
            if before.get(k,{}).get('hex')!=after.get(k,{}).get('hex'))
        report['changed_properties']=changed
        check('only final-tree change is firmware-name deletion',changed==['/fpga-full/firmware-name'])
        check('firmware-name absent after apply','/fpga-full/firmware-name' not in after)
        protected=[k for k in before if k.startswith('/amba/spi@e0007000/ad9361-phy@0/adi,')]
        check('89 AD9361 initialization properties unchanged',len(protected)==89 and
            all(before[k]['hex']==after[k]['hex'] for k in protected))
        clock=after['/amba/slcr@f8000000/clkc@100/phandle']['u32'][0]
        for address in ['7c400000','7c420000']:
            check(address+' 4KiB resource',after['/amba/dma@'+address+'/reg']['u32']==[int(address,16),4096])
            check(address+' FCLK0',after['/amba/dma@'+address+'/clocks']['u32']==[clock,15])
        check('ClockWiz input100/AXI200 provider',after['/amba/clk_wiz@43c10000/clocks']['u32']==[clock,15,clock,16])
        check('VDMA all five FCLK1',after['/amba/dma@43000000/clocks']['u32']==[clock,16]*5)
        check('PWM2 50us retained',after['/backlight/pwms']['u32'][1:]==[2,50000])
        check('pixel33000kHz and 800x480 preserved',all(after['/amba/lcd_800x480/'+k]['u32']==[v]
            for k,v in [('clock-frequency',33000),('hactive',800),('vactive',480),('htotal',1056),('vtotal',528)]))
        check('no source/BD mutation',sha(source)==report['source_sha256'] and sha(bd)==report['candidate_BD_sha256'])
        destination.write_bytes(candidate.read_bytes())
        report.update(status='passed_PC_only_explicit_load_overlay_not_deployed',
            candidate_source=str(destination),candidate_source_sha256=sha(destination),
            dtbo=str(out/'p35.dtbo'),dtbo_sha256=sha(out/'p35.dtbo'),
            protected_AD9361_properties=len(protected),preserved_final_properties=len(after),
            deleted_fragment='fragment@3 (FPGA region with only cells + firmware-name)',
            loading_contract='fresh boot hold, verify no drivers/overlays, explicitly load paired raw bin, verify operating, then apply device overlay once')
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        save()
        print(out,flush=True)
        print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':
    raise SystemExit(main())
