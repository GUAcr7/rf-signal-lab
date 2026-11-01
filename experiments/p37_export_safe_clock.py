"""Export the traced safe-clock bin and re-pair unchanged device descriptions.

P35 v1 schemas are transport contracts reused by the controlled trial runner;
the added P37 provenance explicitly identifies this new physical clock design.
"""
import argparse
from datetime import datetime, timezone
import hashlib, json, os, subprocess
from pathlib import Path
from p32_session import ROOT
from p35_build_ttl import GUARDS
from p37_build_safe_clock import MMCM_GUARD
from p35_restore_vendor_files import EXPECTED as FACTORY
from rfsig.bitstream_format import extract_bit_payload, validate_raw_sync

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--route-report',type=Path,required=True)
    parser.add_argument('--overlay-report',type=Path,required=True)
    args=parser.parse_args()
    route=json.loads(args.route_report.read_text('utf-8'))
    work=Path(route['work']);bd=Path(route['candidate_BD']);checkpoint=Path(route['checkpoint'])
    if route['status']!='passed_native_route_within_declared_constraints_only' or not route['originals_unchanged'] or not route['timing_claim']:
        raise RuntimeError('successful routed candidate required')
    if sha(checkpoint)!=route['checkpoint_sha256'] or sha(bd)!=route['candidate_BD_sha256']:raise RuntimeError('route inputs changed')
    prep_path=Path(route['prepare_report']);prep=json.loads(prep_path.read_text('utf-8'))
    if sha(prep_path)!=route['prepare_report_sha256'] or not prep['connections_and_addresses_unchanged']:
        raise RuntimeError('unverified safe clock topology')
    drp=work/'project/combined.gen/sources_1/bd/system/ip/system_clk_wiz_0_0/system_clk_wiz_0_0_clk_wiz_drp.vhd'
    drp_text=drp.read_text('utf-8')
    import re
    for index,value in [(0,'05F41002'),(2,'00000019')]:
        if not re.search(r'ram_clk_config\('+str(index)+r'\)\s*<=\s*X"'+value+r'"',drp_text,re.I):
            raise RuntimeError('generated DRP reset shadow differs from safe primitive')
    old_overlay=json.loads(args.overlay_report.read_text('utf-8'))
    if old_overlay['status']!='passed_PC_only_explicit_load_overlay_not_deployed' or not all(c['passed'] for c in old_overlay['checks']):raise RuntimeError('original overlay evidence not accepted')
    if old_overlay['candidate_BD_sha256']!=prep['source_hashes_before'][str(Path(prep['source'])/'project/combined.srcs/sources_1/bd/system/system.bd')]:raise RuntimeError('overlay baseline not this source')
    for key,hashkey in [('dtbo','dtbo_sha256'),('candidate_source','candidate_source_sha256'),('paired_report','paired_report_sha256')]:
        if sha(Path(old_overlay[key]))!=old_overlay[hashkey]:raise RuntimeError('overlay source changed '+key)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p37-safe-bin-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(schema='rfsig.p35_ttl_bitstream.v1',phase='P37_safe_clock32',status='exporting',work=str(work),
        route_report=str(args.route_report.resolve()),route_report_sha256=sha(args.route_report),
        checkpoint=str(checkpoint),checkpoint_sha256=sha(checkpoint),candidate_BD=str(bd),candidate_BD_sha256=sha(bd),
        board_operations=False,native_bin_verified=False,TTL33_clock_verified=False,no_auxiliary_LVDS_PLL=False,
        safe_clock_32bit_overflow_fix=True,clock_parameters=dict(M=16.5,D=2,O=25),
        CDC_closed=False,external_IO_timing_closed=False,ADI_sync_id_patch_applied=False,
        production_release=False,factory_firmware_sha256=FACTORY,
        DRP_source=str(drp),DRP_source_sha256=sha(drp),
        DRP_reset_shadow=dict(feedback='0x05F41002',output0='0x00000019'))
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        bit=out/'rf_display_top.bit'
        tcl='set_param general.maxThreads 2\nopen_checkpoint {'+checkpoint.as_posix()+'}\n'
        tcl+='if {[get_property PART [current_design]] ne "xc7z100ffg900-2"} {error "wrong part"}\n'
        tcl+=GUARDS+MMCM_GUARD
        tcl+='set_property BITSTREAM.GENERAL.COMPRESS TRUE [current_design]\nwrite_bitstream -force -bin_file {'+bit.as_posix()+'}\nputs "P37_SAFE_NATIVE_EXPORTED"\nexit 0\n'
        script=out/'executed.tcl';script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'executed.py').write_bytes(Path(__file__).read_bytes());(out/'route-report.json').write_bytes(args.route_report.read_bytes())
        env=os.environ.copy();env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
        command=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace','-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
        with (out/'stdout.txt').open('wb') as log:
            process=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['child_pid']=process.pid;save()
            try:code=process.wait(timeout=300)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True);process.wait(timeout=30);raise
        text=(out/'stdout.txt').read_text('utf-8',errors='replace');report['exit_code']=code
        if code or 'P37_SAFE_NATIVE_EXPORTED' not in text or 'P37_SAFE_MMCM_PRIMITIVE_PASS' not in text:raise RuntimeError('export or hardware clock guard failed')
        raw=bit.with_suffix('.bin');validate_raw_sync(raw.read_bytes())
        parsed=extract_bit_payload(bit.read_bytes())
        if parsed.data!=raw.read_bytes():raise RuntimeError('native bin differs from container payload')
        report.update(status='passed_TTL33_native_bin_not_deployed',bitstream=str(raw),bitstream_sha256=sha(raw),bitstream_bytes=raw.stat().st_size,
            bit_container_sha256=sha(bit),parsed_container_payload_offset=parsed.offset,native_bin_verified=True,
            TTL33_clock_verified=True,no_auxiliary_LVDS_PLL=True,raw_equals_parsed_payload=True)
        # Device addresses, output frequency and connections are unchanged. Reuse
        # the exact compiled, no-firmware DTBO; rebind only its BD provenance.
        overlay=dict(old_overlay)
        overlay.update(phase='P37_safe_clock32',candidate_BD=str(bd),candidate_BD_sha256=sha(bd),
            derived_from=str(args.overlay_report.resolve()),derived_report_sha256=sha(args.overlay_report),
            safe_clock_prepare_report=str(prep_path),safe_clock_prepare_sha256=sha(prep_path),
            pairing_reason='Only clk_wiz primitive M/D/O override changed; requested input/output frequencies, all nodes, clocks, addresses and topology are unchanged')
        overlay['checks']=[*old_overlay['checks'],dict(name='P37 independent clock-only BD change, topology and requested frequencies preserved',passed=True)]
        destination=out/'overlay-report.json';destination.write_text(json.dumps(overlay,indent=2)+'\n',encoding='utf-8')
        report['paired_overlay_report']=str(destination);report['paired_overlay_report_sha256']=sha(destination)
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status']=='passed_TTL33_native_bin_not_deployed' else 1
if __name__=='__main__':raise SystemExit(main())
