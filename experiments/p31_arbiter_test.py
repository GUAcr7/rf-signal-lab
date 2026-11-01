"""Native simulation of the actual ADI DMA request/EOT arbitration RTL."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from p30_run import run_logged,BIN,ROOT


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p31-arbiter-test-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/p31-arb-'+stamp);work.mkdir(exist_ok=False)
    library=Path('E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library')
    sources=[library/name for name in ['util_axis_fifo/util_axis_fifo.v','util_axis_fifo/address_gray_pipelined.v',
        'util_cdc/sync_bits.v','util_cdc/sync_gray.v','common/ad_mem.v','util_axis_resize/util_axis_resize.v']]
    # This fixture instantiates AXIS/AXIS, not the memory-mapped adapters. Do
    # not compile unrelated adapter files and imply those endpoints were tested.
    sources.extend(library/'axi_dmac'/name for name in ['request_arb.v','request_generator.v','data_mover.v',
        'response_generator.v','splitter.v','src_axi_stream.v','dest_axi_stream.v','axi_register_slice.v'])
    sources.append(ROOT/'fpga/tb/tb_adi_dmac_arb.sv')
    headers=[library/'axi_dmac/inc_id.h',library/'axi_dmac/resp.h']
    report=dict(status='running',work=str(work),sources=[],commands=[],board_operations=False,
        scope='Digital dmac_request_arb with ASYNC=1 and AXIS/AXIS endpoints, request-ID wrap and EOT; not exact FIFO/MM endpoint or metastability/hardware acceptance; no CDC waiver')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    for source in sources+headers:
        shutil.copy2(source,work/source.name);shutil.copy2(source,out/source.name)
        report['sources'].append(dict(path=str(source),name=source.name,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    save()
    try:
        # Preserve the vendor Verilog language mode; the bench alone needs SV.
        commands=[('compile-rtl',[str(BIN/'xvlog.bat'),'--relax',*[p.name for p in sources if p.suffix=='.v']]),
            ('compile-bench',[str(BIN/'xvlog.bat'),'--sv','tb_adi_dmac_arb.sv']),
            ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-timescale','1ns/1ps','tb_adi_dmac_arb','-s','p31_arb']),
            ('simulate',[str(BIN/'xsim.bat'),'p31_arb','-runall'])]
        for name,command in commands:
            code=run_logged(command,work,out/(name+'.txt'),180)
            text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
            report['commands'].append(dict(name=name,exit_code=code));save()
            if code or 'ERROR:' in text or 'Fatal:' in text:raise RuntimeError(name+' failed')
        if 'P31_ARBITER_TB_PASS cases=2' not in text:raise RuntimeError('completion marker absent')
        report.update(status='passed',markers=[line for line in text.splitlines() if line.startswith('P31_')])
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:save()
    print(out);print(report['status'])
    if 'error' in report:print(report['error'])
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
