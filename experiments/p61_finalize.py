"""Verify and archive P61 documentation/codec increment; never touches hardware."""
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote
import xml.etree.ElementTree as ET
import zipfile

ROOT = Path(__file__).resolve().parents[1]
DEST = ROOT / 'results/p61-tjc-integration-20261025T034600Z'


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if (DEST / 'report.json').exists():
        raise ValueError('Never overwrite an archived result')
    batches = ['20261025T034055Z', '20261025T034128Z', '20261025T034151Z',
               '20261025T034212Z', '20261025T034315Z']
    originals = []
    successes, failures = [], []
    for stamp in batches:
        folder = ROOT / 'results' / ('p61-tjc-docs-' + stamp)
        report = json.loads((folder / 'report.json').read_text('utf-8'))
        originals.extend(p for p in folder.iterdir() if p.is_file())
        for name, page in report['pages'].items():
            if page['status'] == 'fetched':
                if sha(folder / (name + '.html')) != page['sha256']:
                    raise ValueError('Fetched document bytes changed')
                successes.append(page['url'])
            else:
                failures.append(page)
    xml = ROOT / 'results/p61-tjc-protocol-tests-20261025.xml'
    cases = list(ET.parse(xml).getroot().iter('testcase'))
    if len(cases) != 17 or any(list(case.iter('failure')) or list(case.iter('error')) for case in cases):
        raise ValueError('All 17 offline codec checks required')
    changed = ['START-HERE.md', 'docs/WORKFLOW-NEXT-20261024.md', 'docs/display-terminal-team-task.md',
               'docs/design/tjc-source-screen-20261025.md', 'docs/experiments/EXP-P61-TJC-docs-20261025.md',
               'src/rfsig/tjc_protocol.py', 'tests/test_tjc_protocol.py',
               'experiments/p61_fetch_tjc_docs.py', 'experiments/p61_finalize.py']
    link_count = 0
    for name in changed:
        path = ROOT / name
        if path.suffix == '.md':
            for href in re.findall(r'\[[^\]]*\]\(([^)]+)\)', path.read_text('utf-8')):
                if href.startswith(('http://', 'https://', '#')):
                    continue
                if not (path.parent / unquote(href.split('#')[0])).resolve().is_file():
                    raise ValueError('Broken local document link: ' + href)
                link_count += 1
    copies = []
    for source in originals + [ROOT / name for name in changed] + [xml]:
        target = DEST / 'current-files' / source.relative_to(ROOT)
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, target)
        if sha(source) != sha(target):
            raise ValueError('Increment snapshot changed')
        copies.append(target)
    copies += [p for p in (DEST / 'before').rglob('*') if p.is_file()]
    copies.append(DEST / 'user-product-page.jpg')
    manifest = [dict(path=p.relative_to(DEST).as_posix(), bytes=p.stat().st_size, sha256=sha(p))
                for p in sorted(copies)]
    (DEST / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    archive = DEST / 'p61-increment.zip'
    with zipfile.ZipFile(archive, 'x', compression=zipfile.ZIP_DEFLATED) as z:
        for item in manifest:
            z.write(DEST / item['path'], item['path'])
        z.write(DEST / 'manifest.json', 'manifest.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:
            raise ValueError('Increment ZIP CRC mismatch')
        for item in manifest:
            if hashlib.sha256(z.read(item['path'])).hexdigest() != item['sha256']:
                raise ValueError('Increment member SHA mismatch')
    active = json.loads((ROOT / 'results/p59-active.json').read_text('utf-8'))
    if sha(ROOT / active['report']) != active['report_sha256']:
        raise ValueError('P59 hardware baseline report changed')
    result = dict(status='prepared_TJC_protocol_offline_17_checks_model_and_hardware_pending',
        board_operations=False, serial_opened=False, RF_operations=False,
        actual_screen_model=None, screen_label_seen=False, HMI_compiled=False,
        TFT_downloaded=False, wiring_approved=False, firmware_installed=False,
        successful_official_pages=len(successes), official_page_urls=successes,
        failed_fetches_preserved=failures, codec_tests=17,
        local_document_links_verified=link_count,
        hardware_baseline=active, P59_report_unchanged=True,
        manifest_sha256=sha(DEST / 'manifest.json'),
        archive=dict(path=archive.relative_to(ROOT).as_posix(), bytes=archive.stat().st_size,
                     sha256=sha(archive), CRC_and_all_member_SHA_verified=True),
        scope='P61 code/documents/vendor-page increment; retain P59 full checkpoint separately',
        next='Read actual back-label model; match supply/UART/pinout before HMI selection or wiring')
    (DEST / 'report.json').write_text(json.dumps(result, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (ROOT / 'results/p61-active.json').write_text(json.dumps(dict(status=result['status'],
        report=(DEST / 'report.json').relative_to(ROOT).as_posix(), report_sha256=sha(DEST / 'report.json'),
        actual_model_pending=True, hardware_baseline='results/p59-active.json'), indent=2) + '\n', encoding='utf-8')
    print(DEST)
    print(result['status'])
    print('official pages=' + str(len(successes)) + ', failed fetches preserved=' + str(len(failures)))


if __name__ == '__main__':
    main()
