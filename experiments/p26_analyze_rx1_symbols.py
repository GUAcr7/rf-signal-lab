"""Check every RX1 DMA window against actual TX symbols, without crossing boundaries."""
from datetime import datetime, timezone
import hashlib
import json

import numpy as np

from p22_acquire_comparison import ROOT
from p21_track_and_measure import moment_carrier
from p26_audit_data import source
from rfsig.iq_io import load_iq_dma_s16
from rfsig.reference_receiver import measure_known_snapshot


def main():
    transfer=ROOT/"results/p26-chunk-transfer-20261018T122135Z"
    trace=json.loads((transfer/"report.json").read_text("utf-8"))
    if trace["status"]!="all_payloads_verified":
        raise RuntimeError("transport not accepted")
    entry=trace["files"][0]
    path=transfer/entry["local_file"]
    if hashlib.sha256(path.read_bytes()).hexdigest()!=entry["sha256"]:
        raise RuntimeError("source bytes changed")
    if entry["channels"]!=2 or entry["buffer_samples"]!=65536:
        raise RuntimeError("unexpected capture layout")
    iq=load_iq_dma_s16(path,channels=2)
    tx=source("bpsk")
    rows=[]
    for index,start in enumerate(range(0,len(iq),65536)):
        chunk=iq[start:start+65536]
        if len(chunk)!=65536:
            raise RuntimeError("partial DMA window")
        carrier=moment_carrier(chunk,30720000,2,50000,960000)
        measured=measure_known_snapshot(chunk,tx,carrier,dma_buffer_samples=65536)
        rows.append({"window":index,"first_frame_in_file":start,
                     "source_start_modulo_period":measured.alignment.source_start,
                     "correlation":measured.alignment.correlation,"carrier_hz":measured.alignment.frequency_hz,
                     "timing_offset":measured.recovered.timing_offset,
                     "valid_symbols":len(measured.recovered.symbols),"guard_samples_per_side":measured.recovered.guard_samples,
                     "reference_evm_db":measured.evm_db,"checked_symbols":measured.checked_symbols,
                     "symbol_errors":measured.symbol_errors})
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p26-rx1-symbol-quality-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"source":path.relative_to(ROOT).as_posix(),"sha256":entry["sha256"],
            "channels":2,"modulation_supplied":"bpsk","windows":rows,
            "total_valid_symbols":sum(r["valid_symbols"] for r in rows),
            "total_checked_symbols":sum(r["checked_symbols"] for r in rows),
            "total_symbol_errors":sum(r["symbol_errors"] for r in rows),
            "evm_min_db":min(r["reference_evm_db"] for r in rows),
            "evm_max_db":max(r["reference_evm_db"] for r in rows),
            "represented_nominal_samples_ms":len(iq)/30720000*1000,
            "wall_time_is_not_ADC_time":True,"lossless_proven":False,
            "scope":"Every DMA window is measured separately, with its own whole-window carrier/source fit. No cross-boundary filtering; not independent BER or AI."}
    (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(len(rows),"windows; valid",report["total_valid_symbols"],"checked",report["total_checked_symbols"],
          "errors",report["total_symbol_errors"],"EVM range",round(report["evm_min_db"],2),round(report["evm_max_db"],2))
    print(out)


if __name__=="__main__":
    main()
