"""Explicit derived runners; original P46 controls and evidence remain unchanged."""
from pathlib import Path
from p45_checkpoint import ROOT

def change(text,old,new):
    if text.count(old)!=1:raise ValueError('changed P46 source anchor')
    return text.replace(old,new,1)

def main():
    text=(ROOT/'experiments/p46_known_source.py').read_text()
    text=change(text,"p.add_argument('--source-report',type=Path,required=True);", "p.add_argument('--plan',type=Path,required=True);p.add_argument('--source-report',type=Path,required=True);")
    text=change(text,"origin=Path(sources['source_report'])", """origin=Path(sources['source_report'])
    plan=read(args.plan);package=read(origin)
    if plan['status']!='frozen_before_new_RF_acquisition' or args.blocks!=plan['blocks_per_case']:raise ValueError('frozen capture plan required')
    groups=[g for g in plan['groups'] if g['seed']==package.get('seed')]
    if len(groups)!=1 or sha(origin.read_bytes())!=groups[0]['package_sha256'] or cases!=groups[0]['case_order']:raise ValueError('planned seed/source/order mismatch')""")
    text=change(text,"read(ROOT/'results/p46-human-RF-link-20261022.json')", "plan['physical_link']")
    text=change(text,"('p46-known-'+stamp)","('p52-known-'+stamp)")
    text=change(text,'TX_duration_limit_s=30','TX_duration_limit_s=15')
    text=change(text,"./guard --run $p $n $f $l $w -10 30 $b A $h RF_LINK_REVIEWED", "./guard --run $p $n $f $l $w -10 15 $b A $h RF_LINK_REVIEWED")
    text=text.replace('CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=30','CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=15')
    text=change(text,"start=tx.read(10,", "submitted_host=time.monotonic();start=tx.read(10,")
    text=change(text,"case['native_start'],case['native_completion']=validate_completion(result,args.blocks)","""case['native_start'],case['native_completion']=validate_completion(result,args.blocks)
            case['host_capture_completed_after_submission_s']=time.monotonic()-submitted_host
            if case['host_capture_completed_after_submission_s']>=14:raise ValueError('capture not conservatively inside 15-second TX window')""")
    text=change(text,"lossless_proven=False,known_source_diagnostic_only=True", "plan=str(args.plan.resolve()),plan_sha256=sha(args.plan.read_bytes()),seed=package['seed'],split=groups[0]['role'],capture_session=groups[0]['planned_capture_session'],lossless_proven=False,known_source_diagnostic_only=True")
    target=ROOT/'experiments/p52_capture_sources.py'
    if target.exists():raise FileExistsError(target)
    target.write_text(text,encoding='utf-8')
    text=(ROOT/'experiments/p46_analyse.py').read_text()
    text=change(text,'from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16','from rfsig.real_rf_reference import reproduce_reference')
    old="""wave=make_tx_waveform(mode,sample_rate_hz=30720000,samples_per_symbol=128,symbol_count=1024,seed=20261016,
            offset_hz=960000,digital_peak_counts=256,rolloff=.35,span_symbols=10)
        if pack_tx_iq_le16(wave.iq)!=(original/name).read_bytes():raise ValueError('exact TX reference no longer reproducible')"""
    text=change(text,old,"wave=reproduce_reference(ref,(original/name).read_bytes())")
    text=change(text,"('p46-analysis-%Y%m%dT%H%M%SZ')","('p52-analysis-%Y%m%dT%H%M%SZ')")
    target=ROOT/'experiments/p52_analyse_sources.py'
    if target.exists():raise FileExistsError(target)
    target.write_text(text,encoding='utf-8')
    print('Two explicit derived runners prepared; no board access')
if __name__=='__main__':main()
