"""Restore hash-pinned factory disk files without unloading or reconfiguring PL."""
import argparse
from datetime import datetime,timezone
import json
import re
from p32_session import ROOT,BoardConsole

EXPECTED={
 'ad9361.bin':'65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a',
 'display.bin':'12566368b747728d00dda1e6774ff708b3d1a67fa37b38268bdaa8957f11286e',
 'system_wrapper.bin':'12566368b747728d00dda1e6774ff708b3d1a67fa37b38268bdaa8957f11286e'}

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    args=parser.parse_args()
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-restore-vendor-files-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    record=dict(status='preflight',stages=[],expected_boot=args.expected_boot,
        changes='factory disk files only',reboot=False,PL_reconfigured=False,
        overlay_operations=False,RF_writes=False)
    def save():(out/'report.json').write_text(json.dumps(record,indent=2)+'\n',encoding='utf-8')
    board=None
    def digest(path):
        result=board.command('sha256sum '+path)
        rows=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',result,re.M)
        if len(rows)!=1:raise RuntimeError('ambiguous hash '+path)
        return rows[0]
    try:
        board=BoardConsole('COM8',record,save);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if board.value('/proc/sys/kernel/random/boot_id')!=args.expected_boot:
            raise RuntimeError('boot changed, inspect again')
        if board.value('/etc/board-mode')!='rf':raise RuntimeError('unexpected current mode')
        board.command('/etc/rcS.d/S99board --check-rf')
        if board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('kernel tainted')
        board.command('cd /lib/firmware')
        record['before']={name:digest(name) for name in EXPECTED}
        record['backup_hashes']={name:digest(name+'.vb') for name in EXPECTED}
        if record['backup_hashes']!=EXPECTED:raise RuntimeError('factory backup hash mismatch')
        record['restored']=[];save()
        for name,expected in EXPECTED.items():
            temporary=name+'.p35tmp'
            board.command('test ! -e '+temporary)
            board.command('cp -p '+name+'.vb '+temporary)
            if digest(temporary)!=expected:raise RuntimeError('copied file hash mismatch')
            board.command('mv -f '+temporary+' '+name)
            if digest(name)!=expected:raise RuntimeError('installed file hash mismatch')
            record['restored'].append(name);save()
        board.command('sync')
        record['after']={name:digest(name) for name in EXPECTED}
        if digest('d480p.dtbo')!='7e740c420973a09630575c416f7acf8ab74ff91a9fd058e6227e09eccd4d03f5':
            raise RuntimeError('display overlay is not factory original')
        if digest('pl.dtbo')!='434855ac7488369a4a782c2f6be5c742e4ea62861773d3b671d0792e971e139f':
            raise RuntimeError('RF overlay is not factory original')
        board.command('/etc/rcS.d/S99board --check-rf')
        record['boot_after']=board.value('/proc/sys/kernel/random/boot_id')
        record['tainted_after']=board.value('/proc/sys/kernel/tainted')
        if record['boot_after']!=args.expected_boot or record['tainted_after']!='0':
            raise RuntimeError('board state changed')
        record['status']='factory_disk_files_restored_verified_running_PL_unchanged'
    except Exception as exc:record.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        record['serial_closed']=True;save();print(out);print(record['status'])
    return 0 if record['status'].startswith('factory_') else 1

if __name__=='__main__':raise SystemExit(main())
