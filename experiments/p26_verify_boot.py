"""One RF-mode warm reboot after ALL new captures are durably recovered."""
from datetime import datetime, timezone
import hashlib
import json
import re
import sys
import time
import argparse

from p22_acquire_comparison import Console, ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--continue-from", type=str, help="read-only continuation of an already issued reboot")
    args = parser.parse_args()
    transfers = [ROOT/"results"/folder for folder in (
        "p26-chunk-transfer-20261018T120112Z", "p26-chunk-transfer-20261018T122135Z")]
    for folder in transfers:
        data = json.loads((folder/"report.json").read_text("utf-8"))
        if data["status"] != "all_payloads_verified":
            raise RuntimeError("cannot reboot with incomplete capture recovery")
        for entry in data["files"]:
            if not entry["verified"] or hashlib.sha256((folder/entry["local_file"]).read_bytes()).hexdigest() != entry["sha256"]:
                raise RuntimeError("local original capture failed verification")
    out = ROOT/"results"/datetime.now(timezone.utc).strftime("p26-boot-verification-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    record = {"stages": [], "status": "preflight", "rf_transmitted": False,
              "power_cycle": False, "warm_reboot": False}
    def save():
        (out/"report.json").write_text(json.dumps(record, indent=2)+"\n", encoding="utf-8")
    save()
    board = None
    try:
        # Confirm old transmitter stopped, then release COM9 before opening RX.
        board = Console("COM9", record, save)
        processes = board.command("ps")
        if any("arm-tx-source --run" in row and "grep" not in row for row in processes.splitlines()):
            raise RuntimeError("TX still active; refusing receiver reboot")
        board.close()
        board = Console("COM8", record, save)
        expected = hashlib.sha256((ROOT/"board/boot/S99board").read_bytes()).hexdigest()
        previous = None
        if args.continue_from:
            previous = json.loads((ROOT/args.continue_from/"report.json").read_text("utf-8"))
            if not previous.get("warm_reboot") or not previous.get("boot_id_before"):
                raise RuntimeError("no issued reboot in supplied predecessor")
            record["continuation_of"] = args.continue_from
            record["warm_reboot"] = True
            record["reboot_issued_this_process"] = False
            # Preserve any remaining startup output before issuing commands.
            tail = bytearray()
            deadline = time.monotonic()+6
            while time.monotonic() < deadline:
                tail.extend(board.port.read(board.port.in_waiting or 1))
            record["continuation_console"] = tail.decode("utf-8", errors="replace")
            save()
            if re.search(rb"login:\s*$", tail[-1000:]):
                board.port.write(b"root\r")
                record["login_console"] = board.read_until(r"root@Zynq-Tronlong[^\r\n]*#", 8)
        if expected not in board.command("sha256sum /etc/rcS.d/S99board"):
            raise RuntimeError("installed boot script differs from reviewed source")
        before = previous["boot_id_before"] if previous else re.search(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                           board.command("cat /proc/sys/kernel/random/boot_id"))[0]
        if "rf" not in board.command("cat /etc/board-mode").splitlines():
            raise RuntimeError("mode changed; refusing unexpected reboot")
        record["boot_id_before"] = before
        if not previous:
            board.command("sync")
            board.port.write(b"reboot\r")
            record["warm_reboot"] = True
            save()
            raw = bytearray()
            deadline = time.monotonic()+65
            while time.monotonic() < deadline:
                raw.extend(board.port.read(board.port.in_waiting or 1))
                # A shell can briefly print a prompt during shutdown. Require
                # a new kernel/boot-loader banner before accepting a shell.
                startup = re.search(rb"(?:U-Boot \d|Linux version \d|Booting Linux)", raw)
                if startup and re.search(rb"(?:login:|root@Zynq-Tronlong[^\r\n]*#)\s*$", raw[-1000:]):
                    break
            record["boot_console"] = raw.decode("utf-8", errors="replace")
            save()
            if re.search(rb"login:\s*$", raw[-1000:]):
                board.port.write(b"root\r")
                record["login_console"] = board.read_until(r"root@Zynq-Tronlong[^\r\n]*#", 8)
            elif not re.search(rb"root@Zynq-Tronlong[^\r\n]*#", raw[-1000:]):
                raise RuntimeError("boot shell not reached; archived console for diagnosis")
        after = re.search(r"[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}",
                          board.command("cat /proc/sys/kernel/random/boot_id"))[0]
        record["boot_id_after"] = after
        if before == after:
            raise RuntimeError("boot ID unchanged")
        board.command("uname -a")
        board.command("cat /etc/board-mode")
        if expected not in board.command("sha256sum /etc/rcS.d/S99board"):
            raise RuntimeError("boot script did not persist")
        board.command("/etc/rcS.d/S99board --check-rf")
        log = board.command("dmesg | grep board-init")
        if "bring-up complete (mode=rf)" not in log or "FAILED" in log:
            raise RuntimeError("bring-up failed")
        attempts = re.findall(r"PHY/ADC/DDS names verified \(attempt (\d)\)", log)
        if not attempts:
            raise RuntimeError("updated readiness path did not execute")
        record["successful_attempt"] = int(attempts[-1])
        record["real_retry_branch_exercised"] = record["successful_attempt"] > 1
        board.command("cat /sys/class/fpga_manager/fpga0/state")
        board.command("cat /sys/bus/iio/devices/iio:device*/name")
        board.command("cd /sys/bus/iio/devices/iio:device1")
        for command in ("cat in_voltage_sampling_frequency in_voltage_rf_bandwidth",
                        "cat in_voltage0_gain_control_mode in_voltage0_hardwaregain",
                        "cat out_altvoltage0_RX_LO_frequency in_voltage0_rf_port_select"):
            board.command(command)
        record["status"] = "warm_boot_and_three_device_readiness_verified"
    except Exception as error:
        record["status"] = "failed"
        record["error"] = repr(error)
        raise
    finally:
        if board:
            board.close()
        save()
        print(out, flush=True)


if __name__ == "__main__":
    main()
