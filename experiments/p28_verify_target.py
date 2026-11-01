"""Verify local device data and license checkout with an isolated toy synthesis."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p28-target-verification-' + stamp)
    work = Path('E:/FPGA_Tools/Work') / ('p28-target-' + stamp)
    out.mkdir(exist_ok=False)
    work.mkdir(exist_ok=False)
    (work / 'probe.v').write_text('module license_probe(input wire a, output wire y); assign y = a; endmodule\n', encoding='ascii')
    (work / 'probe.tcl').write_text('''set target xc7z100ffg900-2
puts "P28_TOOL [version -short]"
puts "P28_Z020_PARTS [get_parts -quiet xc7z020clg400-2]"
puts "P28_Z100_PARTS [get_parts -quiet $target]"
if {![llength [get_parts -quiet $target]]} {puts "P28_DEVICE_MISSING"; exit 3}
set_param general.maxThreads 2
create_project -in_memory -part $target
read_verilog probe.v
if {[catch {synth_design -top license_probe -part $target} reason]} {
  puts "P28_SYNTHESIS_BLOCKED $reason"
  exit 4
}
report_utilization -file probe-utilization.rpt
write_checkpoint probe-synth.dcp
puts "P28_TARGET_SYNTHESIS_PASS"
exit 0
''', encoding='ascii')
    tool = Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat')
    command = [str(tool), '-mode', 'batch', '-notrace', '-source', 'probe.tcl', '-log', 'probe.log', '-journal', 'probe.jou']
    result = subprocess.run(command, cwd=work, capture_output=True, timeout=180)
    (out / 'stdout.txt').write_bytes(result.stdout)
    (out / 'stderr.txt').write_bytes(result.stderr)
    text = (result.stdout + result.stderr).decode('utf-8', errors='replace')
    for name in ('probe.v', 'probe.tcl', 'probe.log', 'probe.jou', 'probe-utilization.rpt', 'probe-synth.dcp'):
        path = work / name
        if path.exists():
            (out / name).write_bytes(path.read_bytes())
    license_path = Path.home() / 'AppData/Roaming/XilinxLicense/Xilinx.lic'
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
        status='target_synthesis_verified' if result.returncode == 0 and 'P28_TARGET_SYNTHESIS_PASS' in text else 'blocked',
        exit_code=result.returncode, tool=str(tool), work=str(work), part='xc7z100ffg900-2',
        license_sha256=hashlib.sha256(license_path.read_bytes()).hexdigest(),
        rf_operations=False, board_programming=False, bitstream_generated=False,
        old_z020_part_visible='P28_Z020_PARTS xc7z020clg400-2' in text,
        scope='One-wire isolated tool/license check only. Does not verify the vendor RF/display design, integration, timing or resource fit.')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
    print(report['status'], result.returncode)
    print(out)


if __name__ == '__main__':
    main()
