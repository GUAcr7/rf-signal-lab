"""Self-check vendor divider in the native simulator; no RTL changes or board writes."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def main():
    active = json.loads((ROOT / 'results/p29-active-build.json').read_text('utf-8'))
    display = Path(active['display_short_project']).parent
    sources = list(display.rglob('dual_pixel_24bpp_lvds_mapping.v'))
    if len(sources) != 1:
        raise RuntimeError('expected unique vendor module source')
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'results' / ('p29-display-clock-test-' + stamp)
    out.mkdir(exist_ok=False)
    # Keep simulator working path short as well.
    work = Path('E:/FPGA_Tools/Work') / ('p29sim-' + stamp)
    work.mkdir(exist_ok=False)
    tb = ROOT / 'fpga/tb/tb_display_half_clock.sv'
    for source in [sources[0], tb]:
        shutil.copy2(source, work / source.name)
        shutil.copy2(source, out / source.name)
    tool = Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1')
    record = dict(status='running', board_operations=False, vendor_RTL_modified=False,
        vendor_source=str(sources[0]), vendor_sha256=hashlib.sha256(sources[0].read_bytes()).hexdigest(),
        test_sha256=hashlib.sha256(tb.read_bytes()).hexdigest(),
        scope='functional divider ratio and asynchronous reset only; no full mapping or hardware timing claim', stages=[])
    def save():
        (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    save()
    commands = [
        ('compile', [str(tool/'bin/xvlog.bat'), '--sv', 'tb_display_half_clock.sv',
                     'dual_pixel_24bpp_lvds_mapping.v', str(tool/'data/verilog/src/glbl.v')]),
        ('elaborate', [str(tool/'bin/xelab.bat'), '-L', 'unisims_ver', 'tb_display_half_clock', 'glbl', '-s', 'p29_clock_test']),
        ('simulate', [str(tool/'bin/xsim.bat'), 'p29_clock_test', '-runall'])]
    try:
        for name, command in commands:
            with (out/(name+'.txt')).open('wb') as log:
                result = subprocess.run(command, cwd=work, stdout=log, stderr=subprocess.STDOUT, timeout=180)
            text = (out/(name+'.txt')).read_text('utf-8', errors='replace')
            record['stages'].append(dict(name=name, exit_code=result.returncode))
            save()
            if result.returncode != 0 or 'ERROR:' in text or 'Fatal:' in text:
                raise RuntimeError(name + ' failed')
        text = (out/'simulate.txt').read_text('utf-8', errors='replace')
        if 'P29_DISPLAY_CLOCK_TB_PASS' not in text:
            raise RuntimeError('self-check completion missing')
        record['result'] = next(line for line in text.splitlines() if 'P29_DISPLAY_CLOCK_TB_PASS' in line)
        record['status'] = 'passed'
    except Exception as error:
        record.update(status='failed', error=repr(error))
        raise
    finally:
        save()
        print(out)


if __name__ == '__main__':
    main()
