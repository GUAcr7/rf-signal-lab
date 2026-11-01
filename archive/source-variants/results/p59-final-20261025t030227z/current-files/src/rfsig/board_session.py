"""Pure identity and ownership checks for the fixed P59 board-control entry."""
import json
import re

WORK = '/run/p42-000043'
FTDI_SERIAL = '210203859289B'


def discover_ports(ports):
    """Require one known P201 bridge and one unambiguous CH340 candidate.

    USB identity selects a candidate only; Linux identity must be checked next.
    Bluetooth and the Pluto USB gadget console are never probed.
    """
    tx = [p for p in ports if p.get('vid') == 0x0403
          and p.get('pid') == 0x6010 and p.get('serial_number') == FTDI_SERIAL]
    rx = [p for p in ports if p.get('vid') == 0x1A86 and p.get('pid') == 0x7523]
    if len(tx) != 1 or len(rx) != 1:
        raise ValueError('Require one known P201 FTDI and one CH340; missing or ambiguous USB identity')
    if tx[0]['device'] == rx[0]['device']:
        raise ValueError('TX/RX ports must be distinct')
    return {'TX': tx[0]['device'], 'RX': rx[0]['device']}


def one_json(text, optional=False):
    rows = [json.loads(s) for s in text.splitlines() if s.startswith('{')]
    if optional and not rows:
        return None
    if len(rows) != 1 or not isinstance(rows[0], dict):
        raise ValueError('Expected one framed JSON object')
    return rows[0]


def boot_uuid(value):
    if not isinstance(value, str) or not re.fullmatch(
            r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}', value):
        raise ValueError('Invalid boot UUID')
    return value


def owned_timeout(pid, argv):
    """Exact argv, rather than substring grep, prevents signalling a reused PID."""
    return (isinstance(pid, int) and not isinstance(pid, bool) and pid > 1
            and argv == ['timeout', '-k', '22', '930', WORK + '/monitor',
                         WORK + '/data', '900000', '500'])


def classify_rx(info):
    """Conservative present-state inference; retained results never imply RX live."""
    if info.get('taint') != '0' or not info.get('profile_verified'):
        return 'UNVERIFIED'
    if info.get('init_boot_marker') != info.get('boot_id'):
        return 'WRONG_BOOT_MARKER'
    active = info.get('RX_buffer') == '1'
    scans = info.get('RX_scans', [])
    exited = info.get('exit_code')
    progress = info.get('progress') or {}
    ai = info.get('AI') or {}
    valid_ai = ai.get('boot_id') == info.get('boot_id')
    owned = owned_timeout(info.get('owned_timeout_pid'), info.get('owned_timeout_argv'))
    if active and exited is None and owned and valid_ai and progress.get('state') == 'running':
        return 'RUNNING' if info.get('progress_advancing') else 'RUNNING_PROGRESS_UNCONFIRMED'
    if (not active and info.get('RX_buffer') == '0' and scans == ['0'] * 4
            and exited in ('0', '143') and not owned
            and progress.get('state') == 'stopped' and ai.get('state') == 'STOPPED'
            and valid_ai and ai.get('accepted_class') == -1):
        return 'STOPPED'
    return 'INCONSISTENT_OR_UNKNOWN'


def require_rx_control(info, running):
    state = classify_rx(info)
    if running:
        if state not in ('RUNNING', 'RUNNING_PROGRESS_UNCONFIRMED'):
            raise ValueError('A current boot-owned running RX is required: ' + state)
    elif state != 'STOPPED':
        raise ValueError('A clean stopped RX is required: ' + state)
    if not info.get('RF_matches') or info.get('critical_kernel_fault'):
        raise ValueError('RX RF/kernel preflight failed')


def require_tx_off(info):
    if (info.get('taint') != '0' or info.get('TX_buffer') != '0'
            or info.get('TX_process_observed')
            or info.get('DDS_raw') != ['0'] * 8
            or info.get('DDS_scale') != ['0'] * 8):
        raise ValueError('Source-off preflight failed; calibration not requested')


def require_signal_ready(info, signal):
    require_rx_control(info, running=True)
    ai = info['AI']
    if signal == 'tone':
        if ai.get('state') != 'WAIT_PILOT' or ai.get('ready'):
            raise ValueError('Reference tone requires a fresh WAIT_PILOT state')
    elif signal not in ('bpsk', 'qpsk', 'qam16') or not ai.get('ready'):
        raise ValueError('Modulated source requires this session calibrated')
    if not re.fullmatch(r'[0-9a-fA-F]{32}', ai.get('calibration_token', '')):
        raise ValueError('Calibration token missing')


def source_directory(source, boot):
    if source.get('expected_boot') != boot:
        raise ValueError('Source cache is from an earlier boot')
    path = source.get('remote_directory', '')
    if not re.fullmatch(r'/tmp/p35-p59-\d{8}T\d{6}Z', path):
        raise ValueError('Source cache has an unexpected directory')
    if source.get('source_peak_component_counts') != 256:
        raise ValueError('Source cache changed peak level')
    return path


def score_observations(observations, expected, seconds):
    """Score only stable polled updates, never advertise as full-history accuracy."""
    if not observations:
        raise ValueError('No observations')
    first = observations[0]['elapsed_s']
    stable = [a for a in observations if first + 2 <= a['elapsed_s'] <= first + seconds - 3]
    classified = [a for a in stable if a['state'] == 'CLASSIFIED' and a['accepted_class'] >= 0]
    correct = [a for a in classified if a['accepted_class'] == expected]
    coverage = len(classified) / len(stable) if stable else 0
    accuracy = len(correct) / len(classified) if classified else 0
    return dict(stable_polled_updates=len(stable), classified=len(classified), correct=len(correct),
                coverage=coverage, conditional_accuracy=accuracy,
                passed=bool(stable) and coverage >= .70 and accuracy >= .90)

