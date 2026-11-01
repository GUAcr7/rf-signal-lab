"""Restore ONLY the previously measured RX mode/gain/LO after reboot; no TX."""
from datetime import datetime, timezone
import json
import re
import sys

from p22_acquire_comparison import Console, ROOT


def parse_attribute_frame(text):
    values=re.findall(r"^__P26_VALUE__(.*?)__P26_END__\r?$",text,re.M)
    if len(values)!=1:
        raise RuntimeError("attribute value frame is missing or ambiguous")
    return values[0]


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    profile = json.loads((ROOT/"configs/rf-link-snapshot-p26.json").read_text("utf-8"))
    out = ROOT/"results"/datetime.now(timezone.utc).strftime("p26-rx-profile-restore-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    record = {"stages": [], "status": "preflight", "TX_used": False,
              "rx_attributes_written": [], "before": {}, "after": {}}
    def save():
        (out/"report.json").write_text(json.dumps(record,indent=2)+"\n",encoding="utf-8")
    def read_value(board, command):
        if not re.fullmatch(r"cat [a-zA-Z0-9_/$]+",command):
            raise ValueError("only a known attribute read is allowed")
        board.command("a="+command[4:])
        return parse_attribute_frame(board.command("echo __P26_VALUE__$(cat $a)__P26_END__"))
    board = None
    save()
    try:
        board = Console("COM9",record,save)
        if any("arm-tx-source --run" in row and "grep" not in row for row in board.command("ps").splitlines()):
            raise RuntimeError("TX active; refusing configuration change")
        board.close()
        board = Console("COM8",record,save)
        if "Zynq-Tronlong" not in board.command("uname -a"):
            raise RuntimeError("unexpected receiver")
        board.command("/etc/rcS.d/S99board --check-rf")
        # Resolve names with short shell commands. No enumeration-order identity.
        board.command("p=/sys/bus/iio/devices")
        board.command("for d in $p/iio:device*; do echo $d; cat $d/name; done")
        names=record["stages"][-1]["output"]
        pairs=re.findall(r"(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)",names)
        by_name={name:path for path,name in pairs}
        phy=by_name.get("ad9361-phy")
        adc=by_name.get("cf-ad9361-lpc")
        if not phy or not adc:
            raise RuntimeError("cannot resolve actual PHY and ADC")
        board.command("s="+adc+"/scan_elements")
        for index in range(4):
            if read_value(board,f"cat $s/in_voltage{index}_en") != "0":
                raise RuntimeError("RX buffer may be active; refusing attribute writes")
        board.command("cd "+phy)
        expected={"in_voltage_sampling_frequency":str(profile["sample_rate_hz"]),
                  "in_voltage_rf_bandwidth":str(profile["rf_bandwidth_hz"]),
                  "in_voltage0_rf_port_select":profile["rx_port"]}
        change={"in_voltage0_gain_control_mode":profile["rx_gain_mode"],
                "in_voltage0_hardwaregain":str(profile["rx_gain_db"]),
                "out_altvoltage0_RX_LO_frequency":str(profile["rx_lo_hz"])}
        for attribute in [*expected,*change]:
            record["before"][attribute]=read_value(board,"cat "+attribute)
            save()
        for attribute,value in expected.items():
            if record["before"][attribute]!=value:
                raise RuntimeError("unreviewed rate/bandwidth/port change: "+attribute)
        record["status"]="before_values_saved"
        save()  # Durable backup before the first write.
        for attribute,value in change.items():
            if record["before"][attribute] == value or (attribute.endswith("hardwaregain") and record["before"][attribute]=="0.000000 dB"):
                continue
            board.command("echo "+value+" > "+attribute)
            record["rx_attributes_written"].append(attribute)
            save()
        for attribute in [*expected,*change]:
            record["after"][attribute]=read_value(board,"cat "+attribute)
        wanted={**expected,**change,"in_voltage0_hardwaregain":"0.000000 dB"}
        if record["after"]!=wanted:
            raise RuntimeError("restored configuration readback mismatch")
        record["status"]="reviewed_rx_profile_restored_and_read_back"
    except Exception as error:
        record["status"]="failed"
        record["error"]=repr(error)
        raise
    finally:
        if board:
            board.close()
        save()
        print(out)


if __name__=="__main__":
    main()
