"""Export a traced native bin only from the accepted TTL33 routed checkpoint.

This creates a controlled experiment candidate, not a product timing/CDC release.
No board, boot, device tree or original project writes.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,os
from pathlib import Path
import subprocess
from p32_session import ROOT
from p35_build_ttl import GUARDS
from rfsig.bitstream_format import extract_bit_payload,validate_raw_sync

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route-report',type=Path,required=True)
    args=parser.parse_args()
    route=json.loads(args.route_report.read_text('utf-8'))
    if route['status']!='passed_native_route_within_declared_constraints_only' or not route['originals_unchanged'] or not route['timing_claim']:
        raise RuntimeError('accepted routed timing/clock report required')
    work=Path(route['work']);checkpoint=Path(route['checkpoint'])
    if sha(checkpoint)!=route['checkpoint_sha256']:raise RuntimeError('routed checkpoint changed')
    bd=work/'project/combined.srcs/sources_1/bd/system/system.bd'
    required='c373bacbfc2acc6213b60988d100f49b1a66781a009678e4a59218d99efc46f3'
    if sha(bd)!=required:raise RuntimeError('paired TTL BD changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-ttl-bin-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report=dict(schema='rfsig.p35_ttl_bitstream.v1',status='exporting',work=str(work),
        route_report=str(args.route_report.resolve()),checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint),
        candidate_BD=str(bd),candidate_BD_sha256=sha(bd),
        board_operations=False,native_bin_verified=False,TTL33_clock_verified=False,
        no_auxiliary_LVDS_PLL=False,CDC_closed=False,external_IO_timing_closed=False,
        ADI_sync_id_patch_applied=False,production_release=False,
        factory_firmware_sha256={
          'ad9361.bin':'65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a',
          'display.bin':'12566368b747728d00dda1e6774ff708b3d1a67fa37b38268bdaa8957f11286e',
          'system_wrapper.bin':'12566368b747728d00dda1e6774ff708b3d1a67fa37b38268bdaa8957f11286e'})
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        bit=out/'rf_display_top.bit'
        tcl='set_param general.maxThreads 2\nopen_checkpoint {'+checkpoint.as_posix()+'}\n'
        tcl+='if {[get_property PART [current_design]] ne "xc7z100ffg900-2"} {error "wrong part"}\n'
        tcl+=GUARDS
        tcl+='set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]\n'
        tcl+='write_bitstream -force -bin_file {'+bit.as_posix()+'}\n'
        tcl+='puts "P35_NATIVE_BIN_EXPORTED"\nexit 0\n'
        script=out/'executed.tcl';script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'exporter.py').write_bytes(Path(__file__).read_bytes())
        (out/'route-report.json').write_bytes(args.route_report.read_bytes())
        command=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch',
            '-notrace','-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
        report['command']=command;save()
        env=os.environ.copy();env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
        with (out/'stdout.txt').open('wb') as handle:
            process=subprocess.Popen(command,cwd=work,env=env,stdout=handle,stderr=subprocess.STDOUT)
            report['child_pid']=process.pid;save()
            try:code=process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
                process.wait(timeout=30);raise
        report['exit_code']=code
        text=(out/'stdout.txt').read_text('utf-8',errors='replace')
        if code or 'P35_NATIVE_BIN_EXPORTED' not in text or 'P35_TTL_CLOCK_GUARD_PASS' not in text:
            raise RuntimeError('native export or clock guard failed')
        raw=bit.with_suffix('.bin')
        validate_raw_sync(raw.read_bytes())
        payload=extract_bit_payload(bit.read_bytes())
        if payload.data!=raw.read_bytes():raise RuntimeError('native raw/container payload mismatch')
        report.update(status='passed_TTL33_native_bin_not_deployed',
            bitstream=str(raw),bitstream_sha256=sha(raw),bitstream_bytes=raw.stat().st_size,
            bit_container_sha256=sha(bit),parsed_container_payload_offset=payload.offset,
            native_bin_verified=True,TTL33_clock_verified=True,no_auxiliary_LVDS_PLL=True,
            raw_equals_parsed_payload=True)
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status']=='passed_TTL33_native_bin_not_deployed' else 1

if __name__=='__main__':raise SystemExit(main())
