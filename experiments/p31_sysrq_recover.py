"""Recover the Oops-deadlocked UART session using serial kernel SysRq."""
from datetime import datetime,timezone
import json
from pathlib import Path
import time
import serial

ROOT=Path(__file__).resolve().parents[1]


def main():
    out=ROOT/'results'/('p31-sysrq-recovery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    report=dict(status='attempting',stages=[],firmware_writes=False,reason='owned rmdir blocked after axiadc_remove kernel Oops')
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    port=serial.Serial(port=None,baudrate=115200,timeout=.1,write_timeout=3);port.dtr=False;port.rts=False;port.port='COM8'
    def read(seconds):
        until=time.monotonic()+seconds;data=bytearray()
        while time.monotonic()<until:data.extend(port.read(port.in_waiting or 1))
        return data.decode('ascii',errors='replace')
    def sysrq(key,seconds):
        port.send_break(duration=.3);time.sleep(.1);port.write(key.encode('ascii'))
        output=read(seconds);report['stages'].append(dict(sysrq=key,output=output));save();return output
    save()
    try:
        port.open()
        output=sysrq('s',6)
        if not any(term.lower() in output.lower() for term in ['Emergency Sync','SysRq : Sync','Syncing filesystems']):
            report['status']='serial_sysrq_not_observed_no_reboot_sent'
        else:
            output=sysrq('u',6)
            if not any(term.lower() in output.lower() for term in ['Emergency Remount','Remounting filesystems']):
                report['status']='remount_not_observed_no_reboot_sent'
            else:
                output=sysrq('b',28)
                report['status']='kernel_reboot_observed_pending_identity_check' if any(term in output for term in ['U-Boot','Booting Linux','Linux version']) else 'reboot_not_confirmed'
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:
        if port.is_open:port.close()
        save()
    print(out);print(report['status'])
    for item in report['stages']:print(item['sysrq'],item['output'][-2000:])


if __name__=='__main__':main()
