"""Bounded digital test of actual RX FIFO/MM and TX MM/FIFO endpoint topology."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
from p30_run import run_logged,BIN,ROOT


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p32-fifo-mm-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/p32-fifo-mm-'+stamp);work.mkdir(exist_ok=False)
    library=Path('E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library')
    sources=[library/name for name in ['util_axis_fifo/util_axis_fifo.v','util_axis_fifo/address_gray_pipelined.v',
        'util_cdc/sync_bits.v','util_cdc/sync_gray.v','common/ad_mem.v','util_axis_resize/util_axis_resize.v']]
    sources += [library/'axi_dmac'/name for name in ['request_arb.v','request_generator.v','data_mover.v',
        'response_generator.v','splitter.v','src_fifo_inf.v','dest_fifo_inf.v','src_axi_mm.v',
        'dest_axi_mm.v','address_generator.v','response_handler.v','axi_register_slice.v']]
    bench=ROOT/'fpga/tb/tb_p32_fifo_mm.sv';sources.append(bench)
    headers=[library/'axi_dmac/inc_id.h',library/'axi_dmac/resp.h']
    report=dict(status='running',work=str(work),sources=[],commands=[],board_operations=False,
        scope='Unchanged ADI request arbiter with actual RX FIFO/MM and TX MM/FIFO endpoint types, 64-bit data, 128B bursts, FIFO_SIZE=4, actual async and TX destination-slice parameters; conservative FIFO rates, drain and re-enable. No abrupt abort, independent reset, DDR/HP throughput, analog metastability or CDC waiver proof.')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for source in sources+headers:
        shutil.copy2(source,work/source.name);shutil.copy2(source,out/source.name)
        report['sources'].append(dict(path=str(source),name=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    save()
    try:
        commands=[('compile-rtl',[str(BIN/'xvlog.bat'),'--relax',*[p.name for p in sources if p.suffix=='.v']]),
            ('compile-bench',[str(BIN/'xvlog.bat'),'--sv',bench.name]),
            ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-timescale','1ns/1ps','tb_p32_fifo_mm','-s','p32_fifo_mm']),
            ('simulate',[str(BIN/'xsim.bat'),'p32_fifo_mm','-runall'])]
        for name,command in commands:
            code=run_logged(command,work,out/(name+'.txt'),180)
            text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
            report['commands'].append(dict(name=name,exit_code=code));save()
            if code or 'ERROR:' in text or 'Fatal:' in text:raise RuntimeError(name+' failed')
        if 'P32_FIFO_MM_TB_PASS cases=2' not in text:raise RuntimeError('completion marker absent')
        report.update(status='passed',markers=[s for s in text.splitlines() if s.startswith('P32_')])
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:save();print(out);print(report['status']);print(report.get('error',''))
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
