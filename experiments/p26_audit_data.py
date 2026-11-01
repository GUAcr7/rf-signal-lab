"""Independent byte/known-symbol audit and conservative buffer progress analysis."""
import argparse
import base64
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import sys

import numpy as np

from rfsig.capture_continuity import align_periodic_reference,assess_source_progress
from rfsig.carrier_tracking import constellation
from rfsig.iq_io import load_iq_dma_s16
from rfsig.reference_receiver import measure_known_snapshot
from rfsig.tx_waveforms import make_tx_waveform,pack_tx_iq_le16
from p18_extract_capture import extract_payload
from p21_track_and_measure import moment_carrier

ROOT=Path(__file__).resolve().parents[1]
FS=30_720_000


def source(name):
    mod={"bpsk":"BPSK","qpsk":"QPSK","qam16":"16QAM"}[name]
    tx=make_tx_waveform(mod,sample_rate_hz=FS,samples_per_symbol=128,symbol_count=1024,
                        seed=20261016,offset_hz=960000,digital_peak_counts=256)
    path=ROOT/f"results/p21-mod-waveforms-20261017T122536Z/bundle/{name}.iq16le"
    if pack_tx_iq_le16(tx.iq)!=path.read_bytes():
        raise RuntimeError("transmitted reference bytes changed")
    return tx


def snapshot(path,name):
    tx=source(name)
    x=load_iq_dma_s16(path,channels=4)
    carrier=moment_carrier(x,FS,2 if name=="bpsk" else 4,50000,960000)
    measured=measure_known_snapshot(x,tx,carrier,dma_buffer_samples=65536)
    sy=measured.recovered.symbols
    return {"source":str(path.resolve().relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "carrier_hz":measured.alignment.frequency_hz,"source_start":measured.alignment.source_start,
            "reference_correlation":measured.alignment.correlation,"timing_offset":measured.recovered.timing_offset,
            "reference_evm_db":measured.evm_db,"valid_symbols":len(sy),"checked_symbols":measured.checked_symbols,
            "symbol_errors":measured.symbol_errors,"amplitude_cv":float(np.std(abs(sy))/np.mean(abs(sy))),
            "quadrature_suppression_after_alignment_db":float(10*np.log10(np.mean(sy.real**2)/np.mean(sy.imag**2)))}


def progress(path,buffer_samples,channels=4):
    x=load_iq_dma_s16(path,channels=channels)
    if len(x)%buffer_samples:
        raise ValueError("partial last buffer must not be silently discarded")
    tx=source("bpsk")
    ref=tx.iq*np.exp(-2j*np.pi*960000*np.arange(len(tx.iq))/FS)
    rows=[]
    for start in range(0,len(x),buffer_samples):
        chunk=x[start:start+buffer_samples]
        carrier=moment_carrier(chunk,FS,2,50000,960000)
        try:
            fit=align_periodic_reference(chunk,ref,FS,carrier)
            rows.append({"window":start//buffer_samples,"source_start":fit.source_start,
                         "correlation":fit.correlation,"nmse_db":fit.nmse_db,"carrier_hz":fit.frequency_hz})
        except ValueError as error:
            rows.append({"window":start//buffer_samples,"source_start":None,"correlation":None,"error":str(error)})
    assessment=assess_source_progress([r["source_start"] for r in rows],[r["correlation"] for r in rows],buffer_samples,len(ref))
    return {"source":str(path.resolve().relative_to(ROOT)),"sha256":hashlib.sha256(path.read_bytes()).hexdigest(),
            "channels":channels,"frames":len(x),"buffer_samples":buffer_samples,"windows":rows,"assessment":assessment}


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--transfer",type=Path,action="append",help="repeat for independent verified transfers")
    args=parser.parse_args()
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p26-independent-audit-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    snapshots=[]
    for name in ("bpsk","qpsk","qam16"):
        path=ROOT/f"results/p24-rx-{name}-decoded/segment.bin"
        trace_path=ROOT/f"results/p24-rx-{name}-20261018/transcript.json"
        trace=json.loads(trace_path.read_text("utf-8-sig"))
        raw=base64.b64decode(extract_payload(trace,"base64"),validate=True)
        digest=hashlib.sha256(raw).hexdigest()
        if raw!=path.read_bytes() or not any(digest in e.get("output","") for e in trace["results"] if e["command"].startswith("sha256sum")):
            raise RuntimeError("cold-start source transport/board hash mismatch")
        row=snapshot(path,name)
        row["modulation_supplied"]=name
        row["transport_board_hash_verified"]=True
        snapshots.append(row)
    for case in ("big1","big2"):
        row=snapshot(ROOT/f"results/p22-transfer-20261017T132355Z/{case}.bin","qam16")
        row["modulation_supplied"]="qam16"
        row["case"]=case
        snapshots.append(row)
    progress_cases=[progress(ROOT/"results/p22-transfer-20261017T131327Z/small.bin",4096)]
    two=ROOT/"results/p25-rx-2buf-raw/two.bin"
    pieces=[]
    for index in (1,2,3):
        trace=json.loads((ROOT/f"results/p25-chunk{index}-20261018/transcript.json").read_text("utf-8-sig"))
        pieces.append(extract_payload(trace,"base64"))
    reconstructed=base64.b64decode("".join(pieces),validate=True)
    sha=hashlib.sha256(reconstructed).hexdigest()
    trace=json.loads((ROOT/"results/p25-rx-2buf-20261018/transcript.json").read_text("utf-8-sig"))
    if reconstructed!=two.read_bytes() or not any(sha in e.get("output","") for e in trace["results"] if e["command"].startswith("sha256sum")):
        raise RuntimeError("p25 original transport/hash mismatch")
    progress_cases.append(progress(two,65536))
    transfer_pending=False
    for transfer in args.transfer or []:
        report=json.loads((transfer/"report.json").read_text("utf-8"))
        for entry in report["files"]:
            if not entry.get("verified"):
                transfer_pending=True
                continue
            path=transfer/entry["local_file"]
            if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
                raise RuntimeError("new multi-buffer hash mismatch")
            progress_cases.append(progress(path,entry["buffer_samples"],channels=entry.get("channels",4)))
    table=constellation("qam16")
    report={"schema":"rfsig.independent_review.v1","created_utc":datetime.now(timezone.utc).isoformat(),
            "snapshots":snapshots,"buffer_progress":progress_cases,"transfer_incomplete":transfer_pending,
            "mathematical_checks":{"qam16_fourth_moment":float(np.real(np.mean(table**4))),
                "qam16_unit_fourth_moment":float(np.real(np.mean((table/abs(table))**4))),
                "1200_hz_relative_to_2450mhz_ppm":1200/2450000000*1e6,
                "claim_limit":"CFO change does not measure sample-clock ppm or identify which LO drifted."},
            "limits":["All symbol metrology uses supplied modulation and known transmitted sequence.",
                      "Periodic source matching cannot exclude whole-period losses; no result proves lossless ADC time."]}
    (out/"report.json").write_text(json.dumps(report,ensure_ascii=False,indent=2)+"\n",encoding="utf-8")
    for row in snapshots: print(row["source"],"EVM",round(row["reference_evm_db"],2),"errors",row["symbol_errors"])
    for row in progress_cases: print(row["source"],row["assessment"]["status"],"detected",row["assessment"]["detected_jump_count"])
    print(out)


if __name__=="__main__":
    main()
