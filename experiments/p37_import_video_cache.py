"""Copy only the unchanged baseline video IP cache into the independent project."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from p32_session import ROOT
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    source=Path('E:/p33-ttl-114312/project/combined.cache/ip/2021.1/e80800addbb7fa01')
    target=Path('E:/p37-clock-082321/project/combined.cache/ip/2021.1/e80800addbb7fa01')
    if target.exists():raise RuntimeError('cache entry already exists; no overwrite')
    old=json.loads(Path('E:/p33-ttl-114312/project/combined.srcs/sources_1/bd/system/system.bd').read_text('utf-8'))['design']
    new=json.loads(Path('E:/p37-clock-082321/project/combined.srcs/sources_1/bd/system/system.bd').read_text('utf-8'))['design']
    if old['components']['v_tpg_0']!=new['components']['v_tpg_0']:raise RuntimeError('video component changed')
    before={p.name:sha(p) for p in source.iterdir() if p.is_file()}
    if 'system_v_tpg_0_0.dcp' not in before:raise RuntimeError('baseline video checkpoint absent')
    target.mkdir(parents=True,exist_ok=False)
    for name in before:(target/name).write_bytes((source/name).read_bytes())
    after={p.name:sha(p) for p in target.iterdir() if p.is_file()}
    if before!=after or before!={p.name:sha(p) for p in source.iterdir() if p.is_file()}:raise RuntimeError('cache copy mismatch')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p37-video-cache-copy-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(status='copied_unchanged_video_cache_pending_native_match',source=str(source),target=str(target),
        files_sha256=before,board_operations=False,source_unchanged=True,
        predecessor='results/p37-safe-synth-20261021T082809Z/report.json',
        predecessor_note='Intentionally stopped only this owned build process tree during unchanged video HLS regeneration; not a hardware or timing failure',
        native_cache_match_still_required=True)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());print(out)
if __name__=='__main__':main()
