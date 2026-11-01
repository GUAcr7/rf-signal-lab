"""Validate small-versus-single-buffer captures against the known TX waveform."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from rfsig.capture_continuity import align_periodic_reference,modulo_gaps
from rfsig.carrier_tracking import constellation,evm_db,reference_evm_db
from rfsig.iq_io import load_iq_dma_s16
from rfsig.symbol_recovery import recover_snapshot
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16

ROOT=Path(__file__).resolve().parents[1]
FS=30_720_000
SPS=128


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer",required=True,type=Path)
    args=parser.parse_args()
    transport=json.loads((args.transfer/"report.json").read_text("utf-8"))
    if transport["status"]!="all_payloads_verified":
        raise RuntimeError("transport not verified")
    acquisition=json.loads((Path(transport["source"])/"report.json").read_text("utf-8"))
    name=acquisition["modulation"]
    mod={"bpsk":"BPSK","qpsk":"QPSK","qam16":"16QAM"}[name]
    tx=make_tx_waveform(mod,sample_rate_hz=FS,samples_per_symbol=SPS,symbol_count=1024,
                        seed=20261016,offset_hz=960000,digital_peak_counts=256)
    transmitted=ROOT/f"results/p21-mod-waveforms-20261017T122536Z/bundle/{name}.iq16le"
    if pack_tx_iq_le16(tx.iq)!=transmitted.read_bytes():
        raise RuntimeError("TX reference does not match archived transmitted bytes")
    ref=tx.iq*np.exp(-2j*np.pi*960000*np.arange(len(tx.iq))/FS)
    cases={}
    scatter={}
    for entry in transport["files"]:
        path=args.transfer/entry["local_file"]
        if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
            raise RuntimeError("raw file hash changed")
        x=load_iq_dma_s16(path,channels=4)
        rows=[]
        for start in range(0,len(x),4096):
            fit=align_periodic_reference(x[start:start+4096],ref,FS,994000)
            rows.append({"sample":start,"source_start":fit.source_start,
                         "carrier_hz":fit.frequency_hz,"correlation":fit.correlation,
                         "waveform_nmse_db":fit.nmse_db})
        gaps=modulo_gaps([r["source_start"] for r in rows],4096,len(ref))
        signed=np.where(gaps<len(ref)//2,gaps,gaps-len(ref))
        boundaries=int(np.count_nonzero(abs(signed)>4))
        matches=all(r["correlation"]>.99 for r in rows)
        case={"source":str(path),"sha256":entry["sha256"],"bytes":path.stat().st_size,
              "capture_buffer_samples":entry["buffer_samples"],"subwindows":rows,
              "extra_advance_modulo_period":signed.tolist(),"discontinuous_boundaries":boundaries,
              "all_subwindows_match_source":matches,"full_snapshot":None}
        # Never claim a global known-symbol EVM on a record with missing time.
        if boundaries==0 and matches:
            fit=align_periodic_reference(x,ref,FS,float(np.median([r["carrier_hz"] for r in rows])))
            recovered=recover_snapshot(x,FS,fit.frequency_hz,name)
            expected=tx.symbols[np.rint((fit.source_start+recovered.sample_indices)/SPS).astype(int)%len(tx.symbols)]
            sy=recovered.symbols
            split=len(sy)//2
            gain=np.vdot(expected[:split],sy[:split])/np.vdot(expected[:split],expected[:split])
            eq=sy[split:]/gain
            table=constellation(name)
            decisions=table[np.argmin(abs(eq[:,None]-table[None,:])**2,axis=1)]
            errors=int(np.count_nonzero(abs(decisions-expected[split:])>1e-9))
            case["full_snapshot"]={"timing_method":"maximum-power search, no known-symbol timing supplied",
                "waveform_correlation":fit.correlation,"carrier_hz":fit.frequency_hz,
                "source_start":fit.source_start,"timing_offset":recovered.timing_offset,
                "expected_timing_from_reference":int((-fit.source_start)%SPS),
                "guard_samples_per_side":recovered.guard_samples,"valid_symbols":len(sy),
                "decision_directed_evm_db":evm_db(sy,table),"reference_evm_db":reference_evm_db(sy,expected),
                "heldout_symbol_errors":errors,"heldout_symbols":len(eq)}
            scatter[entry["name"]]=sy/np.sqrt(np.mean(abs(sy)**2))
        cases[entry["name"]]=case
    positive=all(cases[n]["discontinuous_boundaries"]==0 and cases[n]["all_subwindows_match_source"]
                 and cases[n]["full_snapshot"]["reference_evm_db"] < -25
                 and cases[n]["full_snapshot"]["heldout_symbol_errors"]==0 for n in ("big1","big2"))
    out=ROOT/"results"/datetime.now(timezone.utc).strftime(f"p22-buffer-validation-{name}-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"schema":"rfsig.buffer_comparison.v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "transfer":str(args.transfer),"acquisition":transport["source"],"modulation":name,
            "cases":cases,"single_buffer_acceptance_passed":positive,
            "limits":["Single 65536-sample snapshots, not a one-second or indefinite lossless stream.",
                      "Known-source alignment diagnoses modulo-period gaps; whole-period loss is not excluded by correlation alone.",
                      "No claimed cause inside a particular kernel/DMA component; the buffer-size intervention is verified.",
                      "EVM and held-out symbol decisions use a known transmitted sequence; not AI accuracy or a general BER figure."]}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,ax=plt.subplots(1,2,figsize=(12,4),layout="constrained")
    for label,c in cases.items():
        ax[0].plot(np.arange(1,16),c["extra_advance_modulo_period"],"o-",label=label)
    ax[0].set(xlabel="4096-sample subwindow boundary",ylabel="Extra source advance (samples, modulo period)",title="Same RF configuration, different receive buffer size")
    for label,sy in scatter.items():
        ax[1].scatter(sy.real,sy.imag,s=9,label=label,alpha=.5)
    ax[1].set(xlabel="I / RMS",ylabel="Q / RMS",title=f"{mod}: full single-buffer symbol recovery")
    ax[1].axis("equal")
    for a in ax:
        a.legend()
        a.grid(alpha=.3)
    fig.savefig(out/"buffer-comparison.png",dpi=150)
    plt.close(fig)
    for label,c in cases.items():
        full=c["full_snapshot"]
        print(label,"gap_boundaries",c["discontinuous_boundaries"],
              "EVM",round(full["reference_evm_db"],2) if full else "invalid across joins",
              "heldout_errors",full["heldout_symbol_errors"] if full else "not measured")
    print("single_buffer_acceptance_passed",positive)
    print(out)
    return 0 if positive else 1


if __name__=="__main__":
    raise SystemExit(main())
