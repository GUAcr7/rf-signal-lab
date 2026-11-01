"""User-facing regression tests: reject unsafe time assumptions and preserve evidence."""
import base64
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys

import numpy as np

ROOT=Path(__file__).resolve().parents[1]


def run(script,*args):
    return subprocess.run([sys.executable,str(ROOT/"experiments"/script),*map(str,args)],
                           cwd=ROOT,capture_output=True,text=True,encoding="utf-8",timeout=20,
                           env={**os.environ,"PYTHONUTF8":"1","PYTHONIOENCODING":"utf-8"})


def test_tracking_cli_rejects_multibuffer_record_before_running_analysis(tmp_path):
    path=tmp_path/"raw.bin"
    path.write_bytes(np.zeros((8192,4),dtype="<i2").tobytes())
    result=run("p21_track_and_measure.py","--segment",path,"--label","test",
               "--modulation","bpsk","--dma-buffer-samples",4096)
    assert result.returncode==2
    assert "multi-buffer" in result.stderr


def test_block_cli_rejects_a_block_that_would_cross_dma_boundaries(tmp_path):
    result=run("p21_block_analysis.py","--segment",tmp_path/"unused.bin","--label","test",
               "--modulation","bpsk","--dma-buffer-samples",4096,"--block-samples",8192)
    assert result.returncode==2
    assert "never cross a boundary" in result.stderr


def test_extract_records_context_rails_and_unknown_continuity_without_overwriting(tmp_path):
    raw=np.array([[2047,0,0,0],[-2048,0,0,0]],dtype="<i2").tobytes()
    sha=hashlib.sha256(raw).hexdigest()
    transcript=tmp_path/"transcript.json"
    transcript.write_text(json.dumps({"results":[{"command":"base64 /tmp/raw.bin","ok":True,
        "output":base64.b64encode(raw).decode()+"\nroot@board# "}]}),encoding="utf-8")
    out=tmp_path/"decoded"
    args=("--transcript",transcript,"--expect-sha256",sha,"--signal-context","known-source",
          "--positive-rail",2047,"--buffer-samples",1024,"--output",out)
    result=run("p18_extract_capture.py",*args)
    assert result.returncode==0,result.stderr
    record=json.loads((out/"characterisation.json").read_text("utf-8"))
    assert record["signal_context"]=="known-source"
    assert "unverified" in record["adc_time_continuity"]
    assert record["endpoint_fraction"]==1
    original=(out/"characterisation.json").read_bytes()
    repeated=run("p18_extract_capture.py",*args)
    assert repeated.returncode!=0
    assert (out/"segment.bin").read_bytes()==raw
    assert (out/"characterisation.json").read_bytes()==original
