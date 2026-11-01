"""Install the user-downloaded certificate without changing its signed contents."""
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p28-license-install-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source = Path('E:/FPGA_Tools/Downloads/Xilinx.lic')
    # Use the default Windows directory explicitly named by the 2021.1
    # VLM Load License screen, rather than relying on extra search paths.
    destination = Path(os.environ['APPDATA']) / 'XilinxLicense' / 'Xilinx.lic'
    report = dict(created_utc=datetime.now(timezone.utc).isoformat(),
                  source=str(source), destination=str(destination),
                  board_operations=False, system_environment_modified=False,
                  license_signature_or_checkout_verified=False)
    try:
        payload = source.read_bytes()
        text = re.sub(r'\\\r?\n\s*', ' ', payload.decode('utf-8-sig'))
        # Parse executable license directives only. Comment HOSTID text can end
        # with punctuation and is not a license binding directive.
        directives = [line for line in text.splitlines() if line.startswith('INCREMENT ')]
        features = []
        for line in directives:
            words = line.split()
            ids = re.findall(r'\bHOSTID=([^\s]+)', line)
            if ids != ['40c2ba523054']:
                raise RuntimeError('certificate binding differs from the verified board-independent PC NIC')
            if datetime.strptime(words[4], '%d-%b-%Y').date() < datetime.now(timezone.utc).date():
                raise RuntimeError('certificate expired')
            features.append(dict(feature=words[1], version_limit=words[3], expiration=words[4]))
        if not any(item['feature'] == 'Vivado_ML_Enterprise_Edition' for item in features):
            raise RuntimeError('required Enterprise feature missing')
        report.update(features=features, bound_host_id='40c2ba523054',
                      sha256=hashlib.sha256(payload).hexdigest(),
                      previous_file_existed=destination.exists())
        destination.parent.mkdir(parents=True, exist_ok=True)
        if destination.exists():
            shutil.copy2(destination, out / 'previous-Xilinx.lic')
        shutil.copy2(source, destination)
        if destination.read_bytes() != payload:
            raise RuntimeError('installed copy mismatch')
        report['status'] = 'installed_copy_verified_checkout_pending'
    except Exception as error:
        report.update(status='failed', error=str(error))
        raise
    finally:
        (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8', newline='\n')
        print(out)


if __name__ == '__main__':
    main()
