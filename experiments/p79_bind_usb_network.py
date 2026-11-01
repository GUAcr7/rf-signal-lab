"""Bind existing USB network to the P201 identified through its USB console."""
from pathlib import Path
import json,re,sys
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control
import p201_usb_network as net

def main():
    c=None;t=None
    with control.operation_lock():
        try:
            c=control.Controller('p79-bind-USB-network');print(c.out,flush=True);c.status()
            tx=c.record['boards']['TX'];control.require_tx_off(tx)
            with c.board('TX') as (b,identity):
                c.record['USB_IP']=b.command('ip -4 addr show usb0')
                if '192.168.2.1/24' not in c.record['USB_IP']:raise ValueError('Known USB network address absent')
            t=net.connect('192.168.2.1');key=net.fingerprint(t);net.authenticate(t)
            channel=t.open_session(timeout=5)
            channel.exec_command('id -u; uname -a; cat /sys/firmware/devicetree/base/model; echo; cat /proc/sys/kernel/random/boot_id')
            output=channel.makefile('rb').read().decode('utf-8',errors='replace')
            code=channel.recv_exit_status();channel.close();c.record['network_identity']=output
            if code!=0 or not output.startswith('0\n') or 'Linux pzp201' not in output or 'PUZHI PZSDR P201' not in output or output.splitlines()[-1]!=tx['boot_id']:
                raise ValueError('USB/network identities do not match')
            c.record['binding']=dict(host='192.168.2.1',host_key_sha256=key,boot_id=tx['boot_id'],
                                     USB_port=c.ports['TX'],model='PUZHI PZSDR P201')
            c.record['status']='passed_P79_USB_serial_and_network_same_P201_boot'
        except Exception as error:
            if c:c.record.update(status='failed_P79_USB_network_binding',error=repr(error))
            else:raise
        finally:
            if t:t.close()
            if c:
                c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
                if c.record['status'].startswith('passed_'):
                    net.BINDING.write_text(json.dumps(dict(report=str((c.out/'report.json').relative_to(ROOT)),sha256=control.sha(c.out/'report.json')),indent=2)+'\n',encoding='utf-8')
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
