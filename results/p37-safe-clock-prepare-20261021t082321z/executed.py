"""Independent TTL33 copy: avoid ARM32 fixed-factor clock-rate overflow.

Uses the installed Clocking Wizard OVERRIDE_MMCM API. No board operations.
The original P35 project and its evidence are never edited.
"""
from datetime import datetime, timezone
import hashlib, json, os, re, shutil, subprocess
from pathlib import Path
from p32_session import ROOT

SOURCE=Path('E:/p33-ttl-114312')
BD=Path('project/combined.srcs/sources_1/bd/system/system.bd')
PIN='c373bacbfc2acc6213b60988d100f49b1a66781a009678e4a59218d99efc46f3'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    if sha(SOURCE/BD)!=PIN:raise RuntimeError('baseline BD changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p37-safe-clock-prepare-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/p37-clock-'+stamp[9:15]);work.mkdir(exist_ok=False)
    critical=[SOURCE/BD,SOURCE/'project/combined.xpr',SOURCE/'hdl/rf_display_top.v',SOURCE/'constraints/rf.xdc',SOURCE/'constraints/display.xdc']
    before={str(p):sha(p) for p in critical}
    report=dict(schema='rfsig.p37_safe_clock_prepare.v1',status='copying',source=str(SOURCE),
        work=str(work),board_operations=False,source_hashes_before=before,
        intended=dict(M=16.5,D=2,O=25,input_Hz=100000000,output_Hz=33000000,VCO_Hz=825000000),
        driver_intermediate_multiplier_Hz=1650000000,hardware_verified=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        (work/'project').mkdir()
        for name in ['hdl','constraints']:
            shutil.copytree(SOURCE/name,work/name)
        shutil.copytree(SOURCE/'project/combined.srcs',work/'project/combined.srcs')
        xpr=(SOURCE/'project/combined.xpr').read_text('utf-8')
        (work/'project/combined.xpr').write_text(xpr.replace(SOURCE.as_posix(),work.as_posix()),encoding='utf-8',newline='\n')
        tcl=f'''set_param general.maxThreads 2
open_project {{{(work/'project/combined.xpr').as_posix()}}}
if {{[get_property PART [current_project]] ne "xc7z100ffg900-2"}} {{error "wrong part"}}
open_bd_design [get_files */system.bd]
set wiz [get_bd_cells clk_wiz_0]
set_property -dict [list CONFIG.OVERRIDE_MMCM {{true}} CONFIG.MMCM_DIVCLK_DIVIDE {{2}} CONFIG.MMCM_CLKFBOUT_MULT_F {{16.500}} CONFIG.MMCM_CLKOUT0_DIVIDE_F {{25.000}}] $wiz
validate_bd_design
save_bd_design
foreach {{key expected}} {{OVERRIDE_MMCM true MMCM_DIVCLK_DIVIDE 2 MMCM_CLKFBOUT_MULT_F 16.500 MMCM_CLKOUT0_DIVIDE_F 25.000}} {{
  set actual [get_property CONFIG.$key $wiz]
  puts "P37_CONFIG $key=$actual"
  if {{$key eq "OVERRIDE_MMCM"}} {{if {{$actual ne $expected}} {{error "override not kept"}}}} else {{if {{abs($actual-$expected)>0.0001}} {{error "MMCM setting not kept"}}}}
}}
generate_target all [get_files *.bd]
write_bd_tcl -force {{{(work/'p37-safe-clock-validated.tcl').as_posix()}}}
puts "P37_SAFE_CLOCK_GENERATED"
close_project
exit 0
'''
        script=out/'executed.tcl';script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'executed.py').write_bytes(Path(__file__).read_bytes())
        command=['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace','-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')]
        env=os.environ.copy();env['XILINXD_LICENSE_FILE']='E:/FPGA_Tools/Downloads/Xilinx.lic'
        report.update(status='generating',command=command);save()
        with (out/'stdout.txt').open('wb') as log:
            proc=subprocess.Popen(command,cwd=work,env=env,stdout=log,stderr=subprocess.STDOUT)
            report['child_pid']=proc.pid;save()
            try:code=proc.wait(timeout=420)
            except subprocess.TimeoutExpired:
                subprocess.run(['taskkill','/PID',str(proc.pid),'/T','/F'],capture_output=True);proc.wait(timeout=20);raise
        text=(out/'stdout.txt').read_text('utf-8',errors='replace');report['exit_code']=code
        if code or 'P37_SAFE_CLOCK_GENERATED' not in text or re.search(r'^ERROR:',text,re.M):raise RuntimeError('native generation failed')
        old=json.loads((SOURCE/BD).read_text('utf-8'))['design'];new=json.loads((work/BD).read_text('utf-8'))['design']
        if set(old['components'])!=set(new['components']):raise RuntimeError('component set changed')
        changes=[name for name in old['components'] if old['components'][name]!=new['components'][name]]
        if changes!=['clk_wiz_0']:raise RuntimeError('unexpected component changes '+str(changes))
        for key in ['ports','nets','interface_nets','addressing']:
            if old.get(key)!=new.get(key):raise RuntimeError('unexpected connection or map change '+key)
        generated=[]
        for root in [work/'project/combined.gen',work/'project/combined.srcs']:
            if root.exists():
                generated.extend(p for p in root.rglob('*clk_wiz.v') if 'clk_wiz_0' in str(p))
        witnesses=[]
        for path in generated:
            content=path.read_text('utf-8',errors='replace')
            if 'MMCME2_ADV' not in content:continue
            for name,value in [('CLKFBOUT_MULT_F',16.5),('DIVCLK_DIVIDE',2),('CLKOUT0_DIVIDE_F',25)]:
                matches=re.findall(r'\.'+name+r'\s*\(\s*([0-9.]+)\s*\)',content)
                if not matches or any(abs(float(v)-value)>.0001 for v in matches):raise RuntimeError('generated primitive differs '+name)
            witnesses.append(dict(path=str(path),sha256=sha(path)))
        if not witnesses:raise RuntimeError('generated MMCM primitive witness missing')
        report.update(status='passed_safe_clock_BD_and_generated_primitive_not_routed',
            changed_components=changes,connections_and_addresses_unchanged=True,
            candidate_BD=str(work/BD),candidate_BD_sha256=sha(work/BD),generated_primitive=witnesses)
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        report['source_hashes_after']={str(p):sha(p) for p in critical}
        report['source_unchanged']=before==report['source_hashes_after']
        if not report['source_unchanged']:report['status']='failed_source_changed'
        save();print(out,flush=True);print(report['status'],flush=True);print(work,flush=True)
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
