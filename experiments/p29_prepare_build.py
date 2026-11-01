"""Stage untouched vendor sources; isolate all migration/build output on E:."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def extract_selected(archive, destination, prefix=''):
    written = []
    with zipfile.ZipFile(archive) as z:
        for entry in z.infolist():
            if not entry.filename.startswith(prefix) or entry.is_dir():
                continue
            name = entry.filename[len(prefix):]
            target = (destination / name).resolve()
            if not target.is_relative_to(destination.resolve()):
                raise ValueError('archive traversal refused')
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(z.read(entry))
            written.append(dict(path=str(target), bytes=entry.file_size, sha256=digest(target)))
    return written


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    work = Path('E:/FPGA_Tools/Work') / ('p29-vendor-' + stamp)
    out = ROOT / 'results' / ('p29-build-preparation-' + stamp)
    work.mkdir(exist_ok=False)
    out.mkdir(exist_ok=False)
    if shutil.disk_usage(work).free < 5 * 1024**3:
        raise RuntimeError('insufficient E: headroom; no build staged')
    adi_archive = Path('D:/AD9361/AD9361/软件资料/Demo/hw/hdl-hdl_2018_r1.zip')
    display_archive = Path('D:/xilinx/xilinx/4-软件资料/Demo.zip')
    adi_files = extract_selected(adi_archive, work / 'adi', 'hdl-hdl_2018_r1/')
    display_prefix = 'All-Programmable-SoC-demos/axi_video_display_demo/hw/project/axi_video_display_demo_xc7z100/'
    display_files = extract_selected(display_archive, work / 'display', display_prefix)
    rf_source = Path('D:/AD9361/AD9361/软件资料/Demo/hw/src')
    shutil.copytree(rf_source, work / 'rf/src')
    vendor_rf = [dict(path=str(p), sha256=digest(p)) for p in sorted(rf_source.rglob('*')) if p.is_file()]
    bd = work / 'rf/src/scripts/system_bd.tcl'
    original = bd.read_text('utf-8-sig')
    needle = 'set scripts_vivado_version 2017.4'
    if original.count(needle) != 1:
        raise RuntimeError('vendor version guard changed; review before migration')
    migrated = original.replace(needle, 'set scripts_vivado_version 2021.1')
    bd.write_text(migrated, encoding='utf-8', newline='\n')
    (out / 'rf-system-bd-original.tcl').write_text(original, encoding='utf-8', newline='\n')
    (out / 'rf-system-bd-migration.tcl').write_text(migrated, encoding='utf-8', newline='\n')
    roots = sorted(set(re.findall(r'analog\.com:user:([^:\s]+):1\.0', original)))
    libraries = []
    active = set()
    def visit(name):
        if name in libraries:
            return
        if name in active:
            raise RuntimeError('IP dependency cycle')
        active.add(name)
        script = work / 'adi/library' / name / (name + '_ip.tcl')
        if not script.exists():
            raise FileNotFoundError(script)
        for dep in sorted(set(re.findall(r'analog\.com:user:([^:\s}]+):[0-9.]+', script.read_text('utf-8-sig')))):
            if dep != name:
                visit(dep)
        active.remove(name)
        libraries.append(name)
    for name in roots:
        visit(name)
    ips = ' '.join(libraries)
    (work / 'package_ips.tcl').write_text(f'''set_param general.maxThreads 2
puts "P29_PACKAGING_MIGRATION tool=[version -short] original_ADI_expected=2017.4.1"
set library {{{(work / 'adi/library').as_posix()}}}
foreach name {{{ips}}} {{
    puts "P29_PACKAGE_BEGIN $name"
    cd [file join $library $name]
    if {{[catch {{source ${{name}}_ip.tcl}} reason opts]}} {{
        puts "P29_PACKAGE_FAILED $name $reason"
        puts [dict get $opts -errorinfo]
        exit 10
    }}
    if {{![file exists component.xml]}} {{puts "P29_COMPONENT_MISSING $name"; exit 11}}
    puts "P29_PACKAGE_PASS $name"
    close_project
}}
puts "P29_ALL_IPS_PACKAGED"
exit 0
''', encoding='utf-8', newline='\n')
    (work / 'create_rf.tcl').write_text(f'''set_param general.maxThreads 2
cd {{{(work / 'rf/src/scripts').as_posix()}}}
set argc 2
set argv [list xc7z100ffg900-2 {{{(work / 'adi/library').as_posix()}}}]
if {{[catch {{source create_project.tcl}} reason opts]}} {{
 puts "P29_RF_CREATE_FAILED $reason"; puts [dict get $opts -errorinfo]; exit 20
}}
if {{[llength [get_bd_cells -quiet]] < 10}} {{puts "P29_RF_EMPTY_OR_INCOMPLETE_BD"; exit 21}}
validate_bd_design
save_bd_design
set_property top ad_fmcomms3_ebz_xc7z100 [current_fileset]
update_compile_order -fileset sources_1
report_ip_status -file {{{(work / 'rf-ip-status.rpt').as_posix()}}}
write_bd_tcl -force {{{(work / 'rf-migrated-bd.tcl').as_posix()}}}
puts "P29_RF_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
exit 0
''', encoding='utf-8', newline='\n')
    (work / 'inspect_display.tcl').write_text(f'''set_param general.maxThreads 2
open_project {{{(work / 'display/axi_video_display.xpr').as_posix()}}}
report_ip_status -file {{{(work / 'display-ip-status.rpt').as_posix()}}}
puts "P29_DISPLAY_IPS [get_ips -quiet]"
puts "P29_DISPLAY_PART [get_property PART [current_project]]"
puts "P29_DISPLAY_PROJECT_OPENED"
close_project
exit 0
''', encoding='utf-8', newline='\n')
    record = dict(created_utc=datetime.now(timezone.utc).isoformat(), status='staged_not_built', work=str(work),
        adi_archive=dict(path=str(adi_archive), sha256=digest(adi_archive)),
        display_archive=dict(path=str(display_archive), sha256=digest(display_archive)),
        vendor_rf_sources=vendor_rf, staged_adi=adi_files, staged_display=display_files,
        custom_ips_dependency_order=libraries,
        patch='Staged RF system_bd.tcl version declaration 2017.4 -> 2021.1 only; compatibility unverified until validation/synthesis.',
        board_operations=False, vendor_originals_modified=False)
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8', newline='\n')
    (ROOT / 'results/p29-active-build.json').write_text(json.dumps(dict(work=str(work), preparation=str(out / 'report.json')), indent=2) + '\n', encoding='utf-8')
    print(work)
    print(out)
    print(libraries)


if __name__ == '__main__':
    main()
