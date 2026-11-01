"""One bounded, already-reviewed RF configuration; compare RX buffer sizes.

No RF setting writes, reboot, bitstream change or gain increase. The native TX
guard verifies board identity, config and waveform hash; maximum TX time 30 s.
Each serial port has one owner. Every stage is saved, including failure output.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
import re
import sys
import time

import serial

ROOT = Path(__file__).resolve().parents[1]
HASHES = {"bpsk":"167d99034316c7e28c3da46ab3974f883ad457303e836178692cfa451c26217f",
          "qpsk":"","qam16":""}


class Console:
    def __init__(self,port,report,save):
        self.port = serial.Serial(port,115200,timeout=.1,write_timeout=3,
                                  rtscts=False,dsrdtr=False)
        self.report,self.save,self.name=report,save,port
        self.port.dtr=False
        self.port.rts=False
    def close(self):
        self.port.close()
    def read_until(self,pattern,timeout):
        data=bytearray()
        until=time.monotonic()+timeout
        while time.monotonic()<until:
            data.extend(self.port.read(self.port.in_waiting or 1))
            text=data.decode("ascii",errors="replace")
            if re.search(pattern,text,re.M):
                return text
        raise TimeoutError(f"{self.name} timed out; received tail: {data[-600:]!r}")
    def command(self,command,timeout=8):
        if len(command)>72 or "\n" in command:
            raise ValueError("console command must be <=72 chars and one line")
        self.port.write((command+"\recho __P22_RC__:$?\r").encode("ascii"))
        text=self.read_until(r"^__P22_RC__:[0-9]+\r?$",timeout)
        rc=int(re.search(r"^__P22_RC__:([0-9]+)\r?$",text,re.M)[1])
        entry={"port":self.name,"command":command,"exit_code":rc,"output":text,
               "utc":datetime.now(timezone.utc).isoformat()}
        self.report["stages"].append(entry)
        self.save()
        if rc:
            raise RuntimeError(f"{self.name}: stage failed ({rc}): {command}")
        return text


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tx-port",default="COM9")
    parser.add_argument("--rx-port",default="COM8")
    parser.add_argument("--modulation",choices=HASHES,default="bpsk")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out=ROOT/"results"/f"p22-acquisition-{args.modulation}-{stamp}"
    out.mkdir(exist_ok=False)
    record={"created_utc":datetime.now(timezone.utc).isoformat(),"stages":[],
            "modulation":args.modulation,"rf_settings_written":False,"rf_operations":False,"tx_duration_limit_s":30,
            "status":"in_progress","board_files":[]}
    def save():
        (out/"report.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    save()
    tx=rx=None
    tx_started=False
    tx_finished=False
    try:
        tx=Console(args.tx_port,record,save)
        rx=Console(args.rx_port,record,save)
        if "Linux pzp201" not in tx.command("uname -a"):
            raise RuntimeError("unexpected TX board")
        if "Zynq-Tronlong" not in rx.command("uname -a"):
            raise RuntimeError("unexpected RX board")
        boot=tx.command("cat /proc/sys/kernel/random/boot_id")
        bootid=re.search(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",boot)[0]
        tx.command("cd /tmp/p12-source-stage-armsmall/stage")
        inspect=tx.command("./arm/arm-tx-source --inspect")
        for expected in ("tx0_sampling_frequency=30720000","tx_lo=2450000000",
                         "tx0_hardwaregain=-10.000000 dB","tx0_rf_bandwidth=18000000"):
            if expected not in inspect:
                raise RuntimeError(f"TX config mismatch: {expected}")
        tx.command(f"p=/tmp/p12-source-stage-mods256/bundle/{args.modulation}.iq16le")
        local=ROOT/f"results/p21-mod-waveforms-20261017T122536Z/bundle/{args.modulation}.iq16le"
        import hashlib
        expected_hash=hashlib.sha256(local.read_bytes()).hexdigest()
        if args.modulation=="bpsk" and expected_hash != HASHES["bpsk"]:
            raise RuntimeError("BPSK source hash changed")
        if expected_hash not in tx.command("sha256sum $p"):
            raise RuntimeError("TX source hash mismatch")
        tx.command("h="+expected_hash)
        tx.command("b=boot-session:"+bootid)
        tx.command("n=131072; f=30720000; l=2450000000; w=18000000")
        rx.command("cd /sys/bus/iio/devices/iio:device1")
        expected_config={"in_voltage_sampling_frequency":"30720000",
                         "in_voltage_rf_bandwidth":"18000000",
                         "out_altvoltage0_RX_LO_frequency":"2450000000",
                         "in_voltage0_gain_control_mode":"manual",
                         "in_voltage0_hardwaregain":"0.000000 dB",
                         "in_voltage0_rf_port_select":"A_BALANCED"}
        for attribute,value in expected_config.items():
            text=rx.command("cat "+attribute)
            if value not in text.splitlines():
                raise RuntimeError(f"RX config mismatch: {attribute}")
        rx.command("cd /tmp")
        prefix=f"p22-{args.modulation}-{stamp[-7:-1]}"
        cases=[("small",4096),("big1",65536),("big2",65536)]
        for name,_ in cases:
            rx.command(f"test ! -e {prefix}-{name}.bin")
        # No background shell, unbounded loop or automatic retry on TX failure.
        run="./arm/arm-tx-source --run $p $n $f $l $w -10 30 $b A $h RF_LINK_REVIEWED"
        if len(run)>72:
            raise ValueError("TX command too long")
        tx.port.write((run+"\recho __P22_TX_RC__:$?\r").encode("ascii"))
        tx_begin=tx.read_until(r"CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=30",8)
        tx_started=True
        record["rf_operations"]=True
        record["tx_started_output"]=tx_begin
        save()
        print("TX guard passed; acquiring three snapshots at the unchanged settings.",flush=True)
        for name,size in cases:
            filename=f"{prefix}-{name}.bin"
            rx.command(f"iio_readdev -b {size} -s 65536 cf-ad9361-lpc > {filename}",10)
            record["board_files"].append({"name":name,"path":"/tmp/"+filename,
                                         "buffer_samples":size,"expected_bytes":524288})
            save()
        tx_end=tx.read_until(r"^__P22_TX_RC__:[0-9]+\r?$",40)
        tx_finished=True
        record["tx_finished_output"]=tx_end
        if "TX_CLEANUP buffer_released=true rf_settings_written=false status=0" not in tx_end:
            raise RuntimeError("TX cleanup not verified")
        if not re.search(r"^__P22_TX_RC__:0\r?$",tx_end,re.M):
            raise RuntimeError("TX returned nonzero")
        record["status"]="capture_and_tx_cleanup_verified"
        # Transfer AFTER TX deadline; serial output speed does not limit capture.
        for entry in record["board_files"]:
            text=rx.command("sha256sum "+entry["path"])
            entry["sha256"]=re.search(r"^([0-9a-f]{64})\s",text,re.M)[1]
        save()
        print("Capture complete; TX stopped and cleaned up. Raw files remain on RX for separate retrieval.",flush=True)
    except Exception as exc:
        record["status"]="failed"
        record["error"]=repr(exc)
        if tx_started and not tx_finished:
            try:
                record["cleanup_after_error"]=tx.read_until(r"^__P22_TX_RC__:[0-9]+\r?$",40)
            except Exception as cleanup_error:
                record["cleanup_verification_error"]=repr(cleanup_error)
        save()
        raise
    finally:
        if rx: rx.close()
        if tx: tx.close()
        save()
        print(out,flush=True)
    return 0


if __name__=="__main__":
    raise SystemExit(main())
