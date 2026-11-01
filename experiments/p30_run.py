"""Retain real tool exits and sources for one offline integration stage."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT=Path(__file__).resolve().parents[1]
BIN=Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin')


def run_logged(command, cwd, path, timeout):
    with path.open('wb') as log:
        process=subprocess.Popen(command,cwd=cwd,stdout=log,stderr=subprocess.STDOUT)
        try:
            return process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Only terminate the tree belonging to this task's child process.
            subprocess.run(['taskkill','/PID',str(process.pid),'/T','/F'],capture_output=True)
            process.wait(timeout=30)
            raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage',choices=['create','gpio-test','synth','audit','implement','video-test','clock-source'])
    args=parser.parse_args()
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    work=Path(active['work'])
    out=ROOT/'results'/('p30-'+args.stage+'-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',stage=args.stage,created_utc=datetime.now(timezone.utc).isoformat(),
        work=str(work),board_operations=False,boot_files_modified=False,commands=[])
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        if args.stage=='gpio-test':
            sim=work/'gpio_sim';sim.mkdir(exist_ok=False)
            for source in [ROOT/'fpga/rtl/rf_display_gpio.v',ROOT/'fpga/tb/tb_rf_display_gpio.sv']:
                shutil.copy2(source,sim/source.name);shutil.copy2(source,out/source.name)
            commands=[('compile',[str(BIN/'xvlog.bat'),'--sv','tb_rf_display_gpio.sv','rf_display_gpio.v']),
                ('elaborate',[str(BIN/'xelab.bat'),'tb_rf_display_gpio','-s','p30_gpio']),
                ('simulate',[str(BIN/'xsim.bat'),'p30_gpio','-runall'])]
            for name,command in commands:
                code=run_logged(command,sim,out/(name+'.txt'),180)
                report['commands'].append(dict(name=name,exit_code=code));save()
                text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
                if code or 'ERROR:' in text or 'Fatal:' in text: raise RuntimeError(name+' failed')
            text=(out/'simulate.txt').read_text('utf-8',errors='replace')
            marker='P30_GPIO_TB_PASS'
        else:
            script=work/(args.stage+'.tcl')
            shutil.copy2(script,out/script.name)
            report['script_sha256']=hashlib.sha256(script.read_bytes()).hexdigest();save()
            code=run_logged([str(BIN/'vivado.bat'),'-mode','batch','-notrace','-source',str(script),
                '-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],work,out/'stdout.txt',1800)
            report['commands'].append(dict(name=args.stage,exit_code=code));save()
            text=(out/'stdout.txt').read_text('utf-8',errors='replace')
            report['errors']=[s for s in text.splitlines() if 'ERROR:' in s or '_FAILED' in s][-20:]
            if code or report['errors']: raise RuntimeError('Vivado stage failed')
            marker={'create':'P30_MERGED_BD_VALIDATED','synth':'P30_MERGED_SYNTH_PASS',
                'audit':'P30_AUDIT_PASS','implement':'P30_IMPLEMENT_COMPLETED','video-test':'P30_VIDEO_TEST_PASS',
                'clock-source':'P30_CLOCK_SOURCE_CORRECTED'}[args.stage]
        if marker not in text: raise RuntimeError('completion marker missing')
        report['markers']=[line for line in text.splitlines() if line.startswith('P30_')]
        report['status']='passed'
    except Exception as error:
        report.update(status='failed',error=repr(error))
    finally:
        report['artifacts']=[]
        top_log=work/'project/combined.runs/synth_1/runme.log'
        if args.stage=='synth' and top_log.exists():
            shutil.copy2(top_log,out/'top-runme.log')
            report['top_critical_warnings']=[line for line in top_log.read_text('utf-8',errors='replace').splitlines() if line.startswith('CRITICAL WARNING:')]
        for file in work.glob('merged-*'):
            if file.suffix in {'.rpt','.tcl','.txt'}:
                shutil.copy2(file,out/file.name)
                report['artifacts'].append(dict(name=file.name,sha256=hashlib.sha256(file.read_bytes()).hexdigest()))
        report['ended_utc']=datetime.now(timezone.utc).isoformat();save()
        print(out,flush=True)
        print(report['status'],flush=True)
        for error in report.get('errors',[]): print(error)
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':
    raise SystemExit(main())
