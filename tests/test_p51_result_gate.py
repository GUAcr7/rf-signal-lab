import json,sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p51_save_progress import stable_trial
import p51_ai_diagnostic as nominal
import p51_ai_tone_diagnostic as calibrated


def trial():
    r=dict(schema='rfsig.p42_board.v1',status='passed_long_running_RX_LCD_progress_and_independent_idle',
        expected_boot='same',display_revision='p48',duration_ms=1800000,cancel_signal_sent=False)
    for k in ('independent_final_idle_verified','RAM_filesystem_verified','bounded_native_log_verified','native_progress_final_verified','serial_closed'):r[k]=True
    r['native_completion_unconfirmed']=False
    r['native_summary']=dict(duration_ms_requested=1800000,elapsed_software_s=1800.1,status='pass',reason='duration_complete',
        display_updates=3580,maxrss_kib=2504,RF_attributes_written=False,TX_API_loaded=False)
    r['progress_samples']=[dict(state='running',elapsed_software_s=1,display_updates=2,maxrss_kib=2504),
        dict(state='running',elapsed_software_s=11,display_updates=22,maxrss_kib=2504),
        dict(state='finished',elapsed_software_s=1800.1,display_updates=3580,maxrss_kib=2504)]
    return r


def test_duration_completion_and_observed_memory_are_distinct_claims():
    result=stable_trial(trial())
    assert result['observed_maxrss_growth_kib']==0 and not result['physical_refresh_rate_measured'] and not result['lossless_proven']


@pytest.mark.parametrize('kind',['short','cancelled','signal-stop','active','stalled','unfinished','RF-write'])
def test_premature_stop_or_hidden_stall_cannot_pass_long_run(kind):
    r=trial()
    if kind=='short':r['native_summary']['elapsed_software_s']=1799
    if kind=='cancelled':r['cancel_signal_sent']=True
    if kind=='signal-stop':r['native_summary']['reason']='signal_requested_stop'
    if kind=='active':r['native_completion_unconfirmed']=True
    if kind=='stalled':r['progress_samples'][1]['display_updates']=2
    if kind=='unfinished':r['progress_samples'][-1]['state']='running'
    if kind=='RF-write':r['native_summary']['RF_attributes_written']=True
    with pytest.raises(ValueError):stable_trial(r)


@pytest.mark.parametrize('module',[nominal,calibrated])
def test_frozen_probe_inputs_cannot_change_after_diagnostic_plan(tmp_path,monkeypatch,module):
    monkeypatch.setattr(module,'ROOT',tmp_path)
    model=tmp_path/'frozen.npz';model.write_bytes(b'frozen')
    p=tmp_path/'plan.json';p.write_text(json.dumps(dict(status='frozen_before_RF_diagnostic_predictions',
        class_order=['BPSK','QPSK','16QAM'],inputs={'model':dict(path='frozen.npz',sha256=module.sha(model))})))
    module.load_plan(p)
    model.write_bytes(b'changed')
    with pytest.raises(ValueError,match='frozen input changed'):module.load_plan(p)
