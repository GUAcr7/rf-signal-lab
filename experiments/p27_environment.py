"""Read new receiver ABI/network tools; no configuration writes or signals."""
from datetime import datetime, timezone
import json
from p22_acquire_comparison import ROOT,Console


def main():
    out=ROOT/"results"/datetime.now(timezone.utc).strftime("p27-environment-%Y%m%dT%H%M%SZ")
    out.mkdir(exist_ok=False)
    report={"stages":[],"read_only":True}
    def save():
        (out/"report.json").write_text(json.dumps(report,indent=2)+"\n",encoding="utf-8")
    board=Console("COM8",report,save)
    try:
        for cmd in ("uname -a","iio_info -h | head -n 5","ls -l /lib/libc*","cat /proc/net/dev","df -k /tmp","ps"):
            board.command(cmd)
        print(out)
    finally:
        board.close()
        save()


if __name__=="__main__":main()
