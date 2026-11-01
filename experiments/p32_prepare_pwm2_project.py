"""Clone the offline P30 sources, route backlight to free TTC0 channel2, validate BD.

No synthesis, bitstream, hardware operation, or mutation of the P30 baseline.
"""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from p32_session import ROOT


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p32-pwm2-project-'+stamp);out.mkdir(exist_ok=False)
    source=Path('E:/p30c-1019-174235')
    work=Path('E:/p32-pwm2-'+stamp[9:15]);work.mkdir(exist_ok=False)
    critical=[source/'project/combined.xpr',source/'project/combined.srcs/sources_1/bd/system/system.bd',source/'merged-route.dcp']
    before={str(p):sha(p) for p in critical}
    report=dict(status='copying',source=str(source),working_directory=str(work),baseline_hashes_before=before,
        hardware_operations=False,bitstream_generated=False,synthesis_or_route_run=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    try:
        (work/'project').mkdir()
        for name in ['hdl','constraints']:
            shutil.copytree(source/name,work/name)
        shutil.copytree(source/'project/combined.srcs',work/'project/combined.srcs')
        text=(source/'project/combined.xpr').read_text('utf-8').replace(source.as_posix(),work.as_posix())
        (work/'project/combined.xpr').write_text(text,encoding='utf-8',newline='\n')
        tcl=f'''open_project {{{(work/'project/combined.xpr').as_posix()}}}
open_bd_design [get_files */system.bd]
set old [get_bd_nets -of_objects [get_bd_ports lcd_pwm_backlight]]
set old_pins [get_bd_pins -of_objects $old]
if {{[llength $old_pins] != 1 || [get_property NAME $old_pins] ne "TTC0_WAVE0_OUT"}} {{error "unexpected old PWM net"}}
set freepin [get_bd_pins sys_ps7/TTC0_WAVE2_OUT]
if {{[llength $freepin] != 1 || [llength [get_bd_nets -quiet -of_objects $freepin]] != 0}} {{error "TTC0 channel2 unavailable"}}
disconnect_bd_net $old [get_bd_pins sys_ps7/TTC0_WAVE0_OUT]
disconnect_bd_net $old [get_bd_ports lcd_pwm_backlight]
delete_bd_objs $old
connect_bd_net -net display_backlight_ttc0_ch2 $freepin [get_bd_ports lcd_pwm_backlight]
validate_bd_design
save_bd_design
write_bd_tcl -force {{{(work/'p32-pwm2-validated.tcl').as_posix()}}}
puts "P32_PWM2_BD_VALIDATED no_synthesis_no_bitstream"
close_project
exit
'''
        script=work/'patch-pwm2.tcl';script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'executed.tcl').write_text(tcl,encoding='utf-8',newline='\n')
        command=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-source',str(script),'-log',str(work/'vivado.log'),'-journal',str(work/'vivado.jou')]
        report['command']=command;save()
        result=subprocess.run(command,cwd=work,capture_output=True,timeout=240)
        (out/'vivado.stdout').write_bytes(result.stdout);(out/'vivado.stderr').write_bytes(result.stderr)
        report['exit_code']=result.returncode
        if result.returncode or b'P32_PWM2_BD_VALIDATED' not in result.stdout:raise RuntimeError('Vivado BD validation failed')
        bdpath=work/'project/combined.srcs/sources_1/bd/system/system.bd'
        bd=json.loads(bdpath.read_text('utf-8'))['design']
        nets=bd['nets']
        endpoints=next(v['ports'] for v in nets.values() if 'lcd_pwm_backlight' in v['ports'])
        if set(endpoints)!={'sys_ps7/TTC0_WAVE2_OUT','lcd_pwm_backlight'}:raise RuntimeError('PWM2 route not saved')
        report['backlight_endpoints']=endpoints
        report['candidate_bd_sha256']=sha(bdpath)
        report['status']='cloned_PWM2_route_and_BD_validation_passed_not_synthesized'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        report['baseline_hashes_after']={str(p):sha(p) for p in critical}
        report['baseline_unchanged']=report['baseline_hashes_after']==before
        if not report['baseline_unchanged']:report['status']='failed_baseline_changed'
        save();print(out);print(report['status']);print(work)
    return 0 if report['status'].startswith('cloned_') else 1


if __name__=='__main__':raise SystemExit(main())
