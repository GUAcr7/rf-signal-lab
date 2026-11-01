"""Run the same P42 lifecycle checks against the isolated P48 display fork."""
import json
import numpy as np
import pytest
from test_native_rx_full_p36 import ROOT,posix,run
from test_native_live_panel_p42 import (
    invoke,
    test_single_buffer_latest_mailbox_accounting_saved_prefix_and_numerics,
    test_setup_or_refill_error_never_passes_and_releases_resources,
    test_sigterm_during_refill_cancels_and_joins_without_false_duration_pass,
    test_RF_drift_fails_despite_successful_display_updates,
    test_unjoinable_worker_does_not_destroy_live_buffer,
    test_invalid_limits_create_no_output,
    test_existing_output_is_preserved,
    test_until_signal_atomic_progress_and_constant_log_storage,
    test_progress_write_failure_stops_and_releases_RX,
    test_unlimited_cancel_during_refill_is_not_duration_success,
)


@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out=tmp_path_factory.mktemp('live-p48')
    for source,target,flags in (
        (ROOT/'tests/native/mock_latest_panel_p39.c',out/'libiio.so.0',['-shared','-fPIC']),
        (ROOT/'embedded/arm_live_panel_p48/arm_live_panel_p48.c',out/'monitor',['-pthread','-ldl','-lrt','-lm'])):
        result=run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),
                    posix(source),'-o',posix(target),*flags])
        assert result.returncode==0,result.stderr.decode(errors='replace')
    return out


def test_live_metrics_units_come_from_validated_RF_readback(built,tmp_path):
    result,out,_=invoke(built,tmp_path)
    assert result.returncode==0,result.stderr.decode(errors='replace')
    summary=json.loads((out/'summary.json').read_text())
    assert summary['program_version']=='p42' and summary['display_revision']=='p48'
    row=next(json.loads(s) for s in result.stdout.decode().splitlines() if s.startswith('{') and 'arm_panel_metrics' in s)
    assert row['display_revision']=='p48' and row['sample_rate_hz']==30720000
    assert row['fft_bin_width_hz']==30000
    assert row['peak_offset_hz']==row['peak_offset_bins']*30000


@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    out=tmp_path_factory.mktemp('p48-labels');source=out/'probe.c'
    source.write_text('''#define main saved_p48_main
#include "'''+posix(ROOT/'embedded/arm_panel_p48/arm_panel.c')+'''"
#undef main
int main(int argc, char **argv) {
    if (argc != 4) return 2;
    panel_sample_rate_hz = strtod(argv[1], NULL);
    char label[128];
    peak_offset_label(label, sizeof label, strtod(argv[2], NULL), atoi(argv[3]));
    puts(label);
    return 0;
}
''',encoding='ascii')
    result=run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',posix(source),'-o',posix(out/'probe'),'-lm'])
    assert result.returncode==0,result.stderr.decode(errors='replace')
    return out/'probe'


@pytest.mark.parametrize('rate,bins,valid,label',[
    ('30720000','33','1','+990.0 kHz'),('30720000','-33','1','-990.0 kHz'),
    ('30720000','0','1','+0.0 kHz'),('30720000','-512','1','-15360.0 kHz'),
    ('30720000','511','1','+15330.0 kHz'),('30720000','0','0','none (zero input)'),
    ('0','33','1','unknown sample rate'),('nan','33','1','unknown sample rate'),
    ('15360000','33','1','+495.0 kHz'),('30720000','nan','1','invalid peak'),
])
def test_signed_frequency_labels_and_unknown_rate_never_guess(probe,rate,bins,valid,label):
    result=run([posix(probe),rate,bins,valid])
    assert result.returncode==0 and result.stdout.decode().strip()==label
