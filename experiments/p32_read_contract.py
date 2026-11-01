"""Read live timer/clock/startup contract, preserving raw UART evidence."""
from datetime import datetime, timezone
import json
from p32_session import BoardConsole, ROOT


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-live-contract-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report=dict(status='reading',stages=[],board_changes=False)
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=None
    try:
        board=BoardConsole('COM8',report,save)
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        report['boot_id']=board.value('/proc/sys/kernel/random/boot_id')
        for command in [
            'cat /etc/init.d/rcS', 'cat /etc/init.d/rc',
            'ls -l /etc/rcS.d', 'cat /proc/cmdline',
            'p=/sys/devices/system/clocksource/clocksource0',
            'cat $p/current_clocksource $p/available_clocksource',
            'ls -l /sys/class/pwm',
            'cat /sys/kernel/debug/clk/clk_summary',
            'cat /sys/kernel/debug/pwm',
            'ls -l /lib/firmware',
            'sha256sum /lib/firmware/ad9361.bin',
            'sha256sum /lib/firmware/pl.dtbo',
            'cat /proc/mounts',
            'ls /sys/kernel/config/device-tree/overlays',
        ]:
            board.command(command+' || true' if len(command)<64 else command,timeout=15)
        report['status']='read_only_contract_archived'
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        save()
        print(out);print(report['status'])


if __name__=='__main__':main()
