"""Preserve console output and interrupt only this experiment's stuck rmdir."""
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import serial
from serial.tools import list_ports

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'results'/('p31-oops-observation-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    report=dict(status='observing',ports=[dict(port=p.device,description=p.description,hwid=p.hwid) for p in list_ports.comports()],stages=[])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=2)
    port.dtr=False;port.rts=False;port.port='COM8'
    def read(seconds):
        until=time.monotonic()+seconds;data=bytearray()
        while time.monotonic()<until:data.extend(port.read(port.in_waiting or 1))
        return data.decode('ascii',errors='replace')
    try:
        port.open();report['stages'].append(dict(action='passive',output=read(2)));save()
        port.write(b'\x03\r');report['stages'].append(dict(action='interrupt_owned_failed_rmdir',output=read(3)));save()
        port.write(b'echo __P31_SHELL_READY__\r');output=read(3)
        report['stages'].append(dict(action='shell_liveness',output=output))
        report['status']='shell_responded' if '\n__P31_SHELL_READY__' in output else 'shell_not_responding'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if port.is_open:port.close()
        save()
    print(out);print(report['status'])
    for stage in report['stages']:print(stage)
    if 'error' in report:print(report['error'])


if __name__=='__main__':main()
