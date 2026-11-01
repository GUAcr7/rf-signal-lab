"""Record the user-reported TJC model and fetch official matching/candidate PDFs."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p62-tjc-model-%Y%m%dT%H%M%SZ')
    out.mkdir()
    report = dict(status='user_model_recorded_official_variant_matching_in_progress',
        user_reported_text='TJC4827T143 011C P20', normalized_user_model='TJC4827T143_011C_P20',
        source='direct user answer in this conversation', user_model_received=True,
        board_operations=False, wiring_approved=False, exact_official_model_verified=False,
        models={})
    for model in ('TJC4827T143_011C_P20', 'TJC4827T143_011C_I_P20'):
        url = 'http://filedown.tjc1688.com/tjcwiki/new_datasheet/TJC_T1/' + model + '.pdf'
        item = dict(url=url)
        try:
            with urllib.request.urlopen(url, timeout=20) as response:
                raw = response.read(8 * 1024 * 1024 + 1)
                item['final_url'] = response.url
                item['HTTP_status'] = response.status
            if len(raw) > 8 * 1024 * 1024 or not raw.startswith(b'%PDF-'):
                raise ValueError('Unexpected document type/size')
            path = out / (model + '.pdf'); path.write_bytes(raw)
            item.update(status='downloaded', bytes=len(raw), sha256=hashlib.sha256(raw).hexdigest())
            from pypdf import PdfReader
            reader = PdfReader(path)
            item['pages'] = len(reader.pages)
            for number, page in enumerate(reader.pages, 1):
                text = page.extract_text() or ''
                (out / (model + '-page-' + str(number) + '.txt')).write_text(text, encoding='utf-8')
            if model == report['normalized_user_model']:
                report['exact_official_model_verified'] = True
        except Exception as error:
            item.update(status='unavailable_or_not_parsed', error=repr(error))
        report['models'][model] = item
    (out / 'executed.py').write_bytes(Path(__file__).read_bytes())
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
