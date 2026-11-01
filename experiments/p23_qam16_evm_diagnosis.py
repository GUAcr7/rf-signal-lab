"""Corrected data-aided QAM reference check; no board access or output overwrite.

TX nominal offset and RX measured carrier are different quantities. Use the
shared reference receiver instead of mixing the TX reference by the RX carrier.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import sys
from p26_audit_data import snapshot,ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output",type=Path)
    args=parser.parse_args()
    rows=[snapshot(ROOT/f"results/p22-transfer-20261017T132355Z/{case}.bin","qam16") for case in ("big1","big2")]
    out=args.output or ROOT/"results"/datetime.now(timezone.utc).strftime("p26-qam16-reference-fix-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"schema":"rfsig.qam_reference_diagnosis.v2","cases":rows,
            "correction":"TX reference removes 960 kHz nominal offset; RX removes fitted received carrier. Expected symbols come from aligned transmitted payload times.",
            "limits":"Known sequence and modulation supplied; this is metrology, not AI accuracy."}
    (out/"diagnosis.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    for row in rows: print(Path(row["source"]).name,round(row["reference_evm_db"],2),"dB")
    print(out)


if __name__=="__main__": main()
