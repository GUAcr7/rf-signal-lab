"""Measure real panel state readbacks; require full unchanged RF/history review."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,statistics,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
from board_control import sha

def read(p):return json.loads(Path(p).read_text('utf-8'))
def timings(screen):
    stamp=lambda x:datetime.fromisoformat(x).timestamp()
    result=[];events=screen['events'];buttons=screen['physical_events']
    for i,button in enumerate(buttons):
        action=button['effect']
        if action not in ('check','start','stop'):continue
        start=stamp(button['utc']);end=stamp(buttons[i+1]['utc']) if i+1<len(buttons) else float('inf')
        fields=[x for x in events if x['kind']=='field_readback' and x.get('component')=='t1' and start<=stamp(x['utc'])<end]
        target={'check':'READY','start':'RUNNING','stop':'IDLE'}[action]
        completed=next((x for x in fields if x['text']==target),None)
        if not fields or completed is None:raise ValueError('No matching state completion: '+action)
        result.append(dict(signal=button['signal'],action=action,feedback_s=stamp(fields[0]['utc'])-start,
                           completion_s=stamp(completed['utc'])-start))
    return result

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--screen',type=Path,required=True);ap.add_argument('--RF-review',type=Path,required=True);args=ap.parse_args()
    plan=read(ROOT/'results/p80-plan-20261027.json');base_path=ROOT/plan['baseline'];baseline=read(base_path)
    screen=read(args.screen);review=read(args.RF_review)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p80-latency-review-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='reviewing',screen=str(args.screen.resolve().relative_to(ROOT)),screen_sha256=sha(args.screen),
           baseline=str(base_path.relative_to(ROOT)),baseline_sha256=sha(base_path),
           RF_review=str(args.RF_review.resolve().relative_to(ROOT)),RF_review_sha256=sha(args.RF_review),
           plan_sha256=sha(ROOT/'results/p80-plan-20261027.json'),board_operations=False,gates=[])
    def gate(name,passed):
        r['gates'].append(dict(name=name,passed=bool(passed)))
        if not passed:raise ValueError(name)
    try:
        gate('verified real RF/history/pixels/cleanup unchanged',review['status']=='passed_P79_screen_protocol_RF_AI_history_cleanup'
             and all(x['passed'] for x in review['gates']))
        archive=read(ROOT/review['archive'])
        gate('review belongs to this closed fast session',sha(ROOT/archive['screen_report'])==sha(args.screen)
             and screen['fast_control'] and screen['serial_closed'] and screen['status']=='passed_P79_protocol_replay_RF_presets_and_cleanup')
        r['baseline_rows']=timings(baseline);r['optimized_rows']=timings(screen);r['summary']={}
        for action,count in (('check',4),('start',4),('stop',1)):
            old=[x['completion_s'] for x in r['baseline_rows'] if x['action']==action]
            new=[x['completion_s'] for x in r['optimized_rows'] if x['action']==action]
            gate('same action coverage '+action,len(old)==len(new)==count)
            r['summary'][action]=dict(samples=len(new),old_median_s=statistics.median(old),new_median_s=statistics.median(new),
                new_min_s=min(new),new_max_s=max(new),reduction_percent=100*(1-statistics.median(new)/statistics.median(old)))
        gate('declared APPLY median bound',r['summary']['check']['new_median_s']<=plan['limits_s']['check_median'])
        gate('declared START median bound',r['summary']['start']['new_median_s']<=plan['limits_s']['start_median'])
        gate('declared STOP maximum bound',r['summary']['stop']['new_max_s']<=plan['limits_s']['stop_max'])
        gate('all actions faster',all(x['new_median_s']<x['old_median_s'] for x in r['summary'].values()))
        r.update(status='passed_P80_button_latency_and_full_RF_regression',input_origin=screen['input_origin'],
                 complete_human_latency_rehearsal=False,new_independent_AI_accuracy=False,RF_groups=review['groups'])
    except Exception as error:r.update(status='failed_or_incomplete_P80_latency_review',error=repr(error))
    (out/'report.json').write_text(json.dumps(r,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(out,flush=True);print(r['status'],flush=True)
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
