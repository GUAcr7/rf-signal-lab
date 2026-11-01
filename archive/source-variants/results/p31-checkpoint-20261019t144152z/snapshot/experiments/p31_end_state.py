"""Read both board identities and idle state after the Oops/power-cycle recovery."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
import re
from p26_retrieve_chunks import ChunkConsole, ROOT
from p26_restore_rx_profile import parse_attribute_frame


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--rx-boot-id', required=True)
    args = parser.parse_args()
    previous = json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))['p30_integration']
    out = ROOT/'results'/datetime.now(timezone.utc).strftime('p31-end-state-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report = dict(status='reading', stages=[], boards={}, read_only=True,
        firmware_writes=False, RF_attribute_writes=False, physical_RF_silence_measured=False)

    def save():
        (out/'report.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')

    def value(board, path):
        board.command('a='+path)
        return parse_attribute_frame(board.command('echo __P26_VALUE__$(cat $a)__P26_END__'))

    board = None
    save()
    try:
        board = ChunkConsole('COM9', report, save)
        if 'Linux pzp201' not in board.command('uname -a'):
            raise RuntimeError('wrong old board')
        old_boot = value(board, '/proc/sys/kernel/random/boot_id')
        if old_boot != previous['tx_boot_id']:
            raise RuntimeError('old board rebooted; old RAM stage must be revalidated')
        directory = previous['tx_recovery_directory']
        if not re.fullmatch(r'/tmp/p12-source-stage-p30-[0-9]{6}', directory):
            raise ValueError('unexpected historical source stage')
        board.command('cd '+directory+'/stage')
        result = board.command('./arm/arm-tx-source --inspect')
        if 'INSPECT_PASS read_only=true no_buffers_created=true' not in result:
            raise RuntimeError('old source inspect failed')
        processes = board.command('ps')
        if any('arm-tx-source' in line for line in processes.splitlines()):
            raise RuntimeError('TX process still present')
        report['boards']['COM9'] = dict(boot_id=old_boot, RAM_stage=directory,
            inspect_pass=True, TX_process_observed=False)
        board.close()
        board = ChunkConsole('COM8', report, save)
        if 'Zynq-Tronlong' not in board.command('uname -a'):
            raise RuntimeError('wrong new board')
        new_boot = value(board, '/proc/sys/kernel/random/boot_id')
        if new_boot != args.rx_boot_id:
            raise RuntimeError('new boot session changed')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('p=/sys/bus/iio/devices')
        text = board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        names = {n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)', text)}
        required = ['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']
        if not all(n in names for n in required):
            raise RuntimeError('missing named RF device')
        board.command('cd '+names['ad9361-phy'])
        expected = dict(in_voltage_sampling_frequency='30720000', in_voltage_rf_bandwidth='18000000',
            out_altvoltage0_RX_LO_frequency='2450000000', in_voltage0_gain_control_mode='manual',
            in_voltage0_hardwaregain='0.000000 dB', in_voltage0_rf_port_select='A_BALANCED')
        attributes = {key:value(board,key) for key in expected}
        if attributes != expected:
            raise RuntimeError('RX attributes mismatch')
        board.command('cd '+names['cf-ad9361-lpc'])
        buffer = value(board,'buffer/enable')
        scans = [value(board,f'scan_elements/in_voltage{i}_en') for i in range(4)]
        if buffer != '0' or scans != ['0']*4:
            raise RuntimeError('RX buffer/scan still active')
        mode = value(board, '/etc/board-mode')
        fabric = value(board, '/sys/class/fpga_manager/fpga0/state')
        tainted = value(board, '/proc/sys/kernel/tainted')
        if mode != 'rf' or fabric != 'operating' or tainted != '0':
            raise RuntimeError('mode/fabric/kernel state mismatch')
        processes = board.command('ps -ef')
        if any(re.search(r'p27-rx|arm-rx-capture|iio_readdev',line) for line in processes.splitlines()):
            raise RuntimeError('receive process still present')
        installed = re.search(r'^([0-9a-f]{64})\s',board.command('sha256sum /etc/rcS.d/S99board'),re.M)[1]
        if installed != hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest():
            raise RuntimeError('guarded boot script changed')
        board.command('dmesg | tail -n 32')
        report['boards']['COM8'] = dict(boot_id=new_boot, mode=mode, fabric=fabric, tainted=tainted,
            names=names, RX_attributes=attributes, buffer_enable=buffer, scans=scans,
            RX_process_observed=False, boot_script_sha256=installed)
        report['status'] = 'recovered_original_RF_both_boards_idle_and_guard_verified'
    except Exception as error:
        report.update(status='failed', error=repr(error))
    finally:
        if board:
            board.close()
        report['serial_handles_closed'] = True
        save()
    print(out)
    print(report['status'])
    return 1 if report['status'] == 'failed' else 0


if __name__ == '__main__':
    raise SystemExit(main())
