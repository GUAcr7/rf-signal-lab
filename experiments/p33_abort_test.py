"""Native simulation of actual DMA endpoint abort/drain and paused-clock reset."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from p30_run import run_logged,BIN,ROOT


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p33-abort-reset-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/p33-abort-'+stamp);work.mkdir(exist_ok=False)
    prior=json.loads((ROOT/'results/p32-fifo-mm-20261020T110537Z/report.json').read_text('utf-8'))
    sources=[Path(v['path']) for v in prior['sources'] if v['name']!='tb_p32_fifo_mm.sv']
    bench=ROOT/'fpga/tb/tb_p33_dma_abort.sv';sources.append(bench)
    report=dict(status='running',work=str(work),sources=[],commands=[],board_operations=False,
        RTL_changed=False,CDC_waivers_added=False,
        scope='Actual FIFO/MM and MM/FIFO request arbiter, cooperative AXI abort/drain, tagged restart, coordinated AXI/DUT reset with sample-clock paused through release; not arbitrary one-sided live AXI reset, analog metastability, physical CDC or hardware acceptance.')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for source in sources:
        shutil.copy2(source,work/source.name);shutil.copy2(source,out/source.name)
        report['sources'].append(dict(path=str(source),name=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    save()
    try:
        commands=[('compile-rtl',[str(BIN/'xvlog.bat'),'--relax',*[p.name for p in sources if p.suffix=='.v']]),
            ('compile-bench',[str(BIN/'xvlog.bat'),'--sv',bench.name]),
            ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-timescale','1ns/1ps','tb_p33_dma_abort','-s','p33_abort']),
            ('simulate',[str(BIN/'xsim.bat'),'p33_abort','-runall'])]
        for name,command in commands:
            code=run_logged(command,work,out/(name+'.txt'),180)
            text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
            report['commands'].append(dict(name=name,exit_code=code));save()
            if code or 'ERROR:' in text or 'Fatal:' in text:raise RuntimeError(name+' failed')
        if 'P33_ABORT_RESET_TB_PASS cases=2' not in text:raise RuntimeError('completion marker absent')
        report.update(status='passed',markers=[s for s in text.splitlines() if s.startswith('P33_')])
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out);print(report['status']);print(report.get('error',''))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
