"""Freeze real-RF collection/training/evaluation protocol before acquiring new data."""
import json,hashlib
from pathlib import Path
from datetime import datetime,timezone
from p45_checkpoint import ROOT,read,write,sha,rel
from p51_prepare_rf_bank import validate_splits
from p46_restore_tx import validate_source_package

def main():
    bank_path=ROOT/'results/p51-rf-bank-20261023T152633Z/report.json';bank=read(bank_path);validate_splits(bank['groups'])
    rows=[]
    import numpy as np
    rng=np.random.default_rng(20261024)
    for item in bank['groups']:
        path=ROOT/item['package'];meta,_,_=validate_source_package(path)
        if sha(path)!=item['package_sha256'] or meta['seed']!=item['seed']:raise ValueError('source bank changed')
        rows.append(dict(item,case_order=['tone',*rng.permutation(['bpsk','qpsk','qam16']).tolist()]))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-plan-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    plan=dict(status='frozen_before_new_RF_acquisition',source_bank=rel(bank_path),source_bank_sha256=sha(bank_path),groups=rows,
        conditions=bank['conditions'],blocks_per_case=2,frames_per_AI_block=3,frame_length=1024,
        TX_seconds=15,TX_peak_limit=256,RF_gain_changes_allowed=False,
        training_seed=20261024,architecture='existing Conv8 kernel5 stride2 GAP Dense3; new trainable weights',
        training=dict(epochs=300,batch=64,Adam_lr=.005,l2=.0001,selection='minimum validation cross-entropy',
            train_augmentation='8 copies per real frame with independent complex phase, CFO +/-3000Hz and 30dB synthetic additive noise; augmented copies stay train only'),
        quantization='scales derived from augmented training patches only; validation compares frozen FP32/INT8',
        adapter='P51 fixed anti-alias frontend; per-session tone-only common IF, no per-class correction',
        split_unit='source seed and bounded capture session; never adjacent frame random split',
        test_policy='test role RF not acquired until model/preprocessor/quantization/C export frozen',
        pass_gate=dict(heldout_overall_accuracy_min=.9,heldout_each_class_accuracy_min=.8,C_Python_predictions_identical=True),
        scope='three known classes at single fixed symbol rate/IF/gains; no measured SNR or arbitrary signal/unknown rejection claim',
        old_P46_data='diagnostic only; excluded from training/validation/test',
        physical_link=dict(source='direct_user_reply',answer='两板已供电，原接线已恢复',old_TX1_to_new_RX1A_same_connection_confirmed=True),
        board_operations=False,real_RF_acquired=False)
    write(out/'report.json',plan);print(out/'report.json')
if __name__=='__main__':main()
