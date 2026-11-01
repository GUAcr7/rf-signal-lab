"""Known-modulation snapshot features; not blind AI or lossless streaming proof.

Uses the shared snapshot filter/guards and nominal constellation phase. QAM's
fourth moment is meaningful in expectation, not an exact per-symbol phasor.
Coarse orientation precedes PLL decisions, and residual gain phase is removed
afterwards. Each output is new; historical evidence is never overwritten.
"""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from rfsig.carrier_tracking import align_rotation,constellation,evm_db,track_carrier,refine_snapshot_carrier
from rfsig.iq_io import load_iq_dma_s16
from rfsig.symbol_recovery import recover_snapshot
from p21_track_and_measure import moment_carrier

ROOT=Path(__file__).resolve().parents[1]
FS=30_720_000
CASES=[(name,ROOT/f"results/{directory}/{case}.bin")
       for name,directory in (("bpsk","p22-transfer-20261017T131327Z"),
                              ("qpsk","p22-transfer-20261017T131922Z"),
                              ("qam16","p22-transfer-20261017T132355Z"))
       for case in ("big1","big2")]


def analyse(path,modulation,dma_buffer_samples=65536):
    x=load_iq_dma_s16(path,channels=4)
    if len(x)>dma_buffer_samples: raise ValueError("input crosses recorded DMA boundary")
    table=constellation(modulation)
    order=2 if len(table)==2 else 4
    carrier=moment_carrier(x,FS,order,50000,960000)
    recovered=recover_snapshot(x,FS,carrier,modulation)
    coarse,_=align_rotation(recovered.symbols,table)
    tracked=track_carrier(coarse,table,loop_bw=.02)
    causal_aligned,_=align_rotation(tracked.corrected,table)
    refined=refine_snapshot_carrier(coarse,table)
    aligned,rotation=align_rotation(refined.corrected,table)
    return {"source":str(path),"source_sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "modulation_supplied":modulation,"sample_rate_hz":FS,"dma_buffer_samples":dma_buffer_samples,
            "carrier_hz":carrier,"symbols":len(aligned),"timing_offset":recovered.timing_offset,
            "guard_samples_per_side":recovered.guard_samples,"residual_rotation_deg":rotation,
            "decision_evm_before_pll_db":evm_db(coarse,table),"decision_evm_after_causal_pll_db":evm_db(causal_aligned,table),
            "decision_evm_after_batch_fit_db":evm_db(aligned,table),
            "batch_residual_frequency_hz":refined.residual_frequency_rad_per_symbol*FS/128/(2*np.pi),
            "batch_uses_all_valid_symbols":True,
            "amplitude_cv":float(np.std(abs(aligned))/np.mean(abs(aligned))),
            "quadrature_suppression_after_alignment_db":float(10*np.log10(np.mean(aligned.real**2)/np.mean(aligned.imag**2)))}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--case",action="append",help="known modulation=raw path; four-channel DMA input")
    parser.add_argument("--dma-buffer-samples",type=int,default=65536)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    cases=[(name,Path(path)) for name,path in (item.split("=",1) for item in args.case)] if args.case else CASES
    rows=[analyse(path,name,args.dma_buffer_samples) for name,path in cases]
    out=args.output or ROOT/"results"/datetime.now(timezone.utc).strftime("p26-known-modulation-features-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"schema":"rfsig.known_modulation_features.v2","created_utc":datetime.now(timezone.utc).isoformat(),
            "cases":rows,"limits":["Modulation supplied to receiver; these are not blind classification results.",
                "Amplitude CV is rotation invariant; I/Q power ratio is not and requires the recorded alignment.",
                "No arbitrary 10 Hz accuracy requirement is implied; estimator tolerance depends on duration, SNR and target EVM."]}
    (out/"features.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    for row in rows: print(row["modulation_supplied"],Path(row["source"]).name,"batch EVM",round(row["decision_evm_after_batch_fit_db"],2))
    print(out)


if __name__=="__main__": main()
