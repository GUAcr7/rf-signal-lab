"""Fixed, audited P59 status/RX-stop/RX-start/calibration entry.

No automatic RF transmit, reboot, PL reload or persistent configuration writes.
Each start preserves the previous RAM session and runs the accepted P56 binary.
"""
import argparse
from contextlib import contextmanager, ExitStack
from datetime import datetime, timezone
import hashlib
import http.server
import json
from pathlib import Path
import re
import sys
import time
import threading
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'src'), str(ROOT / 'experiments')]
from serial.tools import list_ports
from rfsig.board_session import (WORK, boot_uuid, classify_rx, discover_ports,
                                one_json, require_rx_control, require_tx_off,
                                require_signal_ready, source_directory)
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED, CRITICAL_KERNEL
from p46_restore_tx import validate_source_package
from p46_known_source import GUARD_SHA
from p52_ram import board_ram_tmp


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


@contextmanager
def operation_lock():
    """Serialize this entry across processes before either board is opened."""
    import msvcrt
    path = ROOT / 'results/p59-control.lock'
    with path.open('a+b') as handle:
        if handle.tell() == 0:
            handle.write(b'0'); handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_NBLCK, 1)
        try:
            yield
        finally:
            handle.seek(0)
            msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)


def load_profile():
    # Read the accepted immutable checkpoint identity; do not rewrite its claims.
    active_path = ROOT / 'results/p58-active.json'
    active = json.loads(active_path.read_text('utf-8'))
    final_path = ROOT / active['report']
    if sha(final_path) != active['report_sha256']:
        raise ValueError('Accepted P58 report changed')
    final = json.loads(final_path.read_text('utf-8'))
    boot_path = ROOT / final['boot']
    boot = json.loads(boot_path.read_text('utf-8'))
    directory = boot['installed_directory']
    if not re.fullmatch(r'/etc/p43-\d{8}T\d{6}Z', directory):
        raise ValueError('Unexpected accepted profile directory')
    for name, wanted in boot['installed_files_sha256'].items():
        if sha(boot_path.parent / 'files' / name) != wanted:
            raise ValueError('Accepted profile snapshot changed: ' + name)
    return boot, {'accepted_boot_report': str(boot_path),
                  'accepted_boot_report_sha256': sha(boot_path),
                  'accepted_final_report_sha256': sha(final_path)}


class Controller:
    def __init__(self, action):
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
        self.out = ROOT / 'results' / ('p59-' + action + '-' + stamp)
        self.out.mkdir()
        self.profile, provenance = load_profile()
        self.record = dict(status='checking', action=action, stages=[], boards={},
                           RF_transmissions=0, RF_attribute_writes=False,
                           PL_changes=False, reboots_issued=0,
                           persistent_file_writes=False, serial_closed=False,
                           created_utc=datetime.now(timezone.utc).isoformat(),
                           provenance=provenance)
        (self.out / 'executed.py').write_bytes(Path(__file__).read_bytes())
        self.record['ports'] = [dict(device=p.device, vid=p.vid, pid=p.pid,
                                     serial_number=p.serial_number, location=p.location,
                                     description=p.description)
                                for p in list_ports.comports()]
        self.save()
        self.ports = None

    def save(self):
        (self.out / 'report.json').write_text(
            json.dumps(self.record, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')

    @contextmanager
    def board(self, role):
        b = None
        tty_saved = False
        folder = self.out / (role + '-' + uuid.uuid4().hex[:8])
        folder.mkdir()
        try:
            b = Console(self.ports[role], self.record, self.save)
            b.port = AuditPort(b.port, folder)
            b.shell()
            identity = b.command('uname -a')
            if ('Linux pzp201' if role == 'TX' else 'Zynq-Tronlong') not in identity:
                raise ValueError('Unexpected Linux identity on ' + role)
            b.command('p59_prompt=$PS1'); b.command('p59_tty=$(stty -g)')
            tty_saved = True
            b.command("PS1=''"); b.command('stty -echo')
            yield b, identity
        finally:
            if b:
                if tty_saved:
                    try:
                        b.command('stty "$p59_tty"'); b.command('PS1=$p59_prompt')
                    except Exception as error:
                        self.record.setdefault('TTY_restore_errors', []).append(repr(error))
                b.close()
            self.save()

    @staticmethod
    def optional(b, path):
        if not re.fullmatch(r'/[A-Za-z0-9_./-]+', path):
            raise ValueError('Unexpected read path')
        b.command('v=' + path)
        return b.command('if test -f $v;then cat $v;fi')

    @staticmethod
    def digest(b, path):
        b.command('v=' + path)
        matches = re.findall(r'^([0-9a-f]{64})\s+\S+\r?$', b.command('sha256sum $v'), re.M)
        if len(matches) != 1:
            raise ValueError('Ambiguous SHA: ' + path)
        return matches[0]

    def inspect(self, role, b, identity):
        info = dict(identity=identity, boot_id=boot_uuid(b.value('/proc/sys/kernel/random/boot_id')),
                    taint=b.value('/proc/sys/kernel/tainted'))
        b.command('ir=/sys/bus/iio/devices')
        names = parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        info['IIO_names'] = names
        b.command('cd ' + names['ad9361-phy'])
        attrs = (list(RF_EXPECTED) if role == 'RX' else
                 ['out_voltage_sampling_frequency', 'out_voltage_rf_bandwidth',
                  'out_altvoltage1_TX_LO_frequency', 'out_voltage0_hardwaregain',
                  'out_voltage0_rf_port_select'])
        info['RF'] = {key: b.value(key) for key in attrs}
        info['RX_buffer'] = b.value(names['cf-ad9361-lpc'] + '/buffer/enable')
        info['TX_buffer'] = b.value(names['cf-ad9361-dds-core-lpc'] + '/buffer/enable')
        info['kernel_tail'] = b.command('dmesg | tail -n 160')
        info['critical_kernel_fault'] = bool(re.search(CRITICAL_KERNEL, info['kernel_tail']))
        if role == 'TX':
            info['processes'] = b.command('ps')
            info['TX_process_observed'] = bool(re.search(r'arm-tx-source|\./guard --run', info['processes']))
            b.command('cd ' + names['cf-ad9361-dds-core-lpc'])
            def dds(suffix):
                output = b.command('for n in out_altvoltage*_' + suffix + ';do cat $n;done')
                values = [s.strip() for s in output.splitlines() if re.fullmatch(r'-?\d+(?:\.\d+)?\r?', s)]
                return ['0' if float(v) == 0 else v for v in values]
            info['DDS_raw'] = dds('raw'); info['DDS_scale'] = dds('scale')
            info['UART_devices'] = b.command('ls -l /dev/ttyPS*')
            info['UART_runtime'] = b.command('cat /proc/tty/driver/xuartps || true')
            info['root_mounts'] = b.command('cat /proc/mounts')
        else:
            info['RF_matches'] = info['RF'] == RF_EXPECTED
            info['RX_scans'] = [b.value(names['cf-ad9361-lpc'] + '/scan_elements/in_voltage' + str(i) + '_en') for i in range(4)]
            d = self.profile['installed_directory']
            info['profile_hashes'] = {name: self.digest(b, d + '/' + name)
                                      for name in self.profile['installed_files_sha256']}
            info['selected_wrapper_sha256'] = self.digest(b, '/etc/rcS.d/S99board')
            info['profile_verified'] = (info['profile_hashes'] == self.profile['installed_files_sha256']
                and info['selected_wrapper_sha256'] == self.profile['installed_files_sha256']['boot'])
            info['init_boot_marker'] = self.optional(b, '/run/p43-init-boot').strip()
            # Strip framing lines; optional scalar values use a distinct frame below.
            for key, path in [('init_boot_marker', '/run/p43-init-boot'), ('exit_code', WORK + '/exit'), ('owned_pid', WORK + '/pid')]:
                b.command('v=' + path)
                text = b.command('echo __S__$(cat $v 2>/dev/null)__E__')
                values = re.findall(r'^__S__(.*?)__E__\r?$', text, re.M)
                if len(values) != 1:
                    raise ValueError('Ambiguous optional scalar')
                info[key] = values[0] if values[0] else None
            info['owned_timeout_pid'] = int(info['owned_pid']) if str(info['owned_pid']).isdigit() else None
            info['owned_timeout_argv'] = []
            if info['owned_timeout_pid'] and info['owned_timeout_pid'] > 1:
                b.command('v=/proc/' + str(info['owned_timeout_pid']) + '/cmdline')
                text = b.command("if test -f $v;then tr '\\000' '\\n' <$v;fi")
                info['owned_timeout_argv'] = [s.rstrip('\r') for s in text.splitlines()
                    if s and not s.startswith('__P46_')]
            info['progress'] = one_json(self.optional(b, WORK + '/data/progress.json'), optional=True)
            info['AI'] = one_json(self.optional(b, WORK + '/data/ai.json'), optional=True)
            time.sleep(1)
            info['later_progress'] = one_json(self.optional(b, WORK + '/data/progress.json'), optional=True)
            info['progress_advancing'] = bool(info['progress'] and info['later_progress']
                and info['later_progress'].get('display_updates', 0) > info['progress'].get('display_updates', 0))
            info['session_state'] = classify_rx(info)
        if b.value('/proc/sys/kernel/random/boot_id') != info['boot_id']:
            raise ValueError('Boot changed during inspection')
        return info

    def status(self):
        self.ports = discover_ports(self.record['ports'])
        self.record['resolved_ports'] = self.ports
        self.save()
        errors = []
        for role in ('TX', 'RX'):
            try:
                with self.board(role) as (b, identity):
                    self.record['boards'][role] = self.inspect(role, b, identity)
            except Exception as error:
                self.record['boards'][role] = {'error': repr(error)}
                errors.append(role)
            self.save()
        if errors:
            raise ValueError('Could not identify/read: ' + ', '.join(errors))

    def action(self, action):
        self.status()
        tx, rx = self.record['boards']['TX'], self.record['boards']['RX']
        if action == 'status':
            return
        if action == 'prepare-source':
            self.prepare_source(tx)
            return
        if action == 'send':
            self.send_source(tx, rx)
            return
        if action == 'source-off':
            if (tx['taint'] != '0' or tx['TX_buffer'] != '0'
                    or tx['TX_process_observed'] or tx['DDS_scale'] != ['0'] * 8):
                raise ValueError('Source-off requires idle TX with all DDS scales zero')
            with self.board('TX') as (b, identity):
                fresh = self.inspect('TX', b, identity)
                if (fresh['boot_id'] != tx['boot_id'] or fresh['taint'] != '0'
                        or fresh['TX_buffer'] != '0' or fresh['TX_process_observed']
                        or fresh['DDS_scale'] != ['0'] * 8):
                    raise ValueError('TX changed before zero-source selection')
                b.command('cd ' + fresh['IIO_names']['cf-ad9361-dds-core-lpc'])
                b.command('for n in out_altvoltage*_raw;do echo 0 >$n;done')
                self.record['DDS_zero_source_selected'] = True
                after = self.inspect('TX', b, identity)
                require_tx_off(after)
                if after['RF'] != fresh['RF']:
                    raise ValueError('RF attributes changed during zero-source selection')
                self.record['after_TX'] = after
                self.record['result'] = 'verified_idle_DDS_zero_source_not_absolute_RF_silence'
            return
        if action == 'stop' and rx['session_state'] == 'STOPPED':
            self.record['result'] = 'already_stopped_verified_idle'
            return
        if action == 'start' and rx['session_state'] == 'RUNNING':
            self.record['result'] = 'existing_running_session_reused_no_second_RX'
            return
        require_rx_control(rx, running=(action in ('stop', 'calibrate')))
        if action in ('start', 'calibrate'):
            require_tx_off(tx)
        with self.board('RX') as (b, identity):
            current = self.inspect('RX', b, identity)
            if current['boot_id'] != rx['boot_id']:
                raise ValueError('Boot changed since preflight')
            require_rx_control(current, running=(action in ('stop', 'calibrate')))
            b.command('j=' + self.profile['installed_directory'])
            b.command('w=' + WORK)
            if action == 'stop':
                b.command('sh $j/control stop', timeout=20)
            elif action == 'calibrate':
                # Recheck source-off immediately before requesting background.
                with self.board('TX') as (t, tx_identity):
                    fresh = self.inspect('TX', t, tx_identity)
                    if fresh['boot_id'] != tx['boot_id']:
                        raise ValueError('TX boot changed')
                    require_tx_off(fresh)
                    token = uuid.uuid4().hex
                    b.command('k=' + token); b.command('sh $j/control calibrate $k')
                    self.record['calibration_token'] = token
                time.sleep(3)
            elif action == 'start':
                b.command("grep -q ' /run tmpfs ' /proc/mounts")
                summary = one_json(self.optional(b, WORK + '/data/summary.json'))
                if not all(summary.get(k) for k in ('buffer_released', 'context_released', 'worker_joined', 'RF_after_matches')) or summary.get('cleanup_unconfirmed'):
                    raise ValueError('Previous session cleanup not proven')
                previous = '/run/p59-prior-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                b.command('r=' + previous); b.command('test ! -e $r')
                b.command('test -d $w'); b.command('test ! -L $w')
                b.command('mv $w $r'); self.record['preserved_previous_session'] = previous
                b.command('mkdir $w'); b.command('cp $j/monitor $w/monitor')
                b.command('cp $j/run $w/run'); b.command('chmod 755 $w/monitor')
                for name in ('monitor', 'run'):
                    if self.digest(b, WORK + '/' + name) != self.profile['installed_files_sha256'][name]:
                        raise ValueError('New RAM session bytes differ')
                b.command('sh $w/run </dev/null >/dev/null 2>&1 &')
                self.record['host_started_RX_only'] = True
                time.sleep(3)
            final = self.inspect('RX', b, identity)
            self.record['after_RX'] = final
            if action == 'stop':
                require_rx_control(final, running=False)
            else:
                require_rx_control(final, running=True)
                if not final['progress_advancing']:
                    raise ValueError('New/current RX progress did not advance')
                ai = final['AI']
                if action == 'start' and (ai['state'] != 'CALIBRATION_REQUIRED' or ai['ready'] or ai['accepted_class'] != -1 or ai['calibration_token']):
                    raise ValueError('New session reused old calibration')
                if action == 'calibrate' and (ai['state'] != 'WAIT_PILOT' or ai['calibration_token'] != self.record['calibration_token']):
                    raise ValueError('Fresh background calibration not waiting for pilot')
            self.record['result'] = 'verified_' + action

    def prepare_source(self, tx):
        require_tx_off(tx)
        source_path = ROOT / 'results/p54-plan-20261024T042837Z/2026102315/report.json'
        meta, payload, tar_sha = validate_source_package(source_path)
        class Handler(http.server.BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path != '/pkg.gz':
                    self.send_error(404); return
                self.send_response(200)
                self.send_header('Content-Length', str(len(payload)))
                self.end_headers(); self.wfile.write(payload)
            def log_message(self, *args):
                pass
        server = http.server.ThreadingHTTPServer(('192.168.2.10', 0), Handler)
        worker = threading.Thread(target=server.serve_forever, daemon=True)
        worker.start()
        try:
            with self.board('TX') as (b, identity):
                fresh = self.inspect('TX', b, identity)
                require_tx_off(fresh)
                if fresh['boot_id'] != tx['boot_id']:
                    raise ValueError('TX boot changed before upload')
                self.record['resolved_RAM_tmp'] = board_ram_tmp(b)
                directory = '/tmp/p35-p59-' + datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
                b.command('d=' + directory); b.command('test ! -e $d')
                b.command('mkdir $d'); b.command('u=$d/pkg.gz')
                b.command('h=http://192.168.2.10:' + str(server.server_port) + '/pkg.gz')
                b.command('wget -q -T 10 -O $u $h', timeout=15)
                if self.digest(b, directory + '/pkg.gz') != meta['archive_sha256']:
                    raise ValueError('Transferred package SHA mismatch')
                b.command('gzip -dc $d/pkg.gz >$d/pkg.tar')
                if self.digest(b, directory + '/pkg.tar') != tar_sha:
                    raise ValueError('Tar SHA mismatch')
                b.command('tar -xf $d/pkg.tar -C $d'); b.command('chmod 755 $d/guard')
                b.command('cd $d'); b.command('sha256sum -c sums')
                for name, expected in meta['files_sha256'].items():
                    if self.digest(b, directory + '/' + name) != expected:
                        raise ValueError('Extracted source SHA mismatch')
                inspection = b.command('./guard --inspect', timeout=15)
                expected = dict(tx0_sampling_frequency='30720000',
                    tx0_hardwaregain='-10.000000 dB', tx0_rf_bandwidth='18000000',
                    tx0_rf_port_select='A', tx_lo='2450000000', TX_DMA_sampling_frequency='30720000')
                for key, value in expected.items():
                    if not re.search(r'^' + re.escape(key + '=' + value) + r'\r?$', inspection, re.M):
                        raise ValueError('TX RF/DMA differs: ' + key)
                for name in ('tone', 'bpsk', 'qpsk', 'qam16'):
                    b.command('h=' + meta['files_sha256'][name])
                    result = b.command('./guard --check ' + name + ' 131072 $h')
                    if 'INPUT_CHECK_PASS samples=131072' not in result:
                        raise ValueError('Native file check failed')
                self.record['source'] = dict(expected_boot=tx['boot_id'],
                    remote_directory=directory, files_sha256=meta['files_sha256'],
                    source_report=source_path.relative_to(ROOT).as_posix(),
                    source_report_sha256=sha(source_path), references=meta['references'],
                    source_peak_component_counts=256, inspect=inspection)
                self.record['result'] = 'verified_frozen_sources_uploaded_RAM_only_no_TX'
        finally:
            server.shutdown(); server.server_close(); worker.join(timeout=3)

    def send_source(self, tx, rx):
        if not self.options.rf_link_reviewed:
            raise ValueError('Use --rf-link-reviewed only for the established reviewed coax link')
        require_tx_off(tx); require_signal_ready(rx, self.options.signal)
        cache = json.loads((ROOT / 'results/p59-source-active.json').read_text('utf-8'))
        report_path = ROOT / cache['report']
        if sha(report_path) != cache['report_sha256']:
            raise ValueError('Source upload report changed')
        report = json.loads(report_path.read_text('utf-8'))
        if report['status'] != 'passed_P59_prepare-source':
            raise ValueError('Accepted source upload required')
        source = report['source']
        directory = source_directory(source, tx['boot_id'])
        if sha(ROOT / source['source_report']) != source['source_report_sha256']:
            raise ValueError('Frozen source provenance changed')
        signal = self.options.signal
        seconds = self.options.seconds
        with self.board('TX') as (t, identity):
            fresh = self.inspect('TX', t, identity)
            require_tx_off(fresh)
            if fresh['boot_id'] != tx['boot_id']:
                raise ValueError('TX boot changed before transmission')
            if self.digest(t, directory + '/guard') != GUARD_SHA:
                raise ValueError('TX guard changed')
            if self.digest(t, directory + '/' + signal) != source['files_sha256'][signal]:
                raise ValueError('Source waveform changed')
            with self.board('RX') as (b, rx_identity):
                current = self.inspect('RX', b, rx_identity)
                require_signal_ready(current, signal)
                if current['boot_id'] != rx['boot_id']:
                    raise ValueError('RX boot changed')
                if current['AI']['calibration_token'] != rx['AI']['calibration_token']:
                    raise ValueError('Calibration session changed')
                t.command('cd ' + directory); t.command('p=' + signal)
                t.command('h=' + source['files_sha256'][signal])
                t.command('b=boot-session:' + tx['boot_id'])
                t.command('n=131072; f=30720000; l=2450000000; w=18000000')
                marker = '__P59_TX_' + uuid.uuid4().hex[:8] + '__'
                command = './guard --run $p $n $f $l $w -10 ' + str(seconds) + ' $b A $h RF_LINK_REVIEWED'
                if len(command) > 72:
                    raise ValueError('TX command too long')
                self.record.update(source_upload_report=cache['report'],
                    source_upload_report_sha256=cache['report_sha256'],
                    source_truth=signal, TX_seconds=seconds, source_metadata=source['references'][signal],
                    AI_observations=[], RF_transmissions_requested=1, TX_cleanup_verified=False,
                    scope='deployment observation on exposed seed2315, not independent accuracy')
                pending = False
                transcript = ''
                self.save()
                try:
                    t.port.write((command + "\rprintf '\\n" + marker + ":%s\\n' \"$?\"\r").encode('ascii'))
                    pending = True
                    transcript = t.read(10, r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=' + str(seconds))
                    if 'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=' + str(seconds) not in transcript:
                        raise ValueError('TX submission not confirmed')
                    self.record['RF_transmissions'] = 1
                    self.record['TX_submission_confirmed'] = True
                    started = time.monotonic()
                    while time.monotonic() - started < seconds:
                        self.record['AI_observations'].append(one_json(self.optional(b, WORK + '/data/ai.json')))
                        self.save(); time.sleep(.5)
                finally:
                    if pending:
                        deadline = time.monotonic() + seconds + 12
                        while not re.search(r'^' + marker + r':\d+\r?$', transcript, re.M) and time.monotonic() < deadline:
                            transcript += t.read(2, r'^' + marker + r':\d+\r?$')
                        self.record['TX_transcript'] = transcript
                        self.record['TX_cleanup_verified'] = bool(
                            re.search(r'^' + marker + r':0\r?$', transcript, re.M)
                            and 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' in transcript
                            and 'DDS_ZERO_SOURCE_READBACK=PASS' in transcript)
                        self.save()
                if not self.record['TX_cleanup_verified']:
                    raise ValueError('TX completion/cleanup not confirmed')
                after_tx = self.inspect('TX', t, identity)
                require_tx_off(after_tx)
                if after_tx['RF'] != fresh['RF']:
                    raise ValueError('TX RF changed')
                self.record['after_TX'] = after_tx
                self.record['after_RX'] = self.inspect('RX', b, rx_identity)
                self.record['result'] = 'verified_bounded_source_TX_cleanup_and_current_RX_observations'


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument('action', choices=('status', 'start', 'stop', 'calibrate', 'source-off', 'prepare-source', 'send'), nargs='?', default='status')
    ap.add_argument('--signal', choices=('tone', 'bpsk', 'qpsk', 'qam16'), default='tone')
    ap.add_argument('--seconds', type=int, default=15)
    ap.add_argument('--rf-link-reviewed', action='store_true')
    args = ap.parse_args()
    if not 5 <= args.seconds <= 60:
        ap.error('--seconds must be between 5 and 60')
    c = None
    ownership = ExitStack()
    try:
        ownership.enter_context(operation_lock())
        c = Controller(args.action)
        c.options = args
        print(c.out, flush=True)
        c.action(args.action)
        c.record['status'] = 'passed_P59_' + args.action
    except Exception as error:
        if c:
            c.record.update(status='failed_or_unconfirmed_P59_' + args.action, error=repr(error))
        else:
            print(repr(error), file=sys.stderr)
        return 1
    finally:
        if c:
            c.record['serial_closed'] = True
            c.save()
            if c.record['status'] == 'passed_P59_prepare-source':
                pointer = dict(report=(c.out / 'report.json').relative_to(ROOT).as_posix(),
                               report_sha256=sha(c.out / 'report.json'))
                (ROOT / 'results/p59-source-active.json').write_text(
                    json.dumps(pointer, indent=2) + '\n', encoding='utf-8')
            print(c.record['status'], flush=True)
        ownership.close()
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
