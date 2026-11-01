"""Read-only return-code framing check, only at the already observed U-Boot prompt."""
from datetime import datetime,timezone
import json,re,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parent))
from p64_once_uart_boot import control,Console,AuditPort,PROMPT
def main():
    with control.operation_lock():
        c=control.Controller('p64-uboot-framing');print(c.out,flush=True);b=None
        try:
            c.ports=control.discover_ports(c.record['ports']);audit=c.out/'UART';audit.mkdir()
            b=Console(c.ports['TX'],c.record,c.save);b.port=AuditPort(b.port,audit)
            b.port.write(b'\r');initial=b.read(3,PROMPT)
            if not re.search(PROMPT,initial,re.M):raise ValueError('Not at known U-Boot prompt; no action')
            for command in ('true; echo _P64:$?','false; echo _P64:$?','version; echo _P64:$?','help fpga; echo _P64:$?'):
                b.port.write((command+'\r').encode());answer=b.read(4,PROMPT)
                c.record['stages'].append(dict(command=command,output=answer));c.save()
            c.record['status']='collected_P64_read_only_UBoot_return_framing'
        except Exception as e:c.record.update(status='failed_framing',error=repr(e))
        finally:
            if b:b.close()
            c.record['serial_closed']=True;c.save();print(c.record['status'])
if __name__=='__main__':main()
