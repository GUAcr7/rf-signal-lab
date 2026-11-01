import argparse
import sys
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'experiments'))
from p42_run_live_panel import validate_progress
from p36_fb_snapshot_run import accepted_panel_parent
from p36_retrieve_file import remote_path
import subprocess

def sample():
    return dict(schema='rfsig.live_progress.v1',state='running',duration_ms_requested=0,
        ADC_gaps='unknown',lossless_proven=False,display_updates=3,published_prefixes=20,
        consumed_prefixes=3,last_display_sequence=19,UI_overwritten_prefixes=16,pending_prefixes=1,
        maxrss_kib=2600,elapsed_software_s=2.,peak_db=-30.,rms_per_component_counts=100.)

def test_accounting_and_monotonic_progress():
    s=sample();assert validate_progress(s,0)==s
    assert validate_progress(dict(s,elapsed_software_s=3),0,s)
    for key,value in [('pending_prefixes',2),('consumed_prefixes',4),('display_updates',True),
            ('last_display_sequence',21),('maxrss_kib',0),('peak_db',float('nan')),
            ('ADC_gaps','none'),('state','finished_bad')]:
        with pytest.raises(ValueError):validate_progress(dict(s,**{key:value}),0)
    with pytest.raises(ValueError):validate_progress(s,1000)
    with pytest.raises(ValueError):validate_progress(dict(s,elapsed_software_s=1),0,s)

def test_live_archive_only_after_completed_idle_RAM_telemetry_verified():
    p=dict(schema='rfsig.p42_board.v1',status='passed_long_running_RX_LCD_progress_and_independent_idle',
        expected_boot='current',independent_final_idle_verified=True,native_completion_unconfirmed=False,
        RAM_filesystem_verified=True,bounded_native_log_verified=True,native_progress_final_verified=True,serial_closed=True)
    assert accepted_panel_parent(p,'current')
    assert not accepted_panel_parent(p,'stale')
    for k in ('independent_final_idle_verified','RAM_filesystem_verified','bounded_native_log_verified','native_progress_final_verified','serial_closed'):
        assert not accepted_panel_parent(dict(p,**{k:False}),'current')
    assert not accepted_panel_parent(dict(p,native_completion_unconfirmed=True),'current')
    path='/run/p42-101112/data/last-display-packed.bin.gz'
    assert remote_path(path)==path
    for bad in (path.replace('data/','data/../'),path+';reboot',path.replace('101112','1')):
        with pytest.raises(argparse.ArgumentTypeError):remote_path(bad)

@pytest.mark.parametrize('extra',[
    ['--duration-ms','0'], ['--duration-ms','0','--cancel-after-ms','86400001'],
    ['--duration-ms','10000','--cancel-after-ms','9500'],['--duration-ms','86400001']])
def test_unbounded_or_invalid_host_test_rejected_before_board_or_files(extra,tmp_path):
    script=Path(__file__).resolve().parents[1]/'experiments/p42_run_live_panel.py'
    result=subprocess.run([sys.executable,str(script),'--expected-boot','not-a-real-boot',
        '--build-report',str(tmp_path/'nonexistent-build.json'),'--clock-acceptance',str(tmp_path/'missing-clock.json'),*extra],
        capture_output=True,text=True,timeout=10)
    assert result.returncode==2
    assert 'FileNotFoundError' not in result.stderr
    assert 'duration' in result.stderr or 'bounded' in result.stderr or 'cancel time' in result.stderr
