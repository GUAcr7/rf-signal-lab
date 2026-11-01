"""Read current board state only. No Ctrl-C, RF writes, reboot or overlay edits."""
from datetime import datetime,timezone
import json
from pathlib import Path
import sys

from p22_acquire_comparison import Console,ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p26-preflight-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"created_utc":datetime.now(timezone.utc).isoformat(),"stages":[],"read_only":True}
    def save():
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    save()
    commands={"COM9":["uname -a","cat /proc/sys/kernel/random/boot_id","ps",
                       "ls /tmp/p12-source-stage-1018/stage/arm/arm-tx-source",
                       "ls /tmp/p12-source-stage-mods1018/bundle"],
              "COM8":["uname -a","cat /etc/board-mode","ps",
                       "cat /sys/bus/iio/devices/iio:device*/name",
                       "sha256sum /etc/rcS.d/S99board","readlink -f /tmp",
                       "cat /proc/mounts | grep -E 'tmpfs|mmc'",
                       "cat /proc/uptime","df -k /tmp",
                       "cd /sys/bus/iio/devices/iio:device1",
                       "cat in_voltage_sampling_frequency in_voltage_rf_bandwidth",
                       "cat in_voltage0_gain_control_mode in_voltage0_hardwaregain",
                       "cat out_altvoltage0_RX_LO_frequency in_voltage0_rf_port_select"]}
    for port,rows in commands.items():
        console=None
        try:
            console=Console(port,report,save)
            for command in rows:
                console.command(command,timeout=5)
            print(port,"read-only preflight saved",flush=True)
        finally:
            if console: console.close()
            save()
    print(out)


if __name__=="__main__":
    main()
