"""Known-source metrology on every archived DMA buffer; never concatenate gaps."""
import argparse,hashlib,json
from datetime import datetime,timezone
from pathlib import Path
from dataclasses import asdict
import numpy as np
from p32_session import ROOT
from p37_review_archives import archive_bytes,decode_rx12
from p21_track_and_measure import moment_carrier
from rfsig.real_rf_reference import reproduce_reference
from rfsig.reference_receiver import measure_known_snapshot
from rfsig.capture_continuity import modulo_gaps
from rfsig.saturation import iq_power_stats

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--archives',type=Path,required=True);args=p.parse_args()
    archives=read(args.archives);trial_path=Path(archives['trial']);trial=read(trial_path)
    if archives['status']!='passed_all_known_source_raw_buffers_archived' or sha(trial_path)!=archives['trial_sha256']:raise ValueError('all original RF buffers must be archived')
    sources_path=Path(trial['source_report']);sources=read(sources_path);original=Path(sources['source_report']).parent
    if sha(sources_path)!=trial['source_report_sha256']:raise ValueError('source proof changed')
    plan_path=ROOT/'results/p46-quality-plan-20261022.json';plan=read(plan_path)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-analysis-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    report=dict(status='analysing',archives=str(args.archives.resolve()),archives_sha256=sha(args.archives),trial=str(trial_path),trial_sha256=sha(trial_path),
        plan=str(plan_path),plan_sha256=sha(plan_path),cases=[],RF_operations=False,lossless_proven=False,blind_AI=False,
        scope='Known modulation and exact TX symbols supplied; carrier/source fits use whole DMA window. Second-half decisions are not independent BER.',
        source_seed_shared_across_windows=True,absolute_power_calibrated=False,absolute_frequency_calibrated=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    import matplotlib;matplotlib.use('Agg')
    import matplotlib.pyplot as plt
    fig,axes=plt.subplots(4,2,figsize=(12,12),layout='constrained');save()
    for index,entry in enumerate(archives['cases']):
        name=entry['name'];capture=next(c for c in trial['cases'] if c['name']==name);archive=Path(entry['report'])
        if sha(archive)!=entry['report_sha256']:raise ValueError('archive proof changed')
        meta,raw=archive_bytes(archive)
        if meta['expected_boot']!=trial['expected_boot'] or len(raw)!=capture['raw_bytes'] or meta['verified_raw_sha256']!=capture['raw_sha256']:raise ValueError('mixed acquisition')
        pairs=decode_rx12(raw);iq=pairs[:,0].astype(float)+1j*pairs[:,1]
        ref=sources['references'][name];mode={'bpsk':'BPSK','qpsk':'QPSK','qam16':'16QAM','tone':'tone'}[name]
        wave=reproduce_reference(ref,(original/name).read_bytes())
        row=dict(name=name,archive=str(archive),complete_frames=len(iq),buffers=[],source_bytes_reproduced=True,
            no_cross_DMA_filtering=True,ADC_gaps='unknown');report['cases'].append(row);all_good=True;starts=[]
        for b in range(capture['blocks']):
            x=iq[b*65536:(b+1)*65536]
            if len(x)!=65536:raise ValueError('incomplete buffer')
            stats=asdict(iq_power_stats(x,2048,positive_rail=2047));result=dict(buffer=b,stats=stats)
            row['buffers'].append(result)
            try:
                if name=='tone':
                    frequency=moment_carrier(x,30720000,1,50000,960000)
                    z=x*np.exp(-2j*np.pi*frequency*np.arange(len(x))/30720000);gain=z.mean()
                    residual=float(np.mean(abs(z-gain)**2));nmse=10*np.log10(max(residual/(abs(gain)**2),1e-30))
                    result.update(carrier_hz=frequency,carrier_offset_from_nominal_hz=frequency-960000,tone_residual_nmse_db=float(nmse))
                    good=abs(frequency-960000)<=50000 and stats['endpoint_fraction']==0
                else:
                    hint=moment_carrier(x,30720000,2 if name=='bpsk' else 4,50000,960000)
                    measured=measure_known_snapshot(x,wave,hint,dma_buffer_samples=65536)
                    result.update(carrier_hz=measured.alignment.frequency_hz,waveform_correlation=measured.alignment.correlation,
                        source_start_modulo_period=measured.alignment.source_start,raw_waveform_nmse_db=measured.alignment.nmse_db,
                        reference_evm_db=measured.evm_db,valid_symbols=len(measured.recovered.symbols),guard_per_side=measured.recovered.guard_samples,
                        checked_symbols=measured.checked_symbols,symbol_errors=measured.symbol_errors)
                    starts.append(measured.alignment.source_start)
                    good=(measured.alignment.correlation>=plan['each_modulation_required_waveform_correlation_min']
                        and measured.evm_db<=plan['each_modulation_required_reference_evm_db_max']
                        and measured.symbol_errors<=plan['each_modulation_second_half_symbol_errors_max'] and stats['endpoint_fraction']==0)
                    if b==0:
                        syms=measured.recovered.symbols;expected=measured.expected_symbols
                        gain=np.vdot(expected,syms)/np.vdot(expected,expected)
                        axes[index,1].scatter((syms/gain).real,(syms/gain).imag,s=5,alpha=.5)
                        axes[index,1].set_title(name+' first DMA constellation (known reference)')
                result.update(status='passed' if good else 'quality_threshold_failed');all_good=all_good and good
            except Exception as e:result.update(status='fit_rejected',error=str(e));all_good=False
        if len(starts)==capture['blocks']:
            gaps=modulo_gaps(starts,65536,131072);signed=[int(v if v<65536 else v-131072) for v in gaps]
            row.update(extra_source_advance_modulo_period=signed,nonperiod_jumps_detected=sum(abs(v)>1 for v in signed),whole_period_loss_unobservable=True)
        row['status']='passed_known_source_snapshot_quality' if all_good else 'known_source_quality_failed'
        if name!='tone':
            evms=[v['reference_evm_db'] for v in row['buffers'] if 'reference_evm_db' in v]
            row.update(evm_min_db=min(evms) if evms else None,evm_max_db=max(evms) if evms else None,
                total_checked_symbols=sum(v.get('checked_symbols',0) for v in row['buffers']),total_symbol_errors=sum(v.get('symbol_errors',0) for v in row['buffers']))
        first=iq[:65536];psd=abs(np.fft.fftshift(np.fft.fft(first*np.hanning(len(first)))))**2
        f=np.fft.fftshift(np.fft.fftfreq(len(first),1/30720000))/1e6
        axes[index,0].plot(f,10*np.log10(np.maximum(psd/psd.max(),1e-12)));axes[index,0].set_xlim(.6,1.3);axes[index,0].set_ylim(-90,3)
        axes[index,0].set_title(name+' spectrum relative to this record peak');axes[index,0].set_xlabel('Baseband frequency offset (MHz)')
        axes[index,1].grid(alpha=.3)
        if name=='tone':
            axes[index,1].plot([v['buffer'] for v in row['buffers']],[v['carrier_hz']-960000 for v in row['buffers']],'o-')
            axes[index,1].set_title('Tone offset from nominal (uncalibrated RF clocks)');axes[index,1].set_ylabel('Hz')
        save();print(name,row['status'],row.get('evm_min_db'),row.get('evm_max_db'),flush=True)
    fig.suptitle('Known RF sources on merged receiver | all original DMA windows retained | not blind AI')
    fig.savefig(out/'quality.png',dpi=140);plt.close(fig)
    report['status']='passed_all_known_source_snapshot_quality' if all(c['status']=='passed_known_source_snapshot_quality' for c in report['cases']) else 'known_source_quality_failed'
    report['plot']=str(out/'quality.png');report['inputs_sha256']={str(p.relative_to(ROOT)):sha(p) for p in [Path(__file__),ROOT/'src/rfsig/reference_receiver.py',ROOT/'src/rfsig/capture_continuity.py',ROOT/'src/rfsig/symbol_recovery.py']};save();print(out);print(report['status'])
    return 0 if report['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
