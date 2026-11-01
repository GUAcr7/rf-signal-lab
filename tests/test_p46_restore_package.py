"""Reject unsafe recovery packages on the PC before any UART is opened."""
import gzip
import hashlib
import io
import json
from pathlib import Path
import shutil
import sys
import tarfile
import pytest

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p32_session import ROOT
from p46_restore_tx import validate_source_package

PARENT=ROOT/'results/p46-source-20261022T112638Z/report.json'


def clone(tmp_path):
    source=json.loads(PARENT.read_text('utf-8'))
    for name in (*source['files_sha256'],'pkg.gz','report.json'):
        shutil.copyfile(PARENT.parent/name,tmp_path/name)
    return source,tmp_path/'report.json'


def test_original_host_package_is_still_accepted():
    meta,payload,digest=validate_source_package(PARENT)
    assert meta['source_peak_component_counts']==256
    assert digest==hashlib.sha256(gzip.decompress(payload)).hexdigest()


def test_rejects_changed_host_file(tmp_path):
    _,p=clone(tmp_path);(tmp_path/'tone').write_bytes(b'broken')
    with pytest.raises(ValueError,match='host source changed'):validate_source_package(p)


def test_rejects_above_peak_even_with_updated_member_hash(tmp_path):
    meta,p=clone(tmp_path);f=tmp_path/'tone';raw=f.read_bytes()
    raw=(8192).to_bytes(2,'little',signed=True)+raw[2:];f.write_bytes(raw)
    meta['files_sha256']['tone']=hashlib.sha256(raw).hexdigest()
    p.write_text(json.dumps(meta),'utf-8')
    with pytest.raises(ValueError,match='peak256'):validate_source_package(p)


@pytest.mark.parametrize('corruption',('extra_member','different_payload'))
def test_rejects_archive_that_does_not_match_checked_files(tmp_path,corruption):
    meta,p=clone(tmp_path);stream=io.BytesIO()
    with tarfile.open(fileobj=stream,mode='w') as archive:
        for name in meta['files_sha256']:
            raw=(tmp_path/name).read_bytes()
            if corruption=='different_payload' and name=='tone':raw=bytes(len(raw))
            entry=tarfile.TarInfo(name);entry.size=len(raw);archive.addfile(entry,io.BytesIO(raw))
        if corruption=='extra_member':
            entry=tarfile.TarInfo('../unexpected');entry.size=1;archive.addfile(entry,io.BytesIO(b'x'))
    payload=gzip.compress(stream.getvalue());(tmp_path/'pkg.gz').write_bytes(payload)
    meta['archive_sha256']=hashlib.sha256(payload).hexdigest();p.write_text(json.dumps(meta),'utf-8')
    with pytest.raises(ValueError,match='archive'):validate_source_package(p)
