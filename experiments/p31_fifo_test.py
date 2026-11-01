"""Execute unchanged ADI async FIFOs under native XSim and archive all bytes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from p30_run import run_logged,BIN,ROOT


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p31-fifo-test-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/p31-fifo-'+stamp);work.mkdir(exist_ok=False)
    library=Path('E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library')
    sources=[library/name for name in ['util_axis_fifo/util_axis_fifo.v','util_axis_fifo/address_gray_pipelined.v',
        'util_cdc/sync_bits.v','util_cdc/sync_gray.v','common/ad_mem.v']]
    sources.append(ROOT/'fpga/tb/tb_adi_async_fifo.sv')
    report=dict(status='running',work=str(work),sources=[],commands=[],board_operations=False,
        scope='Digital FIFO functional behavior only; no analog metastability, eot_mem arbitration, target placement or hardware acceptance; no CDC waiver')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for source in sources:
        shutil.copy2(source,work/source.name);shutil.copy2(source,out/source.name)
        report['sources'].append(dict(path=str(source),name=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    save()
    try:
        commands=[('compile',[str(BIN/'xvlog.bat'),'--sv',*[p.name for p in sources]]),
            ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-timescale','1ns/1ps','tb_adi_async_fifo','-s','p31_fifo']),
            ('simulate',[str(BIN/'xsim.bat'),'p31_fifo','-runall'])]
        for name,command in commands:
            code=run_logged(command,work,out/(name+'.txt'),180)
            text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
            report['commands'].append(dict(name=name,exit_code=code));save()
            if code or 'ERROR:' in text or 'Fatal:' in text:raise RuntimeError(name+' failed')
        if 'P31_FIFO_TB_PASS cases=6' not in text:raise RuntimeError('completion marker absent')
        report.update(status='passed',markers=[line for line in text.splitlines() if line.startswith('P31_')])
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:save()
    print(out);print(report['status'])
    if 'error' in report:print(report['error'])
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
