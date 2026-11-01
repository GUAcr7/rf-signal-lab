"""Normalize duplicate filesystem aliases from the first rejected ZIP build."""
from pathlib import Path
import argparse,json,zipfile,hashlib
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def write(p,v):Path(p).write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--out',type=Path,required=True);a=ap.parse_args()
    out=a.out.resolve()
    if ROOT/'results'!=out.parent or not out.name.startswith('p80-final-'):raise ValueError('Exact P80 result folder required')
    active=json.loads((ROOT/'results/p80-active.json').read_text('utf-8'))
    if (ROOT/active['report']).resolve()!=out/'report.json' or sha(out/'report.json')!=active['report_sha256']:
        raise ValueError('Current P80 report changed')
    manifest=json.loads((out/'manifest.json').read_text('utf-8'))
    for name,m in manifest['files'].items():
        if name!='experiments/p80_finalize.py' and sha(ROOT/name)!=m['sha256']:
            raise ValueError('Unexpected file mutation during repack: '+name)
    original=out/'checkpoint.zip';failed=out/'checkpoint-pack-failed.zip'
    if original.parent!=out or failed.parent!=out or failed.exists():raise ValueError('Exact checked result paths required')
    original.rename(failed)
    repair=out/'packaging-repair.json'
    write(repair,dict(reason='First ZIP validation rejected duplicate member from relative and absolute aliases of same file',
                      failed_archive=failed.name,failed_sha256=sha(failed),
                      fix='Normalize absolute resolved paths before writing members; no board or RF changes',
                      original_report_unchanged=True))
    for p in (ROOT/'experiments/p80_finalize.py',Path(__file__).resolve(),failed,repair):
        manifest['files'][p.relative_to(ROOT).as_posix()]=dict(bytes=p.stat().st_size,sha256=sha(p))
    write(out/'manifest.json',manifest)
    with zipfile.ZipFile(original,'w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in sorted(manifest['files']):z.write(ROOT/name,name)
        z.write(out/'manifest.json',(out/'manifest.json').relative_to(ROOT).as_posix())
    with zipfile.ZipFile(original) as z:
        if z.testzip() or len(z.namelist())!=len(set(z.namelist())):raise ValueError('Repacked ZIP validation failed')
        for name,m in manifest['files'].items():
            data=z.read(name)
            if len(data)!=m['bytes'] or hashlib.sha256(data).hexdigest()!=m['sha256'] or sha(ROOT/name)!=m['sha256']:
                raise ValueError('Repacked bytes differ: '+name)
    write(out/'acceptance.json',dict(status='passed_P80_incremental_checkpoint_CRC_SHA',zip_bytes=original.stat().st_size,
                                   zip_sha256=sha(original),files_verified=len(manifest['files']),duplicate_alias_repaired=True))
    print(out,flush=True);print('passed_P80_saved_and_verified',flush=True)

if __name__=='__main__':main()
