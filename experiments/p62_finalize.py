"""Freeze the user model, reviewed reference PDF and documentation increment."""
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / 'results/p62-model-record-20261025T041700Z'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (OUT / 'report.json').exists():
        raise ValueError('Do not overwrite a saved record')
    config_path = ROOT / 'configs/tjc-source-screen.json'
    config = json.loads(config_path.read_text('utf-8'))
    pdf = ROOT / config['official_reference_pdf']
    if sha(pdf) != config['official_reference_pdf_sha256']:
        raise ValueError('Reference PDF changed')
    if config['user_reported_model'] != 'TJC4827T143_011C_P20' or config['official_reference_is_identical_to_user_hardware'] is not None:
        raise ValueError('User model or unresolved variant boundary changed')
    selected = ['configs/tjc-source-screen.json', 'START-HERE.md', 'docs/WORKFLOW-NEXT-20261024.md',
                'docs/design/tjc-source-screen-20261025.md', 'docs/experiments/EXP-P62-TJC-model-20261025.md',
                'experiments/p62_tjc_model_check.py', 'experiments/p62_finalize.py']
    for directory in ('p62-tjc-model-20261025T041313Z', 'p62-tjc-model-20261025T041354Z',
                      'p62-tjc-model-20261025T041434Z', 'p61-tjc-docs-20261025T041153Z'):
        selected += [p.relative_to(ROOT).as_posix() for p in (ROOT / 'results' / directory).iterdir() if p.is_file()]
    links = 0
    for name in selected:
        source = ROOT / name
        if source.suffix == '.md':
            for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', source.read_text('utf-8')):
                if href.startswith(('http:', 'https:', '#')):
                    continue
                if not (source.parent / href).resolve().is_file():
                    raise ValueError('Broken document link: ' + href)
                links += 1
        target = OUT / 'current-files' / name
        target.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(source, target)
        if sha(target) != sha(source):
            raise ValueError('Snapshot mismatch')
    files = [p for folder in ('before', 'current-files', 'reviewed-pages') for p in (OUT / folder).rglob('*') if p.is_file()]
    manifest = [dict(path=p.relative_to(OUT).as_posix(), bytes=p.stat().st_size, sha256=sha(p)) for p in sorted(files)]
    (OUT / 'manifest.json').write_text(json.dumps(manifest, indent=2) + '\n', encoding='utf-8')
    archive = OUT / 'p62-model-increment.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for item in manifest:
            z.write(OUT / item['path'], item['path'])
        z.write(OUT / 'manifest.json', 'manifest.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip():
            raise ValueError('ZIP CRC failed')
        for item in manifest:
            if hashlib.sha256(z.read(item['path'])).hexdigest() != item['sha256']:
                raise ValueError('Member SHA failed')
    report = dict(status='recorded_user_model_reference_specs_reviewed_exact_variant_pending',
        user_reported_model=config['user_reported_model'], user_model_received=True,
        official_reference_model=config['official_reference_model'], exact_variant_equivalence_confirmed=False,
        reference_PDF=config['official_reference_pdf'], reference_PDF_sha256=sha(pdf),
        reference_physical_pages_visually_reviewed=[8, 9, 12],
        actual_wiring_approved=False, board_operations=False, UART_opened=False,
        HMI_model_selected=False, HMI_or_TFT_downloaded=False,
        local_links_verified=links, config_sha256=sha(config_path),
        archive=dict(path=archive.relative_to(ROOT).as_posix(), sha256=sha(archive),
                     all_member_SHA_and_CRC_verified=True),
        hardware_baseline='results/p59-active.json',
        next='Proceed with software control/menu preparation; close actual interface/version match before wiring.')
    (OUT / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'results/p62-active.json').write_text(json.dumps(dict(status=report['status'],
        report=(OUT / 'report.json').relative_to(ROOT).as_posix(), report_sha256=sha(OUT / 'report.json'),
        user_reported_model=config['user_reported_model'], user_model_received=True,
        exact_variant_pending=True, hardware_baseline='results/p59-active.json'), indent=2) + '\n', encoding='utf-8')
    print(OUT)
    print(report['status'])
    print('Increment ZIP CRC and all member SHA passed')


if __name__ == '__main__':
    main()
