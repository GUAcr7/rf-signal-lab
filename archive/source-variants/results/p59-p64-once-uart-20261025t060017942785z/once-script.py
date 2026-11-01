"""One-shot UART-only U-Boot experiment, no default boot file changes.

Requires the human-confirmed empty J19 header. Programs PL only in U-Boot,
before Linux/drivers. No RF trial, hot driver unload or flash write occurs.
An ordinary subsequent boot restores the unchanged original BOOT/DTB.
"""
from datetime import datetime,timezone
import http.server,importlib.util,json,re,sys,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments')]
spec=importlib.util.spec_from_file_location('p64_once_control',ROOT/'host/board_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
STAGE=ROOT/'results/p59-p64-stage-uart-20261025T055702382078Z/report.json'
TOOL=ROOT/'results/p64-internal-build-20261025T055701Z/report.json'
PROMPT=r'(?:^|\n)Pluto> ?$'

def main():
    staged=json.loads(STAGE.read_text(encoding='utf-8'));tool=json.loads(TOOL.read_text(encoding='utf-8'))
    if staged['status']!='passed_P64_two_SD_artifacts_staged_original_boot_unchanged_not_activated':raise ValueError('Stage incomplete')
    if tool['status']!='passed_P64_internal_tool_build_refusals_not_board_test':raise ValueError('Tool incomplete')
    binary=ROOT/tool['binary'];payload=binary.read_bytes()
    if control.sha(binary)!=tool['binary_sha256']:raise ValueError('Tool SHA changed')
    c=None;b=None;server=None;worker=None
    with control.operation_lock():
        try:
            c=control.Controller('p64-once-uart');print(c.out,flush=True)
            c.ports=control.discover_ports(c.record['ports'])
            c.record.update(J19_empty_confirmed_by_human=True,default_boot_files_changed=False,
                stage_report=str(STAGE.relative_to(ROOT)),stage_sha256=control.sha(STAGE),
                tool_report=str(TOOL.relative_to(ROOT)),tool_sha256=control.sha(TOOL),
                experiment_scope='UART-only; inherited full-system CDC/IO and RF not released')
            (c.out/'once-script.py').write_bytes(Path(__file__).read_bytes())
            audit=c.out/'UART';audit.mkdir()
            b=Console(c.ports['TX'],c.record,c.save);b.port=AuditPort(b.port,audit);b.shell()
            identity=b.command('uname -a')
            if 'Linux pzp201' not in identity:raise ValueError('Wrong board')
            b.command("PS1=''");b.command('stty -echo')
            before=c.inspect('TX',b,identity);control.require_tx_off(before)
            if before['boot_id']!=staged['after_TX']['boot_id']:raise ValueError('Stage boot changed')
            c.record['before_TX']=before;b.command('sync');c.save()
            # reboot cannot use framed shell commands: the shell is ending.
            b.port.write(b'reboot\r');c.record['reboots_issued']=1;c.save()
            banner=b.read(25,r'Hit any key to stop autoboot:')
            c.record['reboot_banner']=banner;c.save()
            if 'Hit any key to stop autoboot:' not in banner:raise ValueError('Autoboot interrupt window not observed')
            b.port.write(b' ');answer=b.read(5,PROMPT);c.record['interrupted_prompt']=answer
            if not re.search(PROMPT,answer,re.M):raise ValueError('U-Boot prompt not established')
            c.record['in_uboot']=True;c.save()
            def ub(command,timeout=12):
                if len(command)>72 or '\n' in command or '\r' in command:raise ValueError('Short U-Boot command required')
                b.port.write((command+'\r').encode('ascii'));text=b.read(timeout,PROMPT)
                if not re.search(PROMPT,text,re.M):raise ValueError('U-Boot command prompt missing: '+command)
                token='__P64_RC__';b.port.write(('echo '+token+':$?\r').encode('ascii'))
                ending=b.read(3,PROMPT);matches=re.findall(r'^'+token+r':(\d+)\r?$',ending,re.M)
                rc=int(matches[0]) if len(matches)==1 else None
                c.record['stages'].append(dict(stage='UBoot',command=command,output=text,return_frame=ending,exit_code=rc));c.save()
                if rc!=0:raise ValueError('U-Boot command failed: '+command)
                return text
            if 'loadb' not in ub('help fpga'):raise ValueError('loadb unsupported')
            ub('version');ub('printenv bootargs');ub('mmcinfo')
            def load(address,name,expected):
                text=ub('load mmc 0 '+address+' '+name)
                values=re.findall(r'(\d+) bytes read',text)
                if values!=[str(expected)]:raise ValueError('Unexpected loaded byte count '+name)
            bitpath=ROOT/'results/p64-uart-bit-20261025T054717Z/uart-experiment.bit'
            dtpath=ROOT/'results/p201-uart-candidate-20261024T023801Z/candidate.dtb'
            for name,p in [('p64-uart.bit',bitpath),('p64-uart.dtb',dtpath)]:
                if control.sha(p)!=staged['added_SD_files'][name]:raise ValueError('Staged input changed')
            load('0x100000','p64-uart.bit',bitpath.stat().st_size)
            ub('fpga loadb 0 0x100000 ${filesize}',30)
            c.record.update(PL_changes=True,PL_programming_in_UBoot=1,PL_programming_after_Linux=False);c.save()
            load('0x2080000','uImage',Path('D:/FPGA natch/pluto/uImage').stat().st_size)
            ub('iminfo 0x2080000')
            load('0x4000000','uramdisk.image.gz',Path('D:/FPGA natch/pluto/uramdisk.image.gz').stat().st_size)
            ub('iminfo 0x4000000')
            load('0x2000000','p64-uart.dtb',dtpath.stat().st_size)
            ub('fdt addr 0x2000000')
            if 'okay' not in ub('fdt print /amba/serial@e0000000 status'):raise ValueError('UART DTB not enabled')
            ub('fdt print /aliases serial0');ub('fdt print /aliases serial1')
            b.port.write(b'bootm 0x2080000 0x4000000 0x2000000\r')
            c.record['Linux_boot_log']=b.read(45,r'(?:login:|[^\r\n]*#)\s*$');c.record['in_uboot']=False;c.save()
            b.shell();b.command("PS1=''");b.command('stty -echo')
            identity=b.command('uname -a')
            if 'Linux pzp201' not in identity:raise ValueError('Wrong postboot identity')
            fresh=c.inspect('TX',b,identity);c.record['new_boot_before_DDS_zero']=fresh
            if fresh['boot_id']==before['boot_id'] or fresh['taint']!='0' or fresh['TX_buffer']!='0' or fresh['TX_process_observed']:
                raise ValueError('Fresh idle untainted boot not proven')
            b.command('cd '+fresh['IIO_names']['cf-ad9361-dds-core-lpc'])
            b.command('for n in out_altvoltage*_scale;do echo 0 >$n;done')
            b.command('for n in out_altvoltage*_raw;do echo 0 >$n;done')
            c.record['DDS_controls_zeroed_after_boot']=True;c.save()
            link=b.command('readlink -f /sys/class/tty/ttyPS1/device');c.record['UART1_sysfs_device']=link
            if '/e0000000.serial' not in link and '/e0000000.uart' not in link:raise ValueError('UART0 device missing or wrong')
            c.record['clock_readback']=b.command('cat /sys/kernel/debug/clk/clk_summary')
            control.board_ram_tmp(b)
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path!='/internal':self.send_error(404);return
                    self.send_response(200);self.send_header('Content-Length',str(len(payload)))
                    self.end_headers();self.wfile.write(payload)
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('192.168.2.10',0),Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            directory='/tmp/p35-p64i-'+datetime.now(timezone.utc).strftime('%H%M%S')
            b.command('d='+directory);b.command('mkdir $d');b.command('u=$d/internal')
            b.command('h=http://192.168.2.10:'+str(server.server_port)+'/internal')
            b.command('wget -q -T 10 -O $u $h',timeout=15)
            if c.digest(b,directory+'/internal')!=tool['binary_sha256']:raise ValueError('Helper transfer mismatch')
            b.command('chmod 755 $u')
            result=control.one_json(b.command('$u --device /dev/ttyPS1 --run-internal',timeout=8))
            c.record['internal_loopback']=result
            if result.get('status')!='pass' or result.get('sent')!=512 or result.get('received')!=512 or not result.get('controls_restored'):
                raise ValueError('Internal loopback not complete')
            after=c.inspect('TX',b,identity);control.require_tx_off(after);c.record['after_TX']=after
            c.record['status']='passed_P64_one_shot_UART0_driver_internal_loopback_not_physical_pins_or_RF'
        except Exception as e:
            if c:c.record.update(status='failed_or_incomplete_P64_once_UART',error=repr(e))
            else:raise
        finally:
            if server:server.shutdown();server.server_close()
            if worker:worker.join(2)
            if b:
                if c and c.record.get('status','').startswith('passed_'):
                    try:b.command('stty echo');b.command("PS1='# '")
                    except Exception as error:c.record['console_restore_error']=repr(error)
                b.close()
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
