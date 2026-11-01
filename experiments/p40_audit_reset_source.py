"""Archive pinned vendor AD9361 reset/probe sources for offline diagnosis only."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import tarfile

from p32_session import ROOT


def main():
    prior_path=ROOT/'results/p31-vendor-kernel-20261019T143355Z/report.json'
    prior=json.loads(prior_path.read_text('utf-8'))
    source=Path(prior['source'])
    digest=hashlib.sha256()
    with source.open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):digest.update(chunk)
    if digest.hexdigest()!=prior['archive_sha256']:raise ValueError('vendor source archive changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-reset-source-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    wanted={'drivers/iio/adc/ad9361.c','drivers/iio/adc/ad9361.h','drivers/spi/spi.c'}
    rows=[]
    with tarfile.open(source,'r:gz') as t:
        for member in t:
            if member.name not in wanted:continue
            if not member.isfile() or member.size>2*1024*1024:raise ValueError('unexpected source member')
            raw=t.extractfile(member).read()
            target=member.name.replace('/','__')+'.txt';(out/target).write_bytes(raw)
            rows.append(dict(member=member.name,file=target,bytes=len(raw),sha256=hashlib.sha256(raw).hexdigest()))
            if len(rows)==len(wanted):break
    if set(r['member'] for r in rows)!=wanted:raise ValueError('source members missing')
    r=dict(status='pinned_vendor_reset_and_SPI_sources_archived_for_offline_review',
        source=str(source),archive_sha256=digest.hexdigest(),files=rows,
        previous_source_report=str(prior_path),exact_running_dirty_source_build_match_proven=False,
        board_operations=False,kernel_modified=False,reset_waveform_measured=False,root_cause_closed=False)
    (out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    print(out);print(r['status'])


if __name__=='__main__':main()
