"""Retrieve bounded captures after TX stopped; verify original board hashes."""
import argparse
import base64
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys

from p22_acquire_comparison import Console,ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition",required=True,type=Path)
    parser.add_argument("--port",default="COM8")
    args=parser.parse_args()
    source=json.loads((args.acquisition/"report.json").read_text("utf-8"))
    if source["status"] != "capture_and_tx_cleanup_verified":
        raise RuntimeError("acquisition or TX cleanup was not verified")
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p22-transfer-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"source":str(args.acquisition),"created_utc":datetime.now(timezone.utc).isoformat(),
            "stages":[],"files":[],"status":"in_progress"}
    def save():
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    save()
    rx=None
    try:
        rx=Console(args.port,report,save)
        rx.command("cd /tmp")
        for entry in source["board_files"]:
            filename=Path(entry["path"]).name
            if not re.fullmatch(r"p22-[a-z0-9-]+\.bin",filename):
                raise ValueError("unexpected board filename")
            rx.command("p="+filename)
            rx.command("test ! -e $p.gz")
            rx.command("gzip -c $p > $p.gz")
            response=rx.command("base64 $p.gz",timeout=150)
            allowed=set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
            payload="".join(line.strip() for line in response.splitlines()
                            if len(line.strip())>=4 and set(line.strip())<=allowed)
            compressed=base64.b64decode(payload,validate=True)
            raw=gzip.decompress(compressed)
            sha=hashlib.sha256(raw).hexdigest()
            if sha != entry["sha256"] or len(raw)!=entry["expected_bytes"]:
                raise RuntimeError("board hash/length mismatch; no decoded sample file written")
            target=out/(entry["name"]+".bin")
            target.write_bytes(raw)
            (out/(entry["name"]+".bin.gz")).write_bytes(compressed)
            report["files"].append({**entry,"local_file":target.name,"sha256_matches_board":True,
                                    "compressed_bytes":len(compressed)})
            save()
            print(entry["name"],len(raw),"bytes, board SHA256 verified",flush=True)
        report["status"]="all_payloads_verified"
    except Exception as exc:
        report["status"]="failed"
        report["error"]=repr(exc)
        raise
    finally:
        if rx: rx.close()
        save()
        print(out,flush=True)


if __name__=="__main__":
    main()
