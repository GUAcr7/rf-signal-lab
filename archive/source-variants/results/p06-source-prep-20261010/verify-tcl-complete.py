"""Check Tcl text completeness without sourcing vendor scripts or starting Vivado."""
from pathlib import Path
import datetime as dt
import json
import subprocess

result_dir = Path(__file__).resolve().parent
baseline = result_dir.parent.parent / "fpga" / "vendor-baseline"
workspace = json.loads((baseline / "short-workspace-manifest.json").read_text(encoding="utf-8"))
root = workspace["hdl_root"].replace("\\", "/")
preflight = str(baseline / "preflight-vivado.tcl").replace("\\", "/")
tcl_script = """
proc verify_tree {directory} {
  set checked 0
  foreach path [glob -nocomplain -directory $directory *] {
    if {[file isdirectory $path]} {
      incr checked [verify_tree $path]
    } elseif {[file extension $path] in {.tcl .ttcl}} {
      set input [open $path r]
      set content [read $input]
      close $input
      if {![info complete $content]} {error "Incomplete Tcl syntax: $path"}
      incr checked
    }
  }
  return $checked
}
""" + f"""
if {{[catch {{
  set count [verify_tree {{{root}}}]
  set input [open {{{preflight}}} r]
  set content [read $input]
  close $input
  if {{![info complete $content]}} {{error "Incomplete preflight Tcl syntax"}}
}} message]}} {{puts stderr $message; exit 1}}
puts "COMPLETE_VENDOR_TCL_FILES $count"
puts "PREFLIGHT_TCL_COMPLETE 1"
exit 0
"""
completed = subprocess.run([r"C:\msys64\ucrt64\bin\tclsh.exe"], input=tcl_script, capture_output=True, text=True, check=False)
report = {"checked_at": dt.datetime.now(dt.timezone.utc).isoformat(), "hdl_root": workspace["hdl_root"], "method": "Tcl info complete on file text; vendor commands were never sourced/evaluated", "returncode": completed.returncode, "stdout": completed.stdout, "stderr": completed.stderr, "vivado_started": False, "vendor_commands_executed": False}
(result_dir / "tcl-static-check.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(completed.returncode)
