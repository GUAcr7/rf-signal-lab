"""Port old IP-packager path handling in the staged copy only."""
from datetime import datetime, timezone
import difflib
import hashlib
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    active = json.loads((ROOT / 'results/p29-active-build.json').read_text('utf-8'))
    work = Path(active['work'])
    path = work / 'adi/library/scripts/adi_ip.tcl'
    before = path.read_text('utf-8-sig')
    helper = '''# Migration adapter: IP packager stores relative names. Resolve by canonical
# path, reuse the existing file, and reorder by its stored name. HDL and XDC
# contents/scopes are unchanged. Fail on ambiguous matches.
proc adi_migration_file {group path} {
  set canonical [file normalize $path]
  set matches {}
  foreach candidate [ipx::get_files -of_objects $group] {
    set stored [get_property NAME $candidate]
    if {[string equal -nocase [file normalize $stored] $canonical]} {
      lappend matches $candidate
    }
  }
  if {[llength $matches] > 1} {error "Ambiguous packaged file: $path"}
  if {[llength $matches] == 1} {return [lindex $matches 0]}
  return [ipx::add_file $path $group]
}

'''
    replacements = [
        ('set f [ipx::add_file $ip_constr_files $proj_filegroup]',
         'set f [adi_migration_file $proj_filegroup $ip_constr_files]'),
        ('ipx::reorder_files -front $ip_constr_files $proj_filegroup',
         'ipx::reorder_files -front [get_property NAME $f] $proj_filegroup'),
        ('''    ipx::add_file $i_file $i_filegroup
    ipx::reorder_files -front $i_file $i_filegroup
    set_property SCOPED_TO_REF $i_module [ipx::get_files $i_file -of_objects $i_filegroup]''',
         '''    set packaged_file [adi_migration_file $i_filegroup $i_file]
    ipx::reorder_files -front [get_property NAME $packaged_file] $i_filegroup
    set_property SCOPED_TO_REF $i_module $packaged_file''')]
    after = before
    for old, new in replacements:
        if after.count(old) != 1:
            raise RuntimeError('expected unique legacy statement not found')
        after = after.replace(old, new)
    after = helper + after
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-adi-path-patch-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out / 'adi_ip.before.tcl').write_text(before, encoding='utf-8', newline='\n')
    (out / 'adi_ip.after.tcl').write_text(after, encoding='utf-8', newline='\n')
    (out / 'patch.diff').write_text(''.join(difflib.unified_diff(before.splitlines(True), after.splitlines(True), 'vendor/adi_ip.tcl', 'staged/adi_ip.tcl')), encoding='utf-8')
    path.write_text(after, encoding='utf-8', newline='\n')
    (out / 'report.json').write_text(json.dumps(dict(
        created_utc=datetime.now(timezone.utc).isoformat(), path=str(path),
        before_sha256=hashlib.sha256(before.encode()).hexdigest(),
        after_sha256=hashlib.sha256(after.encode()).hexdigest(),
        functional_hdl_changed=False, xdc_contents_changed=False,
        reason='Observed absolute/relative duplicate XDC name makes ipx::reorder_files fail in 2021.1',
        status='patched_not_yet_retested'), indent=2) + '\n', encoding='utf-8')
    print(out)


if __name__ == '__main__':
    main()
