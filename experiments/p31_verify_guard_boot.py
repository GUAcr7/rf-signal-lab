"""One ordinary reboot to verify the installed guard; no overlay hot removal."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
import time
from p26_retrieve_chunks import ChunkConsole, ROOT
from p26_restore_rx_profile import parse_attribute_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--boot-id', required=True)
    args = parser.parse_args()
    pointer = json.loads((ROOT/'results/p31-checkpoint-active.json').read_text('utf-8'))
    checkpoint = json.loads(__import__('pathlib').Path(pointer['report']).read_text('utf-8'))
    if checkpoint['status'] != 'scoped_evidence_checkpoint_verified':
        raise RuntimeError('durable checkpoint required before reboot')
    expected = hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p31-guard-boot-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record = dict(status='preflight', stages=[], boot_id_before=args.boot_id,
        checkpoint=pointer['report'], ordinary_reboots_issued=0, hot_overlay_removal=False,
        TX_application_started=False, expected_script_sha256=expected)

    def save():
        (out/'report.json').write_text(json.dumps(record, indent=2)+'\n', encoding='utf-8')

    def value(board, path):
        board.command('a='+path)
        return parse_attribute_frame(board.command('echo __P26_VALUE__$(cat $a)__P26_END__'))

    board = None
    save()
    try:
        board = ChunkConsole('COM9',record,save)
        if 'Linux pzp201' not in board.command('uname -a'):
            raise RuntimeError('wrong old board')
        if any('arm-tx-source' in line for line in board.command('ps').splitlines()):
            raise RuntimeError('TX still active')
        board.close()
        board = ChunkConsole('COM8',record,save)
        if 'Zynq-Tronlong' not in board.command('uname -a'):
            raise RuntimeError('wrong new board')
        if value(board,'/proc/sys/kernel/random/boot_id') != args.boot_id:
            raise RuntimeError('unexpected boot session')
        if value(board,'/etc/board-mode')!='rf' or value(board,'/proc/sys/kernel/tainted')!='0':
            raise RuntimeError('unexpected mode or tainted kernel')
        if expected not in board.command('sha256sum /etc/rcS.d/S99board'):
            raise RuntimeError('installed script changed')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('p=/sys/bus/iio/devices')
        board.command('for d in $p/iio:device*; do cat $d/name; done')
        if any(re.search(r'p27-rx|arm-rx-capture|iio_readdev',line) for line in board.command('ps -ef').splitlines()):
            raise RuntimeError('receive client still active')
        board.command('sync', timeout=20)
        # Persist intent before issuing the one command that disrupts the shell.
        record['status']='reboot_intent_saved'
        save()
        board.port.write(b'reboot\r')
        record['ordinary_reboots_issued']=1
        save()
        raw = bytearray()
        deadline = time.monotonic()+55
        while time.monotonic()<deadline:
            raw.extend(board.port.read(board.port.in_waiting or 1))
            if re.search(rb'(?:U-Boot \d|Linux version \d|Booting Linux)',raw) and re.search(
                    rb'(?:login:|root@Zynq-Tronlong[^\r\n]*#)\s*$',raw[-1200:]):
                break
        record['boot_console']=raw.decode('utf-8', errors='replace')
        save()
        if re.search(rb'login:\s*$',raw[-1200:]):
            board.port.write(b'root\r')
            record['login_console']=board.read_until(r'root@Zynq-Tronlong[^\r\n]*#',8)
        elif not re.search(rb'root@Zynq-Tronlong[^\r\n]*#',raw[-1200:]):
            raise RuntimeError('new shell not reached; console archived')
        after=value(board,'/proc/sys/kernel/random/boot_id')
        record['boot_id_after']=after
        if after==args.boot_id:
            raise RuntimeError('boot identity did not change')
        board.command('uname -a')
        if expected not in board.command('sha256sum /etc/rcS.d/S99board'):
            raise RuntimeError('guard did not persist')
        log=board.command('dmesg | grep board-init')
        board.command('cat /sys/bus/iio/devices/iio:device*/name')
        board.command('dmesg | tail -n 60')
        if value(board,'/proc/sys/kernel/tainted')!='0':
            raise RuntimeError('kernel tainted after reboot')
        record['kernel_tainted']=0
        if 'bring-up complete (mode=rf)' not in log or 'FAILED:' in log:
            raise RuntimeError('single-apply startup did not complete; no hot retry attempted')
        board.command('/etc/rcS.d/S99board --check-rf')
        if value(board,'/sys/class/fpga_manager/fpga0/state')!='operating':
            raise RuntimeError('fabric not operating')
        record['status']='guarded_full_warm_boot_and_three_device_readiness_verified'
    except Exception as error:
        record.update(status='failed',error=repr(error))
    finally:
        if board:
            board.close()
        record['serial_closed']=True
        save()
        print(out)
        print(record['status'])
        print(record.get('boot_id_after','unknown'))
    return 1 if record['status']=='failed' else 0


if __name__=='__main__':
    raise SystemExit(main())
