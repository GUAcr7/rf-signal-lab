"""Read identity and startup evidence after the user power-cycled the new board."""
from datetime import datetime,timezone
import json
import re
import serial
import time
from p26_retrieve_chunks import ChunkConsole,ROOT


def main():
    out=ROOT/'results'/('p31-repowered-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    report=dict(status='observing',stages=[],firmware_writes=False,overlay_changes=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    serial_port=serial.Serial(port=None,baudrate=115200,timeout=.1);serial_port.dtr=False;serial_port.rts=False;serial_port.port='COM8'
    try:
        serial_port.open();serial_port.write(b'\r');until=time.monotonic()+3;data=bytearray()
        while time.monotonic()<until:data.extend(serial_port.read(serial_port.in_waiting or 1))
        report['initial_console']=data.decode('ascii',errors='replace')
    finally:serial_port.close();save()
    board=None
    try:
        board=ChunkConsole('COM8',report,save)
        if 'Zynq-Tronlong' not in board.command('uname -a',timeout=15):raise RuntimeError('identity not confirmed')
        output=board.command('cat /proc/sys/kernel/random/boot_id')
        report['boot_id']=re.search(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',output)[0]
        for command in ['cat /etc/board-mode','cat /sys/class/fpga_manager/fpga0/state','dmesg | tail -n 140','cat /proc/sys/kernel/tainted','ps -ef']:
            board.command(command)
        output=board.command('/etc/rcS.d/S99board --check-rf || true')
        report['RF_ready']=bool(re.search(r'^RF_READY phy=',output,re.M))
        report['status']='root_shell_and_original_boot_checked'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if board:board.close()
        save()
    print(out);print(report['status']);print(report.get('boot_id'));print('RF ready',report.get('RF_ready'))
    if 'error' in report:print(report['error'])


if __name__=='__main__':main()
