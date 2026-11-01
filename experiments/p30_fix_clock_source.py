"""Archive first routed result before correcting ClockWiz internal-clock source."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT=Path(__file__).resolve().parents[1]


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'))
    work=Path(active['work']);project=Path(active['project'])
    out=ROOT/'results'/('p30-clock-source-preparation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    artifacts=[]
    for name in ['merged-synth.dcp','merged-route.dcp']:
        source=work/name;shutil.copy2(source,out/('before-'+name))
        artifacts.append(dict(file='before-'+name,sha256=hashlib.sha256(source.read_bytes()).hexdigest()))
    for source in work.glob('merged-route-*.rpt'):shutil.copy2(source,out/('before-'+source.name))
    bd=work/'project/combined.srcs/sources_1/bd/system/system.bd'
    shutil.copy2(bd,out/'before-system.bd')
    script=f'''set_param general.maxThreads 2
cd {{{work.as_posix()}}}
open_project {{{project.as_posix()}}}
open_bd_design [get_files *.bd]
set wizard [get_bd_cells clk_wiz_0]
set before [get_property CONFIG.PRIM_SOURCE $wizard]
if {{$before ne "Single_ended_clock_capable_pin"}} {{error "unexpected baseline: $before"}}
set_property CONFIG.PRIM_SOURCE No_buffer $wizard
validate_bd_design
save_bd_design
generate_target all [get_files *.bd]
write_bd_tcl -force merged-bd.tcl
puts "P30_CLOCK_SOURCE_CORRECTED before=$before after=[get_property CONFIG.PRIM_SOURCE $wizard]"
close_project
exit 0
'''
    (work/'clock-source.tcl').write_text(script,encoding='utf-8',newline='\n')
    report=dict(status='prepared_requires_rebuild',before_artifacts=artifacts,board_operations=False,
        reason='TIMING-4 and TIMING-27: a downstream ClockWiz primary clock replaces common PS FCLK insertion delay',
        change='PRIM_SOURCE Single_ended_clock_capable_pin -> No_buffer; frequencies and MMCM ratios unchanged')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)


if __name__=='__main__':main()
