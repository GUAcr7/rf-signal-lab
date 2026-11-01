"""Checkpoint source and experiment evidence; never changes board state."""
from datetime import datetime,timezone
import hashlib,json,zipfile
from pathlib import Path
from p32_session import ROOT

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def checkpoint(label,reports,destination=None):
    parent=ROOT/'results/p44-checkpoint-20261022T042651578942Z/report.json';prior=read(parent)
    if sha(ROOT/prior['archive']['path'])!=prior['archive']['sha256']:raise ValueError('parent ZIP differs')
    out=destination or ROOT/'results'/datetime.now(timezone.utc).strftime(label+'-%Y%m%dT%H%M%S%fZ')
    if out.resolve().parent!=(ROOT/'results').resolve():raise ValueError('checkpoint destination outside results')
    out.mkdir(exist_ok=False)
    files=set()
    def add(f):
        if f.is_file() and f.name!='checkpoint.zip' and '__pycache__' not in f.parts and not f.resolve().is_relative_to(out):files.add(f.resolve())
    for d in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        for f in (ROOT/d).rglob('*'):add(f)
    for f in ROOT.iterdir():
        if f.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd') or f.name in ('.gitignore','.gitattributes'):add(f)
    # Explicit evidence such as XML may have no date in its filename.
    for f in reports.values():
        f=Path(f).resolve();add(f)
        if f.name=='report.json':
            for child in f.parent.rglob('*'):add(child)
    for f in (ROOT/'results').iterdir():
        if any(day in f.name for day in ('20261022',datetime.now(timezone.utc).strftime('%Y%m%d'))) or f.name in ('p43-active.json','p44-active.json','p45-active.json','p46-active.json','p47-active.json','p48-active.json','p49-active.json','p50-active.json','p51-active.json'):
            if f.is_dir():
                for child in f.rglob('*'):add(child)
            else:add(f)
    def strings(v):
        if isinstance(v,str):yield v
        elif isinstance(v,dict):
            for x in v.values():yield from strings(x)
        elif isinstance(v,list):
            for x in v:yield from strings(x)
    visited=set()
    while True:
        pending=[f for f in files if f.name=='report.json' and f not in visited]
        if not pending:break
        for f in pending:
            visited.add(f)
            try:v=read(f)
            except (ValueError,UnicodeError):continue
            for s in strings(v):
                if '\n' in s or len(s)>400:continue
                n=s.replace('\\','/')
                if not(n.startswith('results/') or n.lower().startswith(ROOT.as_posix().lower()+'/results/')):continue
                child=Path(s);child=(child if child.is_absolute() else ROOT/child).resolve()
                if not child.is_relative_to(ROOT/'results') or not child.is_file():continue
                add(child)
                if child.name=='report.json':
                    for member in child.parent.rglob('*'):add(member)
    rows=[dict(path=rel(f),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(files)];write(out/'manifest.json',rows)
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for row in rows:
            data=z.read(row['path'])
            if len(data)!=row['bytes'] or hashlib.sha256(data).hexdigest()!=row['sha256']:raise ValueError('member SHA differs')
    phase=label.split('-')[0].upper()
    write(out/'report.json',dict(status='passed_'+phase+'_checkpoint_ZIP_CRC_and_all_member_SHA',files=len(rows),all_member_SHA_verified=True,
        reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in reports.items()},board_operations=False,
        archive=dict(path=rel(archive),bytes=archive.stat().st_size,sha256=sha(archive)),
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent),archive_sha256=prior['archive']['sha256'])))
    return out/'report.json'
