"""Fetch the documented HLS fix only from vendor HTTPS; verify ZIP before extraction."""
from datetime import datetime, timezone
import hashlib
import io
import json
from pathlib import Path
import urllib.request
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p29-hls-patch-download-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    attempts = []
    record = dict(status='not_downloaded', documentation='https://docs.amd.com/r/en-US/76960/Solution', attempts=attempts)
    for url in ['https://docs.amd.com/api/khub/maps/DNgYzry5iDmHZl4QfHZ8SA/attachments/ZfFwXVyYLfkvyk6OMpeWbg-DNgYzry5iDmHZl4QfHZ8SA/content',
                'https://www.xilinx.com/Attachment/AR76960/y2k22_patch-1.2.zip',
                'https://download.amd.com/Attachment/AR76960/y2k22_patch-1.2.zip']:
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'}), timeout=20) as response:
                final_url = response.url
                host = urllib.parse.urlparse(final_url).hostname
                if not final_url.startswith('https://') or not (host.endswith('.amd.com') or host.endswith('.xilinx.com')):
                    raise RuntimeError('unexpected redirect host')
                data = response.read(2*1024*1024)
            with zipfile.ZipFile(io.BytesIO(data)) as z:
                names = z.namelist()
                if not any(n.endswith('automg_patch_20220104.tcl') for n in names) or not any(n.endswith('patch.py') for n in names):
                    raise RuntimeError('expected patch members not found')
                if z.testzip() is not None:
                    raise RuntimeError('ZIP integrity error')
            target = Path('E:/FPGA_Tools/Downloads/y2k22_patch-1.2.zip')
            if target.exists() and target.read_bytes() != data:
                raise RuntimeError('refusing different existing download')
            target.write_bytes(data)
            record.update(status='downloaded_verified_zip_not_executed', url=url, final_url=final_url,
                          file=str(target), sha256=hashlib.sha256(data).hexdigest(), members=names)
            attempts.append(dict(url=url, status='verified'))
            break
        except Exception as error:
            attempts.append(dict(url=url, error=str(error)))
    (out / 'report.json').write_text(json.dumps(record, indent=2) + '\n', encoding='utf-8')
    print(out)
    print(record['status'])
    for attempt in attempts:
        print(attempt)
    return 0 if record['status'].startswith('downloaded_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
