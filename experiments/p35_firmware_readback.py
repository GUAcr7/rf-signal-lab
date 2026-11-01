"""Read current board identity, actual firmware files and clock state; no writes."""
from datetime import datetime,timezone
import hashlib
import json
from p32_session import ROOT,BoardConsole

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-firmware-readback-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report=dict(status='reading',read_only=True,stages=[])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=None
    try:
        board=BoardConsole('COM8',report,save);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        report['boot_id']=board.value('/proc/sys/kernel/random/boot_id')
        report['tainted']=board.value('/proc/sys/kernel/tainted')
        report['mode']=board.value('/etc/board-mode')
        board.command('cd /lib/firmware')
        for command in ['sha256sum display.bin system_wrapper.bin ad9361.bin',
                'ls -l *.vb d480p.dtbo* p32*',
                'sha256sum *.vb d480p.dtbo* p32.raw',
                'sha256sum pl.dtbo',
                'sha256sum /etc/rcS.d/S99board',
                'ls /sys/kernel/config/device-tree/overlays',
                'cat /sys/class/fpga_manager/fpga0/state',
                'ls /sys/class/graphics',
                'cat /proc/cmdline',
                'cat /proc/uptime',
                'cat /sys/kernel/debug/clk/clk_summary',
                'dmesg | tail -n 100']:
            board.command(command)
        present=board.command('if [ -r /proc/config.gz ]; then echo CONFIG_PRESENT; fi')
        if '\nCONFIG_PRESENT\r' in present:
            board.command("zcat /proc/config.gz | grep -E 'CLK.*WZRD|IKCONFIG'")
        report['status']='read_only_evidence_captured'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        report['serial_closed']=True
        save();print(out);print(report['status'])
    return 0 if report['status']=='read_only_evidence_captured' else 1

if __name__=='__main__':raise SystemExit(main())
