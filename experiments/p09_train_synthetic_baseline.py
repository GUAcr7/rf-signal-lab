"""Train a fixed traditional baseline; choose with validation, evaluate test once."""
import argparse,hashlib,json,platform,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from rfsig.synthetic_dataset import CLASSES,validate_records,array_hash
from rfsig.modulation_baseline import features,FEATURE_NAMES,loss_gradient,confusion

def main():
    parser=argparse.ArgumentParser();parser.add_argument('dataset',type=Path);a=parser.parse_args()
    root=Path(__file__).resolve().parents[1];out=root/'results'/('p09-synthetic-baseline-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
    manifest=json.loads((a.dataset/'manifest.json').read_text());verification=json.loads((a.dataset/'verification.json').read_text())
    assert manifest['source']=='SYNTHETIC_NOT_REAL_RF'
    assert hashlib.sha256((a.dataset/'manifest.json').read_bytes()).hexdigest()==verification['manifest_sha256']
    assert validate_records(manifest['records'])['records']==180
    split_manifest=json.loads((a.dataset/'split-manifest.json').read_text())
    rows=[];labels=[];splits=[];snrs=[];record_ids=[];indices=[]
    for r in manifest['records']:
        assert r['record_id'] in split_manifest[r['split']]
        file=a.dataset/r['file'];assert hashlib.sha256(file.read_bytes()).hexdigest()==r['file_sha256']
        with np.load(file,allow_pickle=False) as z:
            x=z['noisy'];assert array_hash(x)==r['noisy_sha256']
            for n,frame in enumerate(x.reshape(r['frames'],1024)):
                assert array_hash(frame)==r['frame_sha256'][n]
                rows.append(features(frame));labels.append(CLASSES.index(r['modulation']));splits.append(r['split']);snrs.append(r['nominal_snr_db']);record_ids.append(r['record_id']);indices.append(n)
    x=np.array(rows);y=np.array(labels);splits=np.array(splits);snrs=np.array(snrs)
    train=splits=='train';val=splits=='validation';test=splits=='test'
    assert (train.sum(),val.sum(),test.sum())==(1008,216,216)
    mean=x[train].mean(axis=0);scale=x[train].std(axis=0);scale=np.maximum(scale,1e-8);xn=(x-mean)/scale
    seed=20261011;rng=np.random.default_rng(seed);w=rng.normal(0,.01,(len(FEATURE_NAMES),3));b=np.zeros(3)
    mw=np.zeros_like(w);vw=np.zeros_like(w);mb=np.zeros_like(b);vb=np.zeros_like(b);history=[];best=None;best_val=float('inf')
    lr=.03;l2=.001;iterations=800
    for step in range(1,iterations+1):
        loss,dw,db=loss_gradient(xn[train],y[train],w,b,l2)
        mw=.9*mw+.1*dw;vw=.999*vw+.001*dw*dw;mb=.9*mb+.1*db;vb=.999*vb+.001*db*db
        w-=lr*(mw/(1-.9**step))/(np.sqrt(vw/(1-.999**step))+1e-8)
        b-=lr*(mb/(1-.9**step))/(np.sqrt(vb/(1-.999**step))+1e-8)
        if step%20==0:
            val_loss=loss_gradient(xn[val],y[val],w,b,0)[0]
            history.append({'iteration':step,'train_objective':loss,'validation_loss':val_loss})
            if val_loss<best_val:best_val=val_loss;best=(w.copy(),b.copy(),step)
    w,b,chosen=best
    model=out/'linear-model.npz';np.savez(model,weights=w,bias=b,feature_mean=mean,feature_scale=scale)
    model_hash=hashlib.sha256(model.read_bytes()).hexdigest()
    # No test labels are used by training, scaling, or checkpoint selection above.
    prediction=np.argmax(xn@w+b,axis=1)
    def metrics(mask):
        m=confusion(y[mask],prediction[mask]);return {'frames':int(mask.sum()),'accuracy':float(np.mean(prediction[mask]==y[mask])),'per_class_accuracy':{c:float(m[j,j]/m[j].sum()) for j,c in enumerate(CLASSES)},'confusion_rows_truth_cols_prediction':m.tolist()}
    evaluation={'train':metrics(train),'validation':metrics(val),'test':metrics(test),'test_by_nominal_snr':{str(snr):metrics(test&(snrs==snr)) for snr in [10,15,20]}}
    times=[]
    for frame in xn[test][:100]:
        start=time.perf_counter_ns();np.argmax(frame@w+b);times.append((time.perf_counter_ns()-start)/1e6)
    with np.load(model,allow_pickle=False) as saved:
        replay=np.argmax(((x-saved['feature_mean'])/saved['feature_scale'])@saved['weights']+saved['bias'],axis=1)
        assert np.array_equal(replay,prediction)
    np.savez_compressed(out/'evaluation-predictions.npz',truth=y,prediction=prediction,split=splits,nominal_snr=snrs,record_id=np.array(record_ids),frame_index=np.array(indices))
    report={'status':'completed_synthetic_traditional_baseline_only','model_type':'14 hand-crafted features + linear softmax, FP64 desktop','feature_names':list(FEATURE_NAMES),'parameters':45,'training':{'seed':seed,'iterations':iterations,'optimizer':'full-batch Adam','learning_rate':lr,'l2':l2,'chosen_iteration':chosen,'selection':'lowest validation cross-entropy; test evaluated once after freezing'},'dataset':str(a.dataset.resolve()),'dataset_manifest_sha256':verification['manifest_sha256'],'source':'SYNTHETIC_NOT_REAL_RF','split':{'train':1008,'validation':216,'test':216},'evaluation':evaluation,'model_sha256':model_hash,'saved_model_replay_passed':True,'desktop_linear_head_only_ms':{'mean':float(np.mean(times)),'p95':float(np.quantile(times,.95)),'scope':'feature extraction and IO excluded; ARM unmeasured'},'quantization':'not_performed','ARM_deployment':'not_performed','real_RF_accuracy':'not_measured','reject_unknown_signal':'not_implemented','confidence_calibration':'not_performed','numpy':np.__version__,'python':platform.python_version()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'training-history.json').write_text(json.dumps(history,indent=2)+'\n')
    print(json.dumps({'out':str(out),'evaluation':evaluation,'model_sha256':model_hash}))

if __name__=='__main__':main()
