import hashlib,json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p43_boot_cycle import installed_snapshot

def profile(tmp_path):
    (tmp_path/'files').mkdir();(tmp_path/'files/monitor').write_bytes(b'exact')
    r=dict(status='passed_long_running_RX_LCD_progress_and_independent_idle',serial_closed=True,
        installed_directory='/etc/p43-20261022T030856Z',installed_files_sha256={'monitor':hashlib.sha256(b'exact').hexdigest()})
    p=tmp_path/'report.json';p.write_text(json.dumps(r));return r,p

def test_explicit_cold_artifact_source_requires_exact_profile_and_bytes(tmp_path):
    r,p=profile(tmp_path);assert installed_snapshot(r,p)=={'monitor':b'exact'}
    (tmp_path/'files/monitor').write_bytes(b'changed')
    with pytest.raises(ValueError,match='install changed'):installed_snapshot(r,p)

@pytest.mark.parametrize('field,value',[('installed_directory','other'),('serial_closed',False),('status','failed')])
def test_mismatched_or_unaccepted_artifact_source_rejected(tmp_path,field,value):
    r,p=profile(tmp_path);changed=dict(r);changed[field]=value;p.write_text(json.dumps(changed))
    with pytest.raises(ValueError,match='exact installed profile'):installed_snapshot(r,p)
