import json
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'experiments'))
from p35_once_merged_trial import verified_reuse, sha


@pytest.fixture
def inputs(tmp_path):
    bit = tmp_path/'bit.json'; bit.write_bytes(b'accepted-bit-report')
    overlay = tmp_path/'overlay.json'; overlay.write_bytes(b'accepted-overlay-report')
    prior = dict(status='passed_fresh_boot_merged_probe_and_software_clocks_only',
        serial_closed=True, guard_restored=True, fresh_empty_boot_verified=True,
        reboots_issued=1, PL_programming_attempts=1, overlay_apply_attempts=1,
        bitstream_report_sha256=sha(bit.read_bytes()), overlay_report_sha256=sha(overlay.read_bytes()),
        bitstream_sha256=sha(b'bin'), overlay_sha256=sha(b'dtbo'),
        unique_firmware_name='p35-ttl-20261021T090121Z.bin',
        unique_overlay_name='p35-merged-20261021T090121Z.dtbo')
    return tmp_path/'prior.json', prior, bit, overlay


def invoke(inputs):
    path, prior, bit, overlay = inputs
    path.write_text(json.dumps(prior), encoding='utf-8')
    return verified_reuse(path, bit, overlay, b'bin', b'dtbo')


def test_accepted_matching_pair_is_only_a_reuse_hint(inputs):
    assert invoke(inputs)['firmware_name']=='p35-ttl-20261021T090121Z.bin'


@pytest.mark.parametrize('key,value', [('status', 'failed'), ('guard_restored', False),
    ('fresh_empty_boot_verified', False), ('reboots_issued', 2), ('PL_programming_attempts', True),
    ('bitstream_sha256', sha(b'other')), ('unique_firmware_name', '../ad9361.bin'),
    ('unique_overlay_name', 'p35-merged-20261020T090121Z.dtbo')])
def test_prior_trial_or_artifact_mismatch_is_rejected(inputs, key, value):
    inputs[1][key] = value
    with pytest.raises(ValueError): invoke(inputs)


def test_changed_host_input_is_rejected(inputs):
    inputs[2].write_bytes(b'changed')
    with pytest.raises(ValueError): invoke(inputs)
