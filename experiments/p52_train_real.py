"""Train grouped real RF; validation selects, test RF is deliberately not loaded."""
import argparse,json,time
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT,read,write,sha,rel
from rfsig.trainable_cnn import preprocess,patches,initialize,forward,loss_gradient
from rfsig.cnn_quantization import quantized_forward
from rfsig.real_rf_learning import augment_training,calibrate_real_training,validate_frame_groups

def metrics(y,pred):
    c=np.zeros((3,3),int)
    for a,b in zip(y,pred):c[a,b]+=1
    return dict(frames=len(y),correct=int(np.trace(c)),fraction_correct=float(np.mean(y==pred)),
        per_class_fraction_correct=[float(c[k,k]/c[k].sum()) for k in range(3)],confusion_rows_truth_cols_prediction=c.tolist())

def main():
    p=argparse.ArgumentParser();p.add_argument('--dataset',required=True,type=Path);p.add_argument('--plan',required=True,type=Path);args=p.parse_args()
    data=read(args.dataset);plan=read(args.plan)
    if data['status']!='passed_grouped_REAL_RF_training_validation_dataset_test_not_acquired' or data['test_frames']!=0:raise ValueError('grouped training/validation only')
    file=args.dataset.parent/'frames.npz'
    if sha(file)!=data['frame_file_sha256']:raise ValueError('dataset changed')
    validate_frame_groups(data['frame_records'])
    with np.load(file,allow_pickle=False) as z:frames=z['frames'];y=z['labels'];split=z['split']
    if set(split)!= {'train','validation'}:raise ValueError('test data forbidden during training')
    train=np.flatnonzero(split=='train');val=np.flatnonzero(split=='validation')
    augmented=augment_training(frames[train],seed=plan['training_seed']);labels=np.repeat(y[train],8)
    inputs=patches(preprocess(augmented));vp=patches(preprocess(frames[val]))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-trained-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    model=initialize(plan['training_seed']);m={k:np.zeros_like(v) for k,v in model.items()};v={k:np.zeros_like(x) for k,x in model.items()}
    rng=np.random.default_rng(plan['training_seed']+1);step=0;best_loss=float('inf');history=[];started=time.perf_counter()
    cfg=plan['training']
    for epoch in range(1,cfg['epochs']+1):
        order=rng.permutation(len(inputs));losses=[]
        for begin in range(0,len(order),cfg['batch']):
            ii=order[begin:begin+cfg['batch']];loss,g=loss_gradient(inputs[ii],labels[ii],model,cfg['l2']);losses.append(loss);step+=1
            for key in model:
                m[key]=.9*m[key]+.1*g[key];v[key]=.999*v[key]+.001*g[key]**2
                model[key]-=cfg['Adam_lr']*(m[key]/(1-.9**step))/(np.sqrt(v[key]/(1-.999**step))+1e-8)
        validation_loss=loss_gradient(vp,y[val],model,0)[0]
        row=dict(epoch=epoch,train_loss=float(np.mean(losses)),validation_loss=validation_loss,validation_fraction_correct=float(np.mean(np.argmax(forward(vp,model),1)==y[val])))
        history.append(row)
        if validation_loss<best_loss:best_loss=validation_loss;chosen=epoch;best={k:x.copy() for k,x in model.items()}
        if epoch%50==0:print(json.dumps(row),flush=True)
    model=best;quantized=calibrate_real_training(inputs,model)
    np.savez(out/'cnn-model.npz',**model);np.savez(out/'quantized-model.npz',**quantized)
    fp=forward(vp,model);qi=quantized_forward(vp,quantized)
    results=dict(fp32=metrics(y[val],np.argmax(fp,1)),int8=metrics(y[val],np.argmax(qi,1)))
    # Validation-only mode selection; ties favor the intended compact integer MAC.
    selected='int8' if results['int8']['correct']>=results['fp32']['correct'] else 'fp32'
    report=dict(status='trained_REAL_RF_validation_selected_test_not_acquired',dataset=rel(args.dataset),dataset_sha256=sha(args.dataset),plan=rel(args.plan),plan_sha256=sha(args.plan),
        class_order=data['class_order'],training_real_frames=len(train),training_augmented_frames=len(inputs),validation_real_frames=len(val),test_real_frames=0,
        architecture=plan['architecture'],parameters=115,selected_epoch=chosen,validation_cross_entropy=best_loss,validation=results,selected_mode=selected,
        selected_mode_rule='higher validation correct count; tie int8; selected before test capture',elapsed_s=time.perf_counter()-started,
        model_sha256=sha(out/'cnn-model.npz'),quantized_model_sha256=sha(out/'quantized-model.npz'),quantization_calibration_split='train_only',
        preprocessing_modulation_labels_used=False,independent_test_accuracy='not_yet_measured',AI_accepted=False,board_operations=False)
    write(out/'report.json',report);write(out/'history.json',history);print(out);print(report['status'])
if __name__=='__main__':main()
