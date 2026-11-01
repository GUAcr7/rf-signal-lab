"""Train the already-probed 115-parameter CNN; validation selects, test is frozen."""
import argparse,hashlib,json,platform,time
from pathlib import Path
from datetime import datetime,timezone
import numpy as np
from rfsig.synthetic_dataset import CLASSES,validate_records,array_hash
from rfsig.trainable_cnn import preprocess,patches,initialize,forward,loss_gradient
from rfsig.modulation_baseline import confusion

def main():
    ap=argparse.ArgumentParser();ap.add_argument('dataset',type=Path);ap.add_argument('--epochs',type=int,default=60);ap.add_argument('--validation-only',action='store_true');a=ap.parse_args();root=Path(__file__).resolve().parents[1]
    out=root/'results'/('p09-trained-cnn-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir()
    manifest=json.loads((a.dataset/'manifest.json').read_text());ver=json.loads((a.dataset/'verification.json').read_text());assert hashlib.sha256((a.dataset/'manifest.json').read_bytes()).hexdigest()==ver['manifest_sha256'];validate_records(manifest['records'])
    frames=[];labels=[];splits=[];snrs=[];parents=[];indices=[]
    for r in manifest['records']:
        file=a.dataset/r['file'];assert hashlib.sha256(file.read_bytes()).hexdigest()==r['file_sha256']
        with np.load(file,allow_pickle=False) as z:
            assert array_hash(z['noisy'])==r['noisy_sha256']
            for i,x in enumerate(z['noisy'].reshape(8,1024)):
                frames.append(x.copy());labels.append(CLASSES.index(r['modulation']));splits.append(r['split']);snrs.append(r['nominal_snr_db']);parents.append(r['record_id']);indices.append(i)
    x=preprocess(np.array(frames));p=patches(x);y=np.array(labels);splits=np.array(splits);snrs=np.array(snrs)
    train=np.flatnonzero(splits=='train');val=np.flatnonzero(splits=='validation');test=np.flatnonzero(splits=='test')
    assert (len(train),len(val),len(test))==(1008,216,216)
    seed=20261011;model=initialize(seed);rng=np.random.default_rng(seed+1);m={k:np.zeros_like(v) for k,v in model.items()};v={k:np.zeros_like(t) for k,t in model.items()}
    assert 1<=a.epochs<=1000
    epochs=a.epochs;batch=64;lr=.01;l2=.0001;step=0;best_loss=float('inf');history=[];start=time.perf_counter()
    for epoch in range(1,epochs+1):
        order=rng.permutation(train);losses=[]
        for begin in range(0,len(order),batch):
            ii=order[begin:begin+batch];loss,g=loss_gradient(p[ii],y[ii],model,l2);losses.append(loss);step+=1
            for k in model:
                m[k]=.9*m[k]+.1*g[k];v[k]=.999*v[k]+.001*g[k]**2
                model[k]-=lr*(m[k]/(1-.9**step))/(np.sqrt(v[k]/(1-.999**step))+1e-8)
        val_loss=loss_gradient(p[val],y[val],model,0)[0]
        row={'epoch':epoch,'train_objective':float(np.mean(losses)),'validation_cross_entropy':val_loss,'validation_accuracy':float(np.mean(np.argmax(forward(p[val],model),axis=1)==y[val]))};history.append(row)
        if val_loss<best_loss:best_loss=val_loss;best={k:t.copy() for k,t in model.items()};chosen=epoch
        if epoch%100==0 or epoch==epochs:print(json.dumps(row),flush=True)
    model=best;path=out/'cnn-model.npz';np.savez(path,**model)
    if a.validation_only:
        with np.load(path,allow_pickle=False) as z:np.testing.assert_allclose(forward(p[val],dict(z)),forward(p[val],model),rtol=0,atol=0)
        report={'status':'frozen_validation_selected_CNN_test_pending','architecture':'Conv1D 2->8 kernel5 stride2, ReLU, GAP510, Dense3','parameters':115,'parameter_dtype':'float32','class_order':list(CLASSES),'preprocessing':'per-frame DC subtraction and complex RMS normalization in FP64, cast FP32','training':{'seed':seed,'epochs':epochs,'batch':batch,'optimizer':'Adam','lr':lr,'l2':l2,'chosen_epoch':chosen,'validation_loss':best_loss,'validation_accuracy':float(np.mean(np.argmax(forward(p[val],model),axis=1)==y[val])),'elapsed_s':time.perf_counter()-start,'selection':'validation only; original v1 test was exposed by the earlier 60-epoch diagnostic, so final evaluation requires a new independent holdout'},'dataset':str(a.dataset.resolve()),'dataset_manifest_sha256':ver['manifest_sha256'],'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'weights_bytes':460,'split_frames':{'train':1008,'validation':216,'exposed_old_test_not_evaluated_here':216},'source':'SYNTHETIC_NOT_REAL_RF','test_accuracy':'pending_new_holdout','real_RF_accuracy':'not_measured','quantization':'pending','ARM_deployment':'pending','saved_model_replay_passed':True}
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'training-history.json').write_text(json.dumps(history,indent=2)+'\n');print(json.dumps({'out':str(out),'report':report}),flush=True);return
    prediction=np.argmax(forward(p,model),axis=1)
    with np.load(path,allow_pickle=False) as z:np.testing.assert_array_equal(np.argmax(forward(p,dict(z)),axis=1),prediction)
    def metrics(ii):
        cm=confusion(y[ii],prediction[ii]);return {'frames':len(ii),'accuracy':float(np.mean(y[ii]==prediction[ii])),'per_class_accuracy':{c:float(cm[j,j]/cm[j].sum()) for j,c in enumerate(CLASSES)},'confusion_rows_truth_cols_prediction':cm.tolist()}
    times=[]
    for idx in test[:100]:
        t=time.perf_counter_ns();forward(p[idx:idx+1],model);times.append((time.perf_counter_ns()-t)/1e6)
    np.savez_compressed(out/'evaluation.npz',truth=y,prediction=prediction,split=splits,nominal_snr=snrs,record_id=np.array(parents),frame_index=np.array(indices),logits=forward(p,model))
    report={'status':'trained_CNN_synthetic_only','architecture':'1024x2 -> valid Conv1D(2,8,kernel5,stride2) -> ReLU -> GAP(510) -> Dense3','parameters':sum(t.size for t in model.values()),'parameter_dtype':'float32','class_order':list(CLASSES),'preprocessing':'subtract per-frame complex DC and divide by complex RMS; float64 preprocessing then FP32 channels; tap-major I/Q patches','training':{'seed':seed,'epochs':epochs,'batch':batch,'optimizer':'Adam','lr':lr,'l2':l2,'chosen_epoch':chosen,'selection':'minimum validation cross-entropy; test does not select models','elapsed_s':time.perf_counter()-start},'dataset':str(a.dataset.resolve()),'dataset_manifest_sha256':ver['manifest_sha256'],'split_frames':{'train':1008,'validation':216,'test':216},'split_parents':{'train':126,'validation':27,'test':27},'evaluation':{name:metrics(ii) for name,ii in [('train',train),('validation',val),('test',test)]},'test_by_nominal_snr':{str(s):metrics(test[snrs[test]==s]) for s in [10,15,20]},'model_sha256':hashlib.sha256(path.read_bytes()).hexdigest(),'weights_bytes':sum(t.nbytes for t in model.values()),'desktop_forward_ms':{'mean':float(np.mean(times)),'p95':float(np.quantile(times,.95)),'scope':'forward only; preprocessing/windowing excluded'},'quantization':'not_performed','ARM_deployment':'pending','real_RF_accuracy':'not_measured','source':'SYNTHETIC_NOT_REAL_RF','saved_model_replay_passed':True,'numpy':np.__version__,'python':platform.python_version()}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');(out/'training-history.json').write_text(json.dumps(history,indent=2)+'\n');print(json.dumps({'out':str(out),'report':report}),flush=True)
if __name__=='__main__':main()
