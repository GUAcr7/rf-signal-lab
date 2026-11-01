"""Prepare paired PWM2/VDMA-name candidate; compile/apply on PC only."""
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


def digest(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--project-result',type=Path,required=True)
    args=parser.parse_args()
    project=json.loads(args.project_result.read_text('utf-8'))
    if project['status']!='cloned_PWM2_route_and_BD_validation_passed_not_synthesized' or not project['baseline_unchanged']:
        raise RuntimeError('matching PWM2 BD validation required')
    bd=Path(project['working_directory'])/'project/combined.srcs/sources_1/bd/system/system.bd'
    if digest(bd)!=project['candidate_bd_sha256']:raise RuntimeError('candidate BD changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-paired-overlay-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source=ROOT/'fpga/integration/rf-display-800x480.dts'
    original=source.read_bytes();text=original.decode('utf-8')
    replacements={
        'clock-names = "s_axi_lite_aclk", "m_axi_mm2s_aclk", "m_axi_mm2s_aclk", "m_axi_s2mm_aclk", "m_axi_s2mm_aclk";':
        'clock-names = "s_axi_lite_aclk", "m_axi_mm2s_aclk", "m_axis_mm2s_aclk", "m_axi_s2mm_aclk", "s_axis_s2mm_aclk";',
        'pwms = <&display_ttc0_pwm>, <0x00 0xc350>;':'pwms = <&display_ttc0_pwm>, <0x02 0xc350>;',
        'firmware-name = "rf-display-p31.bin";':'firmware-name = "rf-display-p32.bin";',
    }
    for old,new in replacements.items():
        if text.count(old)!=1:raise RuntimeError('expected source not unique '+old)
        text=text.replace(old,new)
    text='// P32: requires paired TTC0_WAVE2_OUT backlight net. Offline candidate.\n'+text
    candidate=out/'rf-display-p32-pwm2.dts';candidate.write_text(text,encoding='utf-8',newline='\n')
    (out/'p31-source.before.dts').write_bytes(original)
    tools=Path(json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'))['bin'])
    report=dict(status='building',checks=[],stages=[],project_result=str(args.project_result.resolve()),
        candidate_project=project['working_directory'],candidate_BD_sha256=digest(bd),
        board_operations=False,bitstream_generated=False,merged_hardware_verified=False,
        physical_backlight_and_timer_validation=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def check(name,ok):
        report['checks'].append(dict(name=name,passed=bool(ok)))
        if not ok:raise RuntimeError(name)
    try:
        blob=out/'rf-display-p32-pwm2.dtbo'
        command=[str(tools/'dtc.exe'),'-@','-I','dts','-O','dtb','-o',str(blob),str(candidate)]
        result=subprocess.run(command,capture_output=True,timeout=25)
        (out/'dtc.stdout').write_bytes(result.stdout);(out/'dtc.stderr').write_bytes(result.stderr)
        report['stages'].append(dict(command=command,exit_code=result.returncode))
        check('DTC compilation succeeded',result.returncode==0)
        base_data=(ROOT/'results/p31-board-contract-20261019T135528Z/boot-base.dtb').read_bytes()
        payload=blob.read_bytes()
        library=ctypes.CDLL(str(tools/'libfdt-1.dll'))
        library.fdt_open_into.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
        library.fdt_overlay_apply.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        library.fdt_check_full.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        library.fdt_pack.argtypes=[ctypes.c_void_p]
        base=ctypes.create_string_buffer(len(base_data)+len(payload)*2+65536)
        src=ctypes.create_string_buffer(base_data);overlay=ctypes.create_string_buffer(payload)
        check('base FDT valid',library.fdt_check_full(src,len(base_data))==0)
        check('overlay FDT valid',library.fdt_check_full(overlay,len(payload))==0)
        check('base FDT enlarged',library.fdt_open_into(src,base,len(base))==0)
        check('native libfdt PC apply',library.fdt_overlay_apply(base,overlay)==0)
        check('native libfdt pack',library.fdt_pack(base)==0)
        size=struct.unpack_from('>I',base.raw,4)[0]
        check('combined FDT valid',library.fdt_check_full(base,size)==0)
        combined=out/'offline-combined-p32.dtb';combined.write_bytes(base.raw[:size])
        props=properties(combined.read_bytes())
        before=properties((ROOT/'results/p31-overlay-20261019T141549Z/offline-combined-base.dtb').read_bytes())
        strings=lambda path:props[path]['strings']
        cells=lambda path:props[path]['u32']
        check('VDMA five distinct driver names',strings('/amba/dma@43000000/clock-names')==[
            's_axi_lite_aclk','m_axi_mm2s_aclk','m_axis_mm2s_aclk','m_axi_s2mm_aclk','s_axis_s2mm_aclk'])
        check('VDMA clock providers unchanged',props['/amba/dma@43000000/clocks']['hex']==before['/amba/dma@43000000/clocks']['hex'])
        check('backlight requests counter2',cells('/backlight/pwms')[1:]==[2,50000])
        check('PWM remains correct TTC0 block',cells('/amba/ttc_pwm@0/reg')==[0xf8001000,4096])
        check('firmware unique P32 name',strings('/fpga-full/firmware-name')==['rf-display-p32.bin'])
        protected=0
        for key,value in before.items():
            if key.startswith('/amba/spi@e0007000/ad9361-phy@0/') and key.split('/')[-1].startswith('adi,'):
                protected+=1;check('unchanged '+key,props[key]['hex']==value['hex'])
        for k in ['/amba/dma@7c400000/reg','/amba/dma@7c420000/reg','/amba/clk_wiz@43c10000/clocks']:
            check('P31 contract preserved '+k,props[k]['hex']==before[k]['hex'])
        destination=ROOT/'fpga/integration/rf-display-p32-pwm2.dts'
        if destination.exists():raise RuntimeError('candidate source already exists; do not overwrite silently')
        destination.write_bytes(candidate.read_bytes())
        report.update(status='paired_PWM2_VDMA_names_compiled_and_native_PC_applied_not_deployed',
            protected_AD9361_properties=protected,source=str(destination),dtbo=str(blob),
            source_sha256=digest(destination),dtbo_sha256=digest(blob),
            limitations=['PWM driver still exposes other two channels; do not export/configure them',
                'Vendor PWM remove disables ALL channels; no live overlay/PWM driver unload',
                'Requires new synthesis/route and CDC/external timing review',
                'Must verify timer behavior and physical backlight on matching merged hardware'])
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_not_deployed') else 1


if __name__=='__main__':raise SystemExit(main())
