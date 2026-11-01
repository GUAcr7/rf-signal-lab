"""Host-build actual C receiver against deterministic/failing IIO, no board use."""
import json
import os
from pathlib import Path
import subprocess

import numpy as np
import pytest

ROOT=Path(__file__).resolve().parents[1]


def posix(path):
    s=Path(path).resolve().as_posix()
    return "/mnt/"+s[0].lower()+s[2:] if os.name=="nt" else s


def run(command):
    prefix=["wsl.exe","--exec"] if os.name=="nt" else []
    return subprocess.run(prefix+command,capture_output=True,timeout=45)


@pytest.fixture(scope="module")
def built(tmp_path_factory):
    folder=tmp_path_factory.mktemp("native-rx-diagnostic")
    include=ROOT/"embedded/vendor/libiio-v0.24"
    for source,target,extra in ((ROOT/"tests/native/mock_rx_diagnostic.c",folder/"libiio.so.0",["-shared","-fPIC"]),
                                (ROOT/"embedded/arm_rx_diagnostic/arm_rx_diagnostic.c",folder/"receiver",["-ldl","-lrt"])):
        result=run(["gcc","-std=c11","-O2","-Wall","-Wextra","-Werror","-I",posix(include),posix(source),"-o",posix(target),*extra])
        assert result.returncode==0,result.stdout.decode(errors="replace")+result.stderr.decode(errors="replace")
    return folder


def invoke(built,tmp_path,fault="",count="16"):
    output=tmp_path/"output"
    output.mkdir(exist_ok=True)
    log=tmp_path/"cleanup.txt"
    result=run(["env","LD_LIBRARY_PATH="+posix(built),"P27_MOCK_LOG="+posix(log),"P27_MOCK_FAULT="+fault,
                posix(built/"receiver"),posix(output),count])
    return result,output,log


def test_saved_data_is_exactly_the_declared_strided_prefix_for_every_block(built,tmp_path):
    result,out,log=invoke(built,tmp_path)
    assert result.returncode==0,result.stderr.decode(errors="replace")
    data=np.fromfile(out/"prefixes.bin",dtype="<i2").reshape(16,1024,2)
    expected=(np.arange(16)[:,None]*97+np.arange(1024)[None,:]*8)%4096
    np.testing.assert_array_equal(data[:,:,0],np.where(expected>=2048,expected-4096,expected))
    q=4095-expected
    np.testing.assert_array_equal(data[:,:,1],np.where(q>=2048,q-4096,q))
    meta=json.loads((out/"metadata.json").read_text())
    assert len(meta["timestamps"])==16
    assert meta["complete_stream_saved"] is False and meta["lossless_proven"] is False
    assert meta["buffer_released"] is True
    assert log.read_text().strip()=="destroyed=1 enabled=0"


@pytest.mark.parametrize("fault",["format","config","bist","version","step","refill"])
def test_invalid_mode_format_or_refill_cannot_produce_pass(built,tmp_path,fault):
    result,out,log=invoke(built,tmp_path,fault)
    assert result.returncode!=0
    assert b"SPARSE_RX_PASS" not in result.stdout
    assert not (out/"metadata.json").exists()
    if log.exists():
        assert "enabled=0" in log.read_text()
        if fault in ("step","refill"):
            assert "destroyed=1" in log.read_text()


@pytest.mark.parametrize("count",["0","15","513","-1","16oops"])
def test_unbounded_or_invalid_requests_are_rejected(built,tmp_path,count):
    result,out,_=invoke(built,tmp_path,count=count)
    assert result.returncode==2
    assert not list(out.iterdir())


def test_existing_output_files_are_not_overwritten(built,tmp_path):
    result,out,_=invoke(built,tmp_path)
    assert result.returncode==0
    before=(out/"prefixes.bin").read_bytes()
    result,_,_=invoke(built,tmp_path)
    assert result.returncode!=0
    assert (out/"prefixes.bin").read_bytes()==before


def test_maximum_accepted_request_has_bounded_output_and_all_timestamps(built,tmp_path):
    result,out,_=invoke(built,tmp_path,count="512")
    assert result.returncode==0
    meta=json.loads((out/"metadata.json").read_text())
    assert len(meta["timestamps"])==512
    assert (out/"prefixes.bin").stat().st_size==512*1024*4
