"""Bounded, resumable gzip/chunk retrieval with board/raw hashes; no RF writes."""
import argparse
import base64
from datetime import datetime,timezone
import gzip
import hashlib
import json
from pathlib import Path
import re
import sys
import time

from p22_acquire_comparison import Console,ROOT

CHUNK_BYTES=196608


class ChunkConsole(Console):
    def read_until(self,pattern,timeout):
        # Scan a bounded tail instead of decoding the entire growing payload
        # after every serial byte. The RC marker is at the end of each response.
        pattern=re.compile(pattern.encode("ascii"),re.M)
        data=bytearray()
        deadline=time.monotonic()+timeout
        while time.monotonic()<deadline:
            data.extend(self.port.read(self.port.in_waiting or 1))
            if pattern.search(data[max(0,len(data)-4096):]):
                return data.decode("ascii",errors="replace")
        raise TimeoutError(f"serial response did not end in {timeout}s; received {len(data)} bytes")


def decode_payload(text,expected_bytes):
    alphabet=set("ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/=")
    lines=[line.strip() for line in text.splitlines()]
    encoded="".join(line for line in lines if len(line)>=4 and set(line)<=alphabet)
    raw=base64.b64decode(encoded,validate=True)
    if len(raw)!=expected_bytes:
        raise ValueError(f"chunk length {len(raw)} != expected {expected_bytes}")
    return raw


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--acquisition",type=Path,required=True)
    parser.add_argument("--resume",type=Path)
    parser.add_argument("--port",default="COM8")
    parser.add_argument("--name-prefix",choices=("p26","p27"),default="p26",
                        help="explicit namespace for new diagnostic captures; defaults to original P26")
    args=parser.parse_args()
    source=json.loads((args.acquisition/"report.json").read_text("utf-8"))
    if source["status"]!="capture_and_tx_cleanup_verified":
        raise RuntimeError("acquisition or bounded TX cleanup not verified")
    if args.resume:
        out=args.resume.resolve()
        report=json.loads((out/"report.json").read_text("utf-8"))
        if Path(report["acquisition"]).resolve()!=args.acquisition.resolve():
            raise RuntimeError("resume belongs to another acquisition")
    else:
        out=ROOT/"results"/datetime.now(timezone.utc).strftime(args.name_prefix+"-chunk-transfer-%Y%m%dT%H%M%SZ")
        out.mkdir(exist_ok=False)
        report={"created_utc":datetime.now(timezone.utc).isoformat(),"acquisition":str(args.acquisition.resolve()),
                "stages":[],"files":[],"chunk_bytes":CHUNK_BYTES,"status":"in_progress",
                "diagnostic_only":source.get("diagnostic_only",False),
                "complete_stream_saved":source.get("complete_stream_saved",True)}
    def save():
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    save()
    console=None
    try:
        console=ChunkConsole(args.port,report,save)
        console.command("cd /tmp")
        for entry in source["board_files"]:
            filename=Path(entry["path"]).name
            if not re.fullmatch(args.name_prefix+r"-[a-zA-Z0-9-]+\.bin",filename):
                raise ValueError("unexpected board path")
            console.command("p="+filename)
            if entry["sha256"] not in console.command("sha256sum $p"):
                raise RuntimeError("board raw file changed; cannot resume")
            existing=next((row for row in report["files"] if row["name"]==entry["name"]),None)
            if existing is None:
                console.command("test ! -e $p.gz")
                console.command("gzip -c $p > $p.gz",timeout=12)
                gz_sha=re.search(r"^([0-9a-f]{64})\s",console.command("sha256sum $p.gz"),re.M)[1]
                size_text=console.command("wc -c $p.gz")
                gz_bytes=int(re.search(r"^\s*([0-9]+)\s",size_text,re.M)[1])
                existing={**entry,"gzip_sha256":gz_sha,"gzip_bytes":gz_bytes,"chunks":[],"verified":False}
                report["files"].append(existing)
                save()
            elif existing["gzip_sha256"] not in console.command("sha256sum $p.gz"):
                raise RuntimeError("board compressed file changed; cannot resume")
            chunks=[]
            for index,start in enumerate(range(0,existing["gzip_bytes"],CHUNK_BYTES)):
                expected=min(CHUNK_BYTES,existing["gzip_bytes"]-start)
                part=out/f"{entry['name']}-part{index:03d}.gzpart"
                saved=next((c for c in existing["chunks"] if c["index"]==index),None)
                if saved:
                    chunk=part.read_bytes()
                    if len(chunk)!=expected or hashlib.sha256(chunk).hexdigest()!=saved["sha256"]:
                        raise RuntimeError("local saved chunk failed verification")
                else:
                    command=f"dd if=$p.gz bs={CHUNK_BYTES} skip={index} count=1 2>/dev/null | base64"
                    text=console.command(command,timeout=50)
                    chunk=decode_payload(text,expected)
                    part.write_bytes(chunk)
                    existing["chunks"].append({"index":index,"bytes":len(chunk),"sha256":hashlib.sha256(chunk).hexdigest(),"file":part.name})
                    save()
                chunks.append(chunk)
                print(entry["name"],f"chunk {index+1}/{(existing['gzip_bytes']+CHUNK_BYTES-1)//CHUNK_BYTES}",flush=True)
            packed=b"".join(chunks)
            if hashlib.sha256(packed).hexdigest()!=existing["gzip_sha256"]:
                raise RuntimeError("compressed board hash mismatch")
            raw=gzip.decompress(packed)
            if len(raw)!=entry["expected_bytes"] or hashlib.sha256(raw).hexdigest()!=entry["sha256"]:
                raise RuntimeError("original raw board hash/length mismatch")
            target=out/(entry["name"]+".bin")
            if target.exists() and target.read_bytes()!=raw:
                raise RuntimeError("refusing to overwrite a different raw file")
            target.write_bytes(raw)
            existing["verified"]=True
            existing["local_file"]=target.name
            save()
            print(entry["name"],"raw bytes and board SHA256 verified",flush=True)
        report["status"]="all_payloads_verified"
    except Exception as error:
        report["status"]="incomplete"
        report["error"]=repr(error)
        raise
    finally:
        if console: console.close()
        save()
        print(out,flush=True)


if __name__=="__main__":
    main()
