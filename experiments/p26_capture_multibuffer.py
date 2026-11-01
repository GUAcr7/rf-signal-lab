"""Bounded 4/16-buffer BPSK trial at the unchanged, reviewed RF configuration."""
from datetime import datetime,timezone
import argparse
import hashlib
import json
from pathlib import Path
import re
import sys

from p22_acquire_comparison import Console,ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rx1-only",action="store_true",help="select voltage0/1 explicitly; two-channel output")
    args=parser.parse_args()
    stamp=datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out=ROOT/"results"/f"p26-multibuffer-acquisition-{stamp}"
    out.mkdir(exist_ok=False)
    record={"created_utc":datetime.now(timezone.utc).isoformat(),"stages":[],"status":"preflight",
            "rf_operations":False,"rf_settings_written":False,"modulation":"bpsk",
            "tx_duration_limit_s":30,"board_files":[],"file_sink":"/tmp, tmpfs verified separately"}
    record["channels"]=2 if args.rx1_only else 4
    record["channel_ids"]=["voltage0","voltage1"] if args.rx1_only else ["voltage0","voltage1","voltage2","voltage3"]
    def save():
        (out/"report.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    tx=rx=None
    started=finished=False
    save()
    try:
        tx=Console("COM9",record,save)
        rx=Console("COM8",record,save)
        if "Linux pzp201" not in tx.command("uname -a") or "Zynq-Tronlong" not in rx.command("uname -a"):
            raise RuntimeError("unexpected board identity")
        if any("arm-tx-source --run" in line and "grep" not in line
               for line in tx.command("ps").splitlines()):
            raise RuntimeError("an existing transmitter is active")
        bootid=re.search(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                         tx.command("cat /proc/sys/kernel/random/boot_id"))[0]
        tx.command("cd /tmp/p12-source-stage-1018/stage")
        inspect=tx.command("./arm/arm-tx-source --inspect")
        for value in ("tx0_sampling_frequency=30720000","tx_lo=2450000000",
                      "tx0_hardwaregain=-10.000000 dB","tx0_rf_bandwidth=18000000"):
            if value not in inspect: raise RuntimeError("TX config changed: "+value)
        tx.command("p=/tmp/p12-source-stage-mods1018/bundle/bpsk.iq16le")
        sha=hashlib.sha256((ROOT/"results/p21-mod-waveforms-20261017T122536Z/bundle/bpsk.iq16le").read_bytes()).hexdigest()
        if sha not in tx.command("sha256sum $p"): raise RuntimeError("source hash mismatch")
        tx.command("h="+sha)
        tx.command("b=boot-session:"+bootid)
        tx.command("n=131072; f=30720000; l=2450000000; w=18000000")
        rx.command("cd /sys/bus/iio/devices/iio:device1")
        for attr,value in {"name":"ad9361-phy","in_voltage_sampling_frequency":"30720000",
                           "in_voltage_rf_bandwidth":"18000000","in_voltage0_gain_control_mode":"manual",
                           "in_voltage0_hardwaregain":"0.000000 dB","out_altvoltage0_RX_LO_frequency":"2450000000",
                           "in_voltage0_rf_port_select":"A_BALANCED"}.items():
            if value not in rx.command("cat "+attr).splitlines():
                raise RuntimeError("RX config changed: "+attr)
        rx.command("cd /tmp")
        rx.command("d=cf-ad9361-lpc")
        if args.rx1_only:
            # Probe the actual selected scan layout before enabling RF. This
            # does not write LO, gain, bandwidth or sample-rate attributes.
            rx.command("s=/sys/bus/iio/devices/iio:device2/scan_elements")
            for index in (0,1):
                if f"in_voltage{index}_type" not in rx.command("ls $s"):
                    raise RuntimeError("missing RX1 scan channel")
                rx.command(f"cat $s/in_voltage{index}_index")
                if "le:S12/16>>0" not in rx.command(f"cat $s/in_voltage{index}_type"):
                    raise RuntimeError("unexpected RX1 storage type")
        rx.command("df -k /tmp")
        rx.command("time true")  # Verify timing command before RF transmission.
        paths=[(count,f"p26-{stamp[-7:-1]}-{count}.bin") for count in ((16,) if args.rx1_only else (4,16))]
        for _,path in paths: rx.command("test ! -e "+path)
        command="./arm/arm-tx-source --run $p $n $f $l $w -10 30 $b A $h RF_LINK_REVIEWED"
        tx.port.write((command+"\recho __P26_TX_RC__:$?\r").encode())
        record["tx_start"]=tx.read_until(r"CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=30",8)
        started=True
        record["rf_operations"]=True
        save()
        for count,path in paths:
            rx.command("p="+path)
            select=" voltage0 voltage1" if args.rx1_only else ""
            rx.command(f"time iio_readdev -b 65536 -s {65536*count} $d{select} > $p",12)
            expected_bytes=count*65536*2*record["channels"]
            if expected_bytes not in [int(word) for word in rx.command("wc -c $p").split() if word.isdigit()]:
                raise RuntimeError("capture byte count does not match explicit channel layout")
            hash_output=rx.command("sha256sum $p")
            entry={"name":f"buffers{count}","path":"/tmp/"+path,"buffer_samples":65536,
                   "buffer_count":count,"expected_bytes":expected_bytes,"channels":record["channels"],
                   "sha256":re.search(r"^([0-9a-f]{64})\s",hash_output,re.M)[1]}
            record["board_files"].append(entry)
            save()
        record["tx_end"]=tx.read_until(r"^__P26_TX_RC__:[0-9]+\r?$",40)
        finished=True
        if "TX_CLEANUP buffer_released=true rf_settings_written=false status=0" not in record["tx_end"]:
            raise RuntimeError("TX cleanup unverified")
        if not re.search(r"^__P26_TX_RC__:0\r?$",record["tx_end"],re.M):
            raise RuntimeError("TX failed")
        record["status"]="capture_and_tx_cleanup_verified"
        print("Multi-buffer files acquired; bounded TX ended and cleanup verified.")
    except Exception as error:
        record["status"]="failed"
        record["error"]=repr(error)
        if started and not finished:
            try: record["cleanup_after_error"]=tx.read_until(r"^__P26_TX_RC__:[0-9]+\r?$",40)
            except Exception as failure: record["cleanup_error"]=repr(failure)
        raise
    finally:
        if rx: rx.close()
        if tx: tx.close()
        save()
        print(out,flush=True)


if __name__=="__main__":
    main()
