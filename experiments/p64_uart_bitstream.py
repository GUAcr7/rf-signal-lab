"""Build a UART-only experimental bitstream from frozen routed DCP.

Offline artifact preparation only. Existing whole-system CDC/IO issues remain
unaccepted; this does not grant deployment or RF use and never opens hardware.
"""
from datetime import datetime,timezone
import hashlib,json,subprocess
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    parent=ROOT/'results/p201-uart-route-20261024T024517Z/report.json'
    old=json.loads(parent.read_text(encoding='utf-8'));dcp=parent.parent/'uart-routed.dcp'
    if sha(dcp)!=old['files_sha256']['uart-routed.dcp']:raise ValueError('Frozen DCP changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p64-uart-bit-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='building_offline_UART_experiment_only',board_operations=False,deployable=False,
           full_system_release_accepted=False,RF_accepted=False,parent=str(parent.relative_to(ROOT)),
           parent_sha256=sha(parent),DCP_sha256=sha(dcp))
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    script=out/'build.tcl'
    script.write_text('set_param general.maxThreads 2\nopen_checkpoint {'+dcp.as_posix()+'''}
foreach {port pin} {ext_uart_tx E17 ext_uart_rx E18} {
 if {[get_property PACKAGE_PIN [get_ports $port]] ne $pin} {error "UART wrong pad"}
 if {[get_property IOSTANDARD [get_ports $port]] ne "LVCMOS33"} {error "UART IO voltage"}
}
set errors [get_drc_violations -quiet -filter {SEVERITY == Error}]
if {[llength $errors]} {error "Existing error DRC"}
'''+ 'write_bitstream -force -bin_file {'+(out/'uart-experiment.bit').as_posix()+'}\n'
        +'puts "P64_UART_OFFLINE_BITSTREAM_DONE_NOT_RELEASE"\nclose_design\n',encoding='ascii')
    save();print(out,flush=True)
    try:
        with (out/'stdout.txt').open('wb') as f:
            p=subprocess.run(['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch','-notrace',
                '-source',str(script),'-log',str(out/'vivado.log'),'-journal',str(out/'vivado.jou')],
                cwd=out,stdout=f,stderr=subprocess.STDOUT,timeout=600)
        r['exit_code']=p.returncode
        if p.returncode or 'P64_UART_OFFLINE_BITSTREAM_DONE_NOT_RELEASE' not in (out/'stdout.txt').read_text(errors='replace'):
            raise ValueError('Bitstream generation incomplete')
        r['bitstreams']={p.name:dict(bytes=p.stat().st_size,sha256=sha(p)) for p in out.glob('uart-experiment.*')}
        if not (out/'uart-experiment.bit').is_file() or not (out/'uart-experiment.bin').is_file():raise ValueError('Missing bit/bin')
        if sha(dcp)!=r['DCP_sha256']:raise ValueError('Frozen DCP changed during build')
        r['status']='built_P64_UART_experiment_bitstream_not_deployed_or_released'
    except Exception as e:r.update(status='failed_or_incomplete_P64_bitstream',error=repr(e))
    save();print(r['status'],flush=True)
    return 0 if r['status'].startswith('built_') else 1
if __name__=='__main__':raise SystemExit(main())
