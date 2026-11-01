"""Create an explicit calibrated diagnostic fork, retaining the nominal-IF experiment."""
from pathlib import Path
from p32_session import ROOT

def main():
    source=(ROOT/'experiments/p51_ai_diagnostic.py').read_text('utf-8')
    changes=[
        ('from p45_checkpoint import ROOT,read,write,sha,rel','from p45_checkpoint import ROOT,read,write,sha,rel\nfrom rfsig.rf_ai_calibration import adapt_calibrated'),
        ('def freeze():','def freeze(calibration_path):'),
        ('paths=dict(model=',"paths=dict(calibration=calibration_path,calibrated_adapter=ROOT/'src/rfsig/rf_ai_calibration.py',model="),
        ("frequency_fitting='none; common nominal controlled IF'","frequency_fitting='one tone-only common calibration; no per-class fits'"),
        ("write(out/'report.json',plan);print(out);return out/'report.json'","plan['protocol']['common_calibrated_IF_hz']=read(calibration_path)['calibration']['frequency_hz']\n    write(out/'report.json',plan);print(out);return out/'report.json'"),
        ('all_frames=[];truth=[];frame_ids=[]',"calibration=read(inputs['calibration'])['calibration']\n    all_frames=[];truth=[];frame_ids=[]"),
        ('adapt_dma_block(x,sample_rate_hz=SAMPLE_RATE_HZ,nominal_if_hz=NOMINAL_IF_HZ)',
            'adapt_calibrated(x,sample_rate_hz=SAMPLE_RATE_HZ,calibration=calibration)'),
        ('p51-ai-plan-','p51-ai-tone-plan-'),('p51-ai-diagnostic-','p51-ai-tone-diagnostic-'),
        ('independent_source_periods_per_class=1','unique_transmitted_waveforms_per_class=1'),
        ('p=argparse.ArgumentParser(description=__doc__);g=',"p=argparse.ArgumentParser(description=__doc__);p.add_argument('--calibration',type=Path);g="),
        ('if args.freeze_plan:freeze()',"if args.freeze_plan:\n        if not args.calibration:p.error('tone calibration required before freezing')\n        freeze(args.calibration)")]
    for old,new in changes:
        if source.count(old)!=1:raise ValueError('diagnostic source contract changed: '+old)
        source=source.replace(old,new,1)
    compile(source,'p51_ai_tone_diagnostic.py','exec')
    target=ROOT/'experiments/p51_ai_tone_diagnostic.py'
    if target.exists():raise ValueError('calibrated source already exists; do not overwrite')
    target.write_text(source,encoding='utf-8');print(target)

if __name__=='__main__':main()
