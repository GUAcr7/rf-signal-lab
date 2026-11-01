"""Read-only check for external inputs; never programs or connects to a board."""
import argparse,json,shutil
from pathlib import Path

ap=argparse.ArgumentParser(description=__doc__)
ap.add_argument('--vivado',type=Path)
ap.add_argument('--adi-hdl',type=Path)
ap.add_argument('--display-project',type=Path)
a=ap.parse_args()
checks={
 'vivado_launcher':bool(a.vivado and a.vivado.is_file()) or bool(shutil.which('vivado') or shutil.which('vivado.bat')),
 'complete_adi_hdl':bool(a.adi_hdl and (a.adi_hdl/'library').is_dir() and (a.adi_hdl/'projects').is_dir()),
 'board_vendor_display_project':bool(a.display_project and a.display_project.is_dir()),
}
print(json.dumps({'checks':checks,'ready_for_full_hardware_rebuild':all(checks.values()),
 'hardware_accessed':False,'note':'Presence checks only. Tool version, vendor revisions, licenses, migrated exports, constraints and boot-image pairing still require verification.'},indent=2))
raise SystemExit(0 if all(checks.values()) else 2)
