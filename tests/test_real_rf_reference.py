import copy,json
from pathlib import Path
import pytest
from rfsig.real_rf_reference import reproduce_reference
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'results/p51-rf-bank-20261023T152633Z/2026102301'

@pytest.mark.parametrize('name',['tone','bpsk','qpsk','qam16'])
def test_metadata_reproduces_new_seed_without_hardcoded_old_seed(name):
    meta=json.loads((SOURCE/'report.json').read_text())
    wave=reproduce_reference(meta['references'][name],(SOURCE/name).read_bytes())
    assert wave.reference['seed']==2026102301

@pytest.mark.parametrize('field,value',[('seed',20261016),('seed',True),('digital_peak_counts',512),('sample_rate_hz',1000000),('samples_per_symbol',64)])
def test_wrong_reference_refused_before_quality_analysis(field,value):
    ref=copy.deepcopy(json.loads((SOURCE/'report.json').read_text())['references']['bpsk']);ref[field]=value
    with pytest.raises(ValueError):reproduce_reference(ref,(SOURCE/'bpsk').read_bytes())

def test_wrong_payload_is_never_used_as_known_source():
    ref=json.loads((SOURCE/'report.json').read_text())['references']['qpsk'];raw=(SOURCE/'qpsk').read_bytes()
    with pytest.raises(ValueError,match='exact TX bytes'):reproduce_reference(ref,b'\0\0\0\0'+raw[4:])
