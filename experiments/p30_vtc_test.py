"""Test actual VTC 6.2 generated model; no substitution of a behavioral DUT."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
from p30_run import run_logged

ROOT=Path(__file__).resolve().parents[1]
BIN=Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin')


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    work=Path(active['work'])
    source=work/'project/combined.gen/sources_1/bd/system/ip/system_v_tc_0_0/sim/system_v_tc_0_0.vhd'
    if not source.exists():
        source=work/'project/combined.srcs/sources_1/bd/system/ip/system_v_tc_0_0/sim/system_v_tc_0_0.vhd'
    assert source.exists(),source
    entity='system_v_tc_0_0'
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p30-vtc-test-'+stamp);out.mkdir(exist_ok=False)
    sim=work/('vtcsim-'+stamp);sim.mkdir(exist_ok=False)
    tb=ROOT/'fpga/tb/tb_vtc_runtime.sv'
    for path in [source,tb]:
        shutil.copy2(path,sim/path.name);shutil.copy2(path,out/path.name)
    report=dict(status='running',board_operations=False,source=str(source),source_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        tb_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),stages=[],scope='Actual upgraded VTC 6.2 AXI read/write and progressive 800x480 generator only; accelerated pixel clock; AXI gated after setup; no panel, clock-wizard, VDMA or TPG claim',
        primary_reference='https://docs.amd.com/r/en-US/pg016_v_tc/Register-Descriptions')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        commands=[('vhdl',[str(BIN/'xvhdl.bat'),source.name]),
            ('verilog',[str(BIN/'xvlog.bat'),'--sv',tb.name,str(BIN.parent/'data/verilog/src/glbl.v')]),
            ('elaborate',[str(BIN/'xelab.bat'),'-mt','2','-L','v_tc_v6_2_2','-L','axi_lite_ipif_v3_0_4','-L','lib_cdc_v1_0_2','tb_vtc_runtime','glbl','-s','p30_vtc']),
            ('simulate',[str(BIN/'xsim.bat'),'p30_vtc','-runall'])]
        for name,command in commands:
            code=run_logged(command,sim,out/(name+'.txt'),1200 if name=='simulate' else 180)
            text=(out/(name+'.txt')).read_text('utf-8',errors='replace')
            report['stages'].append(dict(name=name,exit_code=code));save()
            if code or 'ERROR:' in text or 'Fatal:' in text:raise RuntimeError(name+' failed')
        if 'P30_VTC_RUNTIME_TB_PASS' not in text:raise RuntimeError('completion marker absent')
        report.update(status='passed',markers=[s for s in text.splitlines() if s.startswith('P30_')])
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:save();print(out);print(report['status'])
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
