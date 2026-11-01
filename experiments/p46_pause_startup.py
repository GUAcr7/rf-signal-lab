"""Pause next-boot selection while keeping the current merged hardware untouched."""
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p36_full_rx_run import RF_EXPECTED
from p46_preflight import parse_names

def main():
    prior=json.loads((ROOT/'results/p43-enabled-20261022T105320Z/report.json').read_text('utf-8'))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p46-startup-pause-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='checking',stages=[],expected_boot=prior['expected_boot'],RF_operations=False,PL_changes=False,next_boot_selection_paused=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    def digest(path):
        board.command('f='+path);v=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $f'),re.M)
        if len(v)!=1:raise ValueError('ambiguous hash')
        return v[0]
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if board.value('/proc/sys/kernel/random/boot_id')!=prior['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity differs')
        if re.search(r'/run/p42-\d+/monitor|iio_readdev|arm-tx-source',board.command('ps -ef')):raise ValueError('application active')
        board.command('ir=/sys/bus/iio/devices');names=parse_names(board.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        board.command('cd '+names['ad9361-phy'])
        if {k:board.value(k) for k in RF_EXPECTED}!=RF_EXPECTED:raise ValueError('RF profile differs')
        board.command('cd '+names['cf-ad9361-lpc'])
        if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX not idle')
        if digest('/etc/rcS.d/S99board')!=prior['wrapper_sha256'] or digest(prior['installed_directory']+'/original')!=prior['original_guard_sha256']:raise ValueError('startup identity differs')
        board.command('j='+prior['installed_directory']);board.command('z=/etc/rcS.d/.p46-switch');board.command('test ! -e $z')
        board.command('cp $j/original $z');board.command('chmod 755 $z')
        if digest('/etc/rcS.d/.p46-switch')!=prior['original_guard_sha256']:raise ValueError('staging differs')
        board.command('mv $z /etc/rcS.d/S99board');board.command('sync',timeout=20)
        if digest('/etc/rcS.d/S99board')!=prior['original_guard_sha256']:raise ValueError('pause failed')
        r.update(status='passed_idle_startup_selection_paused_no_hardware_reload',next_boot_selection_paused=True)
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
