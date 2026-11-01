"""Prospectively fixed validation gate; exposed P73 event diagnostics afterward.

Never reads original independent P52 heldout files. Candidate, data selection,
and acceptance gate are saved before evaluation. No board or production writes.
"""
import argparse
import time
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT, read, write, sha, rel
from p74_phase_pool import PHASE_DEGREES, phase_pool_logits, three_frame_consensus
from rfsig.trainable_cnn import preprocess, patches
from rfsig.cnn_quantization import quantized_forward
from p37_review_archives import decode_rx12
from rfsig.rf_ai_calibration import adapt_calibrated

PROTOCOL = dict(
    candidate='fixed8_phase_group_mean_logits_INT8_then_unchanged_3_of_3',
    phase_degrees=list(PHASE_DEGREES), aggregation='arithmetic_mean_logits_per_frame',
    model_weights_fit=False, thresholds_changed=False,
    selection_data='original P52 validation split only, no frame reshuffle',
    original_independent_test_read=False,
    validation_gate=dict(overall_accuracy_min=.90, each_class_accuracy_min=.80,
                         no_overall_or_per_class_regression=True),
    exposed_event_gate=dict(required_all_original_CLASSIFIED_preserved=True,
                           uncertain_improvement_min_blocks=1,
                           accepted_wrong_allowed=0),
    no_deployment=True,
    limit='validation and P73 events are exposed; no new independent accuracy claim')


def score(logits, labels):
    pred = logits.argmax(axis=1)
    matrix = np.zeros((3, 3), dtype=int)
    for y, p in zip(labels, pred):
        matrix[int(y), int(p)] += 1
    return dict(correct=int(np.sum(pred == labels)), total=len(labels),
                accuracy=float(np.mean(pred == labels)), confusion=matrix.tolist(),
                each_class_accuracy=[float(matrix[k, k] / matrix[k].sum()) for k in range(3)],
                predictions=pred.tolist())


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--review', type=Path, required=True)
    a = ap.parse_args()
    out = ROOT / 'results' / datetime.now(timezone.utc).strftime('p74-offline-%Y%m%dT%H%M%SZ')
    out.mkdir()
    protocol = dict(PROTOCOL, candidate_sha256=sha(ROOT/'experiments/p74_phase_pool.py'),
                    evaluator_sha256=sha(Path(__file__)))
    write(out/'protocol.json', protocol)
    r = dict(status='evaluating_P74_offline_candidate', protocol=protocol,
             protocol_sha256=sha(out/'protocol.json'), board_operations=False,
             production_changed=False, gates=[])

    def gate(name, ok):
        r['gates'].append(dict(name=name, passed=bool(ok)))
        if not ok:
            raise ValueError(name)

    try:
        frozen = read(ROOT/'results/p52-export-20261024T043113Z/report.json')
        for item in frozen['frozen_inputs'].values():
            gate('frozen SHA '+item['path'], sha(ROOT/item['path']) == item['sha256'])
        dataset_report = read(ROOT/frozen['frozen_inputs']['dataset']['path'])
        dataset = ROOT/'results/p54-plan-20261024T042837Z/dataset/frames.npz'
        expected = 'b5d9e6474e165936482563e28586f2813d46e4e52338d94af9ba56dca7108aeb'
        gate('original dataset SHA', sha(dataset) == expected)
        r['dataset_report_keys'] = sorted(dataset_report)
        with np.load(ROOT/frozen['frozen_inputs']['quantized']['path'], allow_pickle=False) as z:
            quantized = dict(z)
        with np.load(dataset, allow_pickle=False) as z:
            mask = z['split'] == 'validation'
            frames, labels, seeds = z['frames'][mask], z['labels'][mask], z['seed'][mask]
            train_seeds = set(z['seed'][z['split'] == 'train'].tolist())
        gate('validation-only 54 frames balanced and seed-disjoint',
             len(frames) == 54 and np.bincount(labels, minlength=3).tolist() == [18]*3
             and train_seeds.isdisjoint(set(seeds.tolist())))
        t0 = time.perf_counter()
        baseline = quantized_forward(patches(preprocess(frames)), quantized)
        r['baseline_wall_s'] = time.perf_counter() - t0
        t0 = time.perf_counter()
        candidate = phase_pool_logits(frames, quantized)
        r['candidate_wall_s'] = time.perf_counter() - t0
        r['validation'] = dict(baseline=score(baseline, labels), candidate=score(candidate, labels),
                               seeds=seeds.tolist())
        np.savez_compressed(out/'validation-logits.npz', labels=labels, seeds=seeds,
                            baseline_logits=baseline, candidate_logits=candidate)
        b, c = r['validation']['baseline'], r['validation']['candidate']
        passed_validation = (c['accuracy'] >= .90 and min(c['each_class_accuracy']) >= .80
                             and c['correct'] >= b['correct']
                             and all(cv >= bv for cv, bv in zip(c['each_class_accuracy'], b['each_class_accuracy'])))
        r['validation_candidate_gate_passed'] = passed_validation
        # Group invariance is a mechanistic control, not a new RF accuracy score.
        deviations = []
        for degrees in PHASE_DEGREES:
            rotated = phase_pool_logits(frames*np.exp(1j*np.deg2rad(degrees)), quantized)
            deviations.append(dict(degrees=degrees, max_logit_difference=float(abs(candidate-rotated).max()),
                                   predictions_identical=bool(np.array_equal(rotated.argmax(axis=1), candidate.argmax(axis=1)))))
        r['phase_group_control'] = deviations
        gate('all 8 group rotations preserve validation predictions', all(d['predictions_identical'] for d in deviations))
        # Same normalized input with positive scale and static DC offset.
        affine = phase_pool_logits(frames*4 + (3+2j), quantized)
        r['affine_control'] = dict(max_logit_difference=float(abs(candidate-affine).max()),
            predictions_identical=bool(np.array_equal(affine.argmax(axis=1), candidate.argmax(axis=1))))
        gate('normalization control preserves predictions', r['affine_control']['predictions_identical'])
        if not passed_validation:
            r.update(status='rejected_P74_validation_gate_no_deployment',
                     next_step='retain original inference; do not tune this candidate on P73 labels')
        else:
            # Only now expose the already diagnosed P73 events for regression.
            review = read(a.review)
            gate('P73 actual events reviewed', review['status'] == 'completed_P73_same_update_events_full_history_and_frozen_replay')
            trial_path = ROOT/review['trial']
            gate('P73 trial SHA', sha(trial_path) == review['trial_sha256'])
            trial = read(trial_path)
            r.update(review=rel(a.review), review_sha256=sha(a.review), events=[])
            files = trial_path.parent/'files'
            for event in trial['events']:
                base = f'event-{event["id"]:02d}'
                ai = read(files/(base+'.json'))
                raw = files/(base+'.bin')
                gate('P73 raw SHA '+base, sha(raw) == trial['files_sha256'][raw.name])
                pairs = decode_rx12(raw.read_bytes())
                iq = pairs[:,0].astype(float) + 1j*pairs[:,1]
                calibration = dict(status='known_tone_common_IF_calibrated', frequency_hz=ai['common_IF_hz'],
                    shared_across_modulation_classes=True, modulation_labels_used=False)
                frames, _ = adapt_calibrated(iq, sample_rate_hz=30720000, calibration=calibration)
                frames = np.asarray(frames, dtype=np.complex64)
                base_logits = quantized_forward(patches(preprocess(frames)), quantized)
                original = three_frame_consensus(base_logits)
                gate('P73 frozen replay '+base, original['predictions'] == ai['raw_predictions'])
                pooled = phase_pool_logits(frames, quantized)
                row = dict(event=base, original_state=ai['state'], baseline=original,
                           candidate=three_frame_consensus(pooled), candidate_logits=pooled.tolist())
                r['events'].append(row)
            fixed = [e for e in r['events'] if e['original_state'] == 'UNCERTAIN']
            normal = [e for e in r['events'] if e['original_state'] == 'CLASSIFIED']
            r['exposed_event_summary'] = dict(original_uncertain=len(fixed),
                now_correct_consensus=sum(e['candidate']['accepted_class'] == 2 for e in fixed),
                now_uncertain=sum(e['candidate']['accepted_class'] == -1 for e in fixed),
                original_classified_preserved=sum(e['candidate']['accepted_class'] == 2 for e in normal),
                original_classified=len(normal),
                wrong_accepted=sum(e['candidate']['accepted_class'] not in (-1, 2) for e in r['events']))
            s = r['exposed_event_summary']
            event_pass = (s['now_correct_consensus'] >= 1 and s['wrong_accepted'] == 0
                          and s['original_classified_preserved'] == len(normal))
            r.update(status=('passed_P74_offline_candidate_requires_native_parity_fresh_RF'
                             if event_pass else 'rejected_P74_exposed_event_regression_no_deployment'),
                     exposed_event_gate_passed=event_pass,
                     next_step='native C parity and latency, then prospectively frozen new RF sessions; no production change')
    except Exception as exc:
        r.update(status='failed_P74_offline_evaluation', error=repr(exc))
    write(out/'report.json', r)
    print(out)
    print(r['status'])


if __name__ == '__main__':
    main()
