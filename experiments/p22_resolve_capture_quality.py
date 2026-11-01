"""Reproduce the archived DMA-gap diagnosis without hardware or RF writes.

Evidence is always written to a new directory. The three p21 captures and their
board-verified hashes are immutable inputs. The known source is used explicitly
for diagnosis, not disguised as a blind modulation recogniser.
"""
import argparse
import base64
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np

from rfsig.capture_continuity import align_periodic_reference, modulo_gaps
from rfsig.carrier_tracking import constellation, evm_db, reference_evm_db
from rfsig.iq_io import load_iq_dma_s16
from rfsig.symbol_recovery import recover_snapshot
from rfsig.tx_waveforms import make_tx_waveform, pack_tx_iq_le16
from p18_extract_capture import extract_payload

ROOT = Path(__file__).resolve().parents[1]
FS = 30_720_000
SPS = 128
BUFFER = 4096


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_case(name, modulation):
    path = ROOT / f"results/p21-rx-{name}-long-decoded/segment.bin"
    metadata = json.loads(path.with_name("characterisation.json").read_text("utf-8"))
    trace_path = ROOT / f"results/p21-rx-{name}-long-20261017/transcript.json"
    trace = json.loads(trace_path.read_text("utf-8-sig"))
    payload = base64.b64decode(extract_payload(trace,"base64"),validate=True)
    actual_sha = digest(path)
    if payload != path.read_bytes() or actual_sha != metadata["sha256"]:
        raise RuntimeError(f"{name}: original payload/hash mismatch")
    hashes_in_board_output = [e["output"] for e in trace["results"]
                              if e["command"].startswith("sha256sum")]
    if not any(actual_sha in text for text in hashes_in_board_output):
        raise RuntimeError(f"{name}: no matching board SHA evidence")
    source = ROOT / f"results/p21-mod-waveforms-20261017T122536Z/bundle/{name}.iq16le"
    tx = make_tx_waveform(modulation,sample_rate_hz=FS,samples_per_symbol=SPS,
                          symbol_count=1024,seed=20261016,offset_hz=960_000,
                          digital_peak_counts=256,rolloff=.35,span_symbols=10)
    if pack_tx_iq_le16(tx.iq) != source.read_bytes():
        raise RuntimeError(f"{name}: reference does not reproduce transmitted bytes")
    ref = tx.iq*np.exp(-2j*np.pi*960_000*np.arange(len(tx.iq))/FS)
    x = load_iq_dma_s16(path,channels=4)
    rows = []
    # 994 kHz is an initial search seed from the archived moment estimate, not
    # a calibrated oscillator reading. Every buffer independently refines it.
    for start in range(0,len(x),BUFFER):
        chunk = x[start:start+BUFFER]
        fit = align_periodic_reference(chunk,ref,FS,994_000.)
        recovered = recover_snapshot(chunk,FS,fit.frequency_hz,name,
                                     timing_offset=(-fit.source_start)%SPS)
        expected_positions = np.rint((fit.source_start+recovered.sample_indices)/SPS).astype(int) % len(tx.symbols)
        expected = tx.symbols[expected_positions]
        symbols = recovered.symbols
        # Resolve the remaining constant PSK/QAM rotation with the first half,
        # then count decision errors on the other half (no per-symbol fitting).
        split = len(symbols)//2
        gain = np.vdot(expected[:split],symbols[:split])/np.vdot(expected[:split],expected[:split])
        equalised = symbols[split:]/gain
        table = constellation(name)
        decisions = table[np.argmin(abs(equalised[:,None]-table[None,:])**2,axis=1)]
        errors = int(np.count_nonzero(abs(decisions-expected[split:]) > 1e-9))
        rows.append({"buffer":start//BUFFER,"file_start":start,"source_start":fit.source_start,
                     "carrier_hz":fit.frequency_hz,"waveform_correlation":fit.correlation,
                     "waveform_nmse_db":fit.nmse_db,"timing_offset":recovered.timing_offset,
                     "guard_samples_per_side":recovered.guard_samples,"valid_symbols":len(symbols),
                     "timing_method":"known-source integer alignment (not blind timing)",
                     "decision_directed_evm_db":evm_db(symbols,table),
                     "reference_evm_db":reference_evm_db(symbols,expected),
                     "heldout_symbols":len(equalised),"heldout_symbol_errors":errors})
    gaps = modulo_gaps([r["source_start"] for r in rows],BUFFER,len(ref))
    for i,gap in enumerate(gaps,1):
        signed = int(gap if gap < len(ref)//2 else gap-len(ref))
        rows[i]["extra_source_advance_modulo_period"] = signed
        rows[i]["discontinuous_from_previous"] = abs(signed) > 4
    verified = all(r["waveform_correlation"] > .99 for r in rows)
    return {"source":str(path.relative_to(ROOT)),"source_sha256":actual_sha,
            "transcript_sha256":digest(trace_path),"transport_verified":True,
            "transmitted_file":str(source.relative_to(ROOT)),"tx_sha256":digest(source),
            "reference_bytes_reproduced":True,"frames":len(x),
            "buffers":rows,"all_buffers_match_known_source":verified,
            "discontinuous_boundaries":sum(r.get("discontinuous_from_previous",False) for r in rows),
            "worst_reference_evm_db":max(r["reference_evm_db"] for r in rows),
            "heldout_symbols":sum(r["heldout_symbols"] for r in rows),
            "heldout_symbol_errors":sum(r["heldout_symbol_errors"] for r in rows)}


def plot_report(cases,out):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    fig,axes = plt.subplots(3,2,figsize=(12,10),layout="constrained")
    for row,(name,case) in enumerate(cases.items()):
        records = case["buffers"]
        buffers = [r["buffer"] for r in records]
        starts = np.unwrap(np.array([r["source_start"] for r in records])*2*np.pi/131072)*131072/(2*np.pi)
        extra = starts-starts[0]-np.arange(len(starts))*BUFFER
        axes[row,0].plot(buffers,extra,"o-")
        axes[row,0].set_title(f"{name}: known-source position versus file order")
        axes[row,0].set_ylabel("Extra source advance (samples, modulo period)")
        axes[row,1].plot(buffers,[r["reference_evm_db"] for r in records],"o-",label="Known-symbol EVM")
        axes[row,1].plot(buffers,[r["waveform_nmse_db"] for r in records],".-",label="Raw waveform NMSE")
        axes[row,1].set_title(f"{name}: each DMA buffer analysed independently")
        axes[row,1].set_ylabel("Error (dB, lower is better)")
        axes[row,1].legend()
        for ax in axes[row]:
            ax.set_xlabel("Stored DMA buffer number (not continuous ADC time)")
            ax.grid(alpha=.3)
    fig.suptitle("Archived real RF: gaps between buffers, clean symbols within buffers\nKnown-source diagnostic; no new RF experiment and no recovered missing samples")
    fig.savefig(out/"continuity-and-quality.png",dpi=150)
    plt.close(fig)


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args = parser.parse_args()
    out = args.output or ROOT/"results"/datetime.now(timezone.utc).strftime("p22-gap-resolution-%Y%m%dT%H%M%SZ")
    out.mkdir(parents=True,exist_ok=False)
    cases = {name:run_case(name,mod) for name,mod in (("bpsk","BPSK"),("qpsk","QPSK"),("qam16","16QAM"))}
    report = {"schema":"rfsig.archived_capture_continuity.v1","created_utc":datetime.now(timezone.utc).isoformat(),
              "nature":"offline reanalysis of archived real RF; no board operations",
              "sample_rate_hz":FS,"dma_buffer_samples":BUFFER,"source_period_samples":131072,
              "cases":cases,
              "limits":["Known transmitted waveform and modulation supplied; not blind AI or general BER acceptance.",
                        "Positions and missing advances are modulo the 131072-sample TX period.",
                        "Correlation strongly supports discontinuous source time at DMA boundaries; exact overflow mechanism needs new capture.",
                        "No missing samples are fabricated or restored. Filter guards reduce symbol count.",
                        "No gap-free longer capture is claimed by this offline analysis."],
              "code_sha256":{str(p.relative_to(ROOT)):digest(p) for p in [Path(__file__),ROOT/"src/rfsig/capture_continuity.py",ROOT/"src/rfsig/symbol_recovery.py",ROOT/"src/rfsig/carrier_tracking.py"]}}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    plot_report(cases,out)
    for name,c in cases.items():
        print(name,"gapped_boundaries",c["discontinuous_boundaries"],"worst_EVM_dB",round(c["worst_reference_evm_db"],2),
              "heldout_errors",c["heldout_symbol_errors"],"/",c["heldout_symbols"],"all_source_matches",c["all_buffers_match_known_source"])
    print(out)
    return 0 if all(c["all_buffers_match_known_source"] for c in cases.values()) else 1


if __name__ == "__main__":
    raise SystemExit(main())
