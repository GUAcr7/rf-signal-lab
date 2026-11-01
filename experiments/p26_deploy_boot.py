"""Guarded atomic boot-script update and read-only RF readiness check. No reboot."""
from datetime import datetime, timezone
import hashlib
import json
import sys

from p22_acquire_comparison import Console, ROOT


def main():
    sys.stdout.reconfigure(encoding="utf-8")
    out = ROOT/"results"/datetime.now(timezone.utc).strftime("p26-boot-deployment-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report = {"stages": [], "status": "preflight", "rf_writes": False, "rebooted": False,
              "previous_sha256": "1f22eae506ac98643f13f231bd7f4b6586de355e5f63b7018d6640926823d5ba",
              "new_sha256": hashlib.sha256((ROOT/"board/boot/S99board").read_bytes()).hexdigest()}
    def save():
        (out/"report.json").write_text(json.dumps(report, indent=2)+"\n", encoding="utf-8")
    save()
    board = None
    try:
        board = Console("COM8", report, save)
        if "Zynq-Tronlong" not in board.command("uname -a"):
            raise RuntimeError("unexpected receiver board")
        board.command("cd /etc/rcS.d")
        if report["previous_sha256"] not in board.command("sha256sum S99board"):
            raise RuntimeError("installed script changed since review; refusing overwrite")
        board.command("p=/tmp/p26-S99board-candidate")
        if report["new_sha256"] not in board.command("sha256sum $p"):
            raise RuntimeError("uploaded candidate hash mismatch")
        board.command("sh -n $p")
        board.command("b=/etc/p26-S99board-before-20261018")
        board.command("test ! -e $b")
        board.command("cp -p S99board $b")
        if report["previous_sha256"] not in board.command("sha256sum $b"):
            raise RuntimeError("board backup failed verification")
        report["backup_path"] = "/etc/p26-S99board-before-20261018"
        save()
        board.command("n=.S99board.p26-new")
        board.command("test ! -e $n")
        board.command("cp $p $n")
        board.command("chmod 755 $n")
        board.command("cmp $p $n")
        board.command("mv $n S99board")
        board.command("sync")
        if report["new_sha256"] not in board.command("sha256sum S99board"):
            raise RuntimeError("installed script hash mismatch")
        board.command("ls -l S99board")
        board.command("./S99board --check-rf")
        board.command("iio_readdev --help")
        board.command("ls /sys/bus/iio/devices/iio:device2/scan_elements")
        report["status"] = "installed_hash_mode_and_readiness_verified"
    except Exception as error:
        report["status"] = "failed"
        report["error"] = repr(error)
        raise
    finally:
        if board:
            board.close()
        save()
        print(out)


if __name__ == "__main__":
    main()
