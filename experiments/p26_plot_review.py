"""Plot measured buffer-boundary evidence and reference-checked QAM metrology."""
from datetime import datetime, timezone
import json
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def main():
    report=json.loads(sorted(ROOT.glob("results/p26-independent-audit-*/report.json"))[-1].read_text("utf-8"))
    features=json.loads((ROOT/"results/p26-known-modulation-features-20261018T121600Z/features.json").read_text("utf-8"))
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p26-review-figures-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    fig,axes=plt.subplots(1,2,figsize=(12,4.6),layout="constrained")
    for case,label,color in ((report["buffer_progress"][3],"4 stored channels: 11 jumps","#c44437"),
                             (report["buffer_progress"][4],"RX1 only: no non-periodic jump detected","#187d83")):
        values=[row["extra_advance_modulo_period"] for row in case["assessment"]["boundaries"]]
        axes[0].plot(range(1,len(values)+1),values,"o-",markersize=4,label=label,color=color)
    axes[0].axhline(0,color="gray",linewidth=.6)
    axes[0].set(xlabel="Boundary before DMA window",ylabel="Signed modulo source advance (samples)",
                title="Same rate / buffer size; different channel mask")
    axes[0].legend(fontsize=8,loc="upper right")
    axes[0].grid(alpha=.2)
    qam=[row for row in features["cases"] if row["modulation_supplied"]=="qam16"]
    known=[row for row in report["snapshots"] if row.get("case")]
    index=np.arange(2)
    for delta,key,label,color in ((-.24,"decision_evm_before_pll_db","Coarse carrier","#c8a65c"),
                                  (0.,"decision_evm_after_causal_pll_db","Causal PLL","#8a7eb2"),
                                  (.24,"decision_evm_after_batch_fit_db","Batch refinement","#187d83")):
        axes[1].bar(index+delta,[row[key] for row in qam],width=.22,label=label,color=color)
    axes[1].plot(index,[row["reference_evm_db"] for row in known],"k_",markersize=45,markeredgewidth=2,label="Known-symbol reference")
    axes[1].set(xticks=index,xticklabels=["16QAM big1","16QAM big2"],ylabel="EVM (dB; lower is better)",
                title="All 502 valid symbols; no extra transient trimming",ylim=(-43,0))
    axes[1].legend(fontsize=8,loc="upper right")
    axes[1].grid(axis="y",alpha=.2)
    fig.suptitle("P26 measured review: finite snapshots, supplied modulation",fontsize=13)
    fig.text(.01,-.04,"Periodic reference length = 131072 samples. Zero modulo jumps does not prove lossless long-time capture.",fontsize=9)
    fig.savefig(out/"review.png",dpi=160,bbox_inches="tight")
    fig.savefig(out/"review.pdf",bbox_inches="tight")
    plt.close(fig)
    print(out)


if __name__=="__main__":
    main()
