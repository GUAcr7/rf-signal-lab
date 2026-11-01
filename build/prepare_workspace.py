"""Materialize the original project paths without executing historical scripts."""
import argparse, json, shutil
from pathlib import Path, PurePosixPath

ROOT=Path(__file__).resolve().parents[1]

def main():
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument('--output',type=Path,required=True)
    a=ap.parse_args();dest=a.output.resolve()
    if dest.exists():raise SystemExit('Output must not already exist; no files were replaced.')
    dest.mkdir(parents=True)
    data=json.loads((ROOT/'source_manifest.json').read_text(encoding='utf8'))
    used=set();count=0
    for row in data['files']:
        original=row.get('original_project_path')
        if not original or row['path'].startswith('archive/revisions/'):continue
        p=PurePosixPath(original)
        if p.is_absolute() or '..' in p.parts or ':' in original:raise ValueError('Unsafe source map')
        if original in used:continue
        used.add(original)
        source=(ROOT/row['path']).resolve();target=dest.joinpath(*p.parts).resolve()
        if not source.is_relative_to(ROOT) or not target.is_relative_to(dest):raise ValueError('Path escaped root')
        target.parent.mkdir(parents=True,exist_ok=True);shutil.copyfile(source,target);count+=1
    print(json.dumps({'files':count,'workspace':str(dest),'hardware_accessed':False,
        'note':'Original filename case restored; publication redactions remain. Vendor inputs and per-machine paths still need the preflight/reproduction review.'},ensure_ascii=False))

if __name__=='__main__':main()
