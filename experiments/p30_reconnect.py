"""Identify both re-powered boards, archive boot evidence before any recovery."""
from datetime import datetime,timezone
import json
import os
import re
import time
import serial
from p22_acquire_comparison import Console,ROOT


def observe(port,report,save):
    link=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=3)
    link.dtr=False;link.rts=False;link.port=port;link.open()
    def read_for(seconds):
        end=time.monotonic()+seconds;data=bytearray()
        while time.monotonic()<end:data.extend(link.read(link.in_waiting or 1))
        return data.decode('ascii',errors='replace')
    try:
        link.write(b'\r');text=read_for(1)
        report['login_observation'].append(dict(port=port,output=text));save()
        if re.search(r'login:\s*$',text) and 'pzp201' in text:
            link.write(b'root\r');text=read_for(.7)
            report['login_observation'].append(dict(port=port,action='documented_user_login',output=text));save()
            if 'Password:' not in text:raise RuntimeError('unexpected TX login flow')
            # Documented default for this lab board, already used this session.
            # Never store the submitted credential in the transcript.
            link.write((os.environ['RFSIG_BOARD_PASSWORD']+'\r').encode('utf-8'));text=read_for(.8)
            report['login_observation'].append(dict(port=port,action='documented_password_redacted',output=text));save()
        if 'login:' in text and not re.search(r'#\s*$',text):
            raise RuntimeError('login not established; no shell commands submitted')
        return text
    finally:link.close()


def main():
    out=ROOT/'results'/('p30-reconnect-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',stages=[],login_observation=[],boards={},RF_writes=False,reboots=False,bitstream_writes=False)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    for port,expected in [('COM9','Linux pzp201'),('COM8','Zynq-Tronlong')]:
        console=None
        try:
            observe(port,report,save)
            console=Console(port,report,save)
            identity=console.command('uname -a')
            if expected not in identity:raise RuntimeError('identity mismatch')
            boot=console.command('cat /proc/sys/kernel/random/boot_id')
            bootid=re.search(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',boot)[0]
            report['boards'][port]=dict(identity_confirmed=True,boot_id=bootid)
            if port=='COM8':
                for command in ['cat /etc/board-mode','cat /proc/uptime','dmesg | tail -n 100',
                        'for f in /sys/bus/iio/devices/iio:device*/name; do cat $f; done',
                        'cat /sys/class/fpga_manager/fpga0/state',
                        'ps -ef']:
                    console.command(command)
                try:
                    console.command('/etc/rcS.d/S99board --check-rf')
                    report['boards'][port]['RF_ready']=True
                except RuntimeError:report['boards'][port]['RF_ready']=False
            else:
                console.command('ls /tmp')
                console.command('ps')
        except Exception as error:
            report['boards'].setdefault(port,{}).update(error=repr(error))
        finally:
            if console:console.close()
            save()
    report['status']='board_states_archived_before_recovery';save()
    print(out)
    print(json.dumps(report['boards'],indent=2))


if __name__=='__main__':main()
