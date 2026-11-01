"""Add the self-tested /2 clock constraint to the copied display project only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    test = sorted((ROOT/'results').glob('p29-display-clock-test-*/report.json'))[-1]
    if json.loads(test.read_text('utf-8'))['status'] != 'passed':
        raise RuntimeError('vendor divider self-check must pass first')
    active = json.loads((ROOT/'results/p29-active-build.json').read_text('utf-8'))
    project = Path(active['display_short_project'])
    work = Path(active['work'])
    source = ROOT/'fpga/constraints/display_lvds_half_clock.xdc'
    target = project.parent/'p29_lvds_half_clock.xdc'
    if target.exists():
        raise RuntimeError('constraint already staged; inspect before repeating')
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p29-clock-constraint-prepare-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    shutil.copy2(project, out/'display-project-before.xpr')
    shutil.copy2(source, target)
    shutil.copy2(source, out/source.name)
    script = fr'''set_param general.maxThreads 2
cd {{{work.as_posix()}}}
open_project {{{project.as_posix()}}}
add_files -fileset constrs_1 -norecurse {{{target.as_posix()}}}
set_property PROCESSING_ORDER LATE [get_files {{{target.as_posix()}}}]
set directory [file normalize [get_property DIRECTORY [get_runs synth_1]]]
if {{![string match -nocase {{{project.parent.as_posix()}/*}} $directory]}} {{error "run escaped copied project"}}
reset_run synth_1
launch_runs synth_1 -jobs 2
wait_on_run synth_1
if {{[get_property PROGRESS [get_runs synth_1]] ne "100%" || ![string match *Complete* [get_property STATUS [get_runs synth_1]]]}} {{exit 51}}
open_run synth_1
set src [get_pins -hier -filter {{NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/C}}]
set dst [get_pins -hier -filter {{NAME =~ */dual_pixel_24bpp_lvds_mapping_0/inst/parity_flag_reg/Q}}]
set master [get_clocks -of_objects $src]
set divided [get_clocks -of_objects $dst]
if {{[llength $master] != 1 || [llength $divided] != 1}} {{error "ambiguous clocks"}}
set in_period [get_property PERIOD $master]
set out_period [get_property PERIOD $divided]
if {{abs($out_period-2*$in_period) > 0.001}} {{error "clock is not /2"}}
puts "P29_CLOCK_PERIODS master_ns=$in_period divided_ns=$out_period"
check_timing -verbose -file display-clock-check-timing.rpt
report_timing_summary -file display-clock-timing.rpt
report_clocks -file display-clock-clocks.rpt
report_cdc -details -file display-clock-cdc.rpt
report_drc -file display-clock-drc.rpt
report_utilization -file display-clock-utilization.rpt
write_checkpoint -force display-clock-reviewed.dcp
set f [open display-clock-check-timing.rpt r]
set text [read $f]; close $f
if {{![regexp {{checking no_clock \(([0-9]+)\)}} $text ignored no_clock] || $no_clock != 0}} {{error "unclocked endpoints remain"}}
if {{![regexp {{checking unconstrained_internal_endpoints \(([0-9]+)\)}} $text ignored unconstrained] || $unconstrained != 0}} {{error "unconstrained internal endpoints remain"}}
puts "P29_DISPLAY_CLOCK_MODEL_VERIFIED no_clock=$no_clock unconstrained_internal_endpoints=$unconstrained"
close_project
exit 0
'''
    (work/'refine_display_clock.tcl').write_text(script, encoding='utf-8', newline='\n')
    (out/'report.json').write_text(json.dumps(dict(status='staged_not_yet_synthesized',
        self_check=str(test), project=str(project), constraint=str(target),
        constraint_sha256=hashlib.sha256(source.read_bytes()).hexdigest(),
        vendor_RTL_changed=False, board_operations=False), indent=2)+'\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
