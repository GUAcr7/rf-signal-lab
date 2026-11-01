"""Offline review of the observed demo, preserving missing action coverage."""
from pathlib import Path
from datetime import datetime, timezone
import argparse
import json
import sys
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / 'experiments'), str(ROOT / 'host'), str(ROOT / 'src')]
from p79_review_screen_session import read, panel, decode_rx12, glyph_mask
from PIL import Image


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--archive', type=Path, required=True)
    args = ap.parse_args()
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p83-review-%Y%m%dT%H%M%SZ')
    out.mkdir()
    r = dict(status='reviewing_P83_observed_actions', gates=[], groups=[], board_operations=False,
             archive=str(args.archive.resolve().relative_to(ROOT)), archive_sha256=panel.control.sha(args.archive),
             user_feedback='全部正常，演示完成', feedback_does_not_substitute_missing_packets=True,
             standalone_without_PC=False, analyzer_comparison=False, new_independent_AI_accuracy=False)

    def gate(name, passed):
        r['gates'].append(dict(name=name, passed=bool(passed)))
        if not passed:
            raise ValueError(name)

    try:
        a = read(args.archive)
        gate('complete stopped archive', a['status'] == 'passed_P79_stopped_RX_full_history_archived'
             and a['serial_closed'] and a['TX_stopped'] and a['RX_stopped'])
        sp = ROOT / a['screen_report']
        s = read(sp)
        gate('unchanged closed manual session', panel.control.sha(sp) == a['screen_sha256']
             and s['serial_closed'] and s['input_origin'] == 'human_finger'
             and s['status'] in ('partial_P79_interactive_session', 'passed_P79_physical_screen_RF_presets_and_cleanup'))
        r.update(screen=str(sp.relative_to(ROOT)), screen_sha256=panel.control.sha(sp), screen_status=s['status'])
        files = args.archive.parent / 'files'
        for name, digest in a['files_sha256'].items():
            gate('archive SHA ' + name, panel.control.sha(files / name) == digest)
        ai = [json.loads(x) for x in (files / 'ai-history.jsonl').read_text().splitlines()]
        metrics = [json.loads(x) for x in (files / 'metrics-history.jsonl').read_text().splitlines()]
        summary, progress = read(files / 'summary.json'), read(files / 'progress.json')
        gate('complete paired history', len(ai) == len(metrics) == summary['display_updates'] + 1)
        gate('stopped resource cleanup', summary['display_revision'] == 'p75' and summary['status'] == 'stopped'
             and all(summary[k] for k in ('worker_joined', 'buffer_released', 'context_released', 'RF_after_matches'))
             and not summary['cleanup_unconfirmed'])
        gate('same boot and original model', all(x['boot_id'] == a['after_RX']['boot_id']
             and x['model_sha256'] == 'bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457' for x in ai))
        gate('AI metrics paired source state token', all(x['source_block_sequence'] == m['source_block_sequence']
             and x['state'] == m['AI_state'] and x['accepted_class'] == m['accepted_class']
             and x['calibration_token'] == m['calibration_token'] for x, m in zip(ai, metrics)))
        gate('invalid measurements cleared', all(m['valid'] or all(m[k] is None for k in
             ('LO_plus_center_hz', 'ROI_99_width_hz', 'ROI_power_counts_squared', 'center_offset_hz')) for m in metrics))
        gate('stopped AI cleared', ai[-1]['state'] == 'STOPPED' and ai[-1]['accepted_class'] == -1 and not metrics[-1]['valid'])
        natural, stops = set(), []
        for job in s['jobs']:
            path = ROOT / job['report']
            gate('unchanged successful job ' + path.parent.name, panel.control.sha(path) == job['report_sha256'] and job['passed'])
            if job['kind'] != 'run' or job.get('before_RF'):
                continue
            j = read(path)
            gate('native identity and cleanup ' + j['signal'], panel.accepted_receipt(j['supervisor_receipt'],
                 j['job_nonce'], j['boards']['TX']['boot_id'], j['signal'], j['seconds'])
                 and j['TX_cleanup_verified'] and panel.cleanup_proven(j['TX_transcript'], j['TX_exit_code']))
            if job.get('cancelled'):
                if job.get('cancel_reason') == 'stop':
                    gate('native in-flight STOP', j['supervisor_receipt']['stop_seen'] and j['supervisor_receipt']['signal_sent'])
                    stops.append(job)
                continue
            observed = j['AI_observations']
            gate('RX observations present', bool(observed))
            start, token = observed[0]['elapsed_s'], j['boards']['RX']['AI']['calibration_token']
            rows = [x for x in ai[:-1] if start + 2 <= x['elapsed_s'] <= start + j['seconds'] - 3
                    and x['calibration_token'] == token]
            accepted = [x for x in rows if x['state'] == 'CLASSIFIED' and x['accepted_class'] >= 0]
            expected = dict(bpsk=0, qpsk=1, qam16=2)[j['signal']]
            correct = sum(x['accepted_class'] == expected for x in accepted)
            coverage = len(accepted) / len(rows) if rows else 0
            accuracy = correct / len(accepted) if accepted else 0
            r['groups'].append(dict(signal=j['signal'], stable_updates=len(rows), accepted=len(accepted),
                                    correct=correct, coverage=coverage, conditional_accuracy=accuracy))
            gate('unchanged known-source acceptance ' + j['signal'], len(rows) >= 5 and coverage >= .70 and accuracy >= .90)
            natural.add(j['signal'])
        gate('at least one actual natural source', bool(natural))
        times = np.array([x['elapsed_s'] for x in ai[:-1]])
        seq = np.array([x['source_block_sequence'] for x in ai[:-1]])
        gate('fresh advancing display', len(times) > 2 and np.all(np.diff(times) > 0)
             and np.all(np.diff(seq) > 0) and np.max(np.diff(times)) < 2)
        pair = decode_rx12((files / 'last-display-packed.bin').read_bytes())
        x = pair[:8192, 0].astype(float) + 1j * pair[:8192, 1]
        w = (.5 - .5 * np.cos(2 * np.pi * np.arange(1024) / 1024)).astype(np.float32).astype(float)
        power = np.mean(abs(np.fft.fft(x.reshape(8, 1024) * w, axis=1)) ** 2, axis=0) / (1024 * np.sum(w * w))
        gate('same-source final FFT RMS', abs(10 * np.log10(max(power)) - progress['peak_db']) < .002
             and abs(float(np.sqrt(np.mean(abs(x) ** 2) / 2)) - progress['rms_per_component_counts']) < 1e-6)
        pixels = np.fromfile(files / 'fb.raw', dtype='<u4').reshape(480, 800)
        for y, label, color, left in ((286, 'State: STOPPED', 0xffdee6ee, 456),
                                    (308, 'LO+center: unavailable', 0xff96a5b6, 456),
                                    (328, '99% ROI BW: unavailable', 0xff96a5b6, 456),
                                    (456, 'AI: STOPPED | controlled 3 classes', 0xff96a5b6, 16)):
            mask = glyph_mask(label, ROOT / 'embedded/arm_panel/font8x12.h')
            gate('actual stopped pixels ' + label,
                 np.array_equal(pixels[y:y + 12, left:left + mask.shape[1]], np.where(mask, color, 0xff0c0e12).astype('<u4')))
        Image.frombytes('RGB', (800, 480), (files / 'fb.raw').read_bytes(), 'raw', 'BGRX').save(out / 'receiver-stopped.png')
        raw = (sp.parent / 'UART/uart.rx.bin').read_bytes()
        stop_packet = b'\x65\x00\x07\x00\xff\xff\xff' in raw
        r.update(status=('passed_P83_full_manual_three_sources_and_STOP'
                        if set(('bpsk', 'qpsk', 'qam16')) <= natural and bool(stops) and stop_packet
                        else 'passed_P83_observed_sources_and_cleanup_partial_coverage'),
                 observed_natural_signals=sorted(natural), missing_natural_signals=sorted(set(('bpsk', 'qpsk', 'qam16')) - natural),
                 raw_STOP_packet_present=stop_packet, actual_inflight_STOP=bool(stops) and stop_packet,
                 complete_three_class_and_STOP=set(('bpsk', 'qpsk', 'qam16')) <= natural and bool(stops) and stop_packet,
                 display_updates=summary['display_updates'], elapsed_software_s=summary['elapsed_software_s'],
                 max_display_interval_s=float(np.max(np.diff(times))))
    except Exception as error:
        r.update(status='failed_or_unconfirmed_P83_review', error=repr(error))
    (out / 'report.json').write_text(json.dumps(r, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(out, flush=True)
    print(r['status'], flush=True)
    return 0 if r['status'].startswith('passed_') else 1


if __name__ == '__main__':
    raise SystemExit(main())
