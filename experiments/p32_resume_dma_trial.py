"""Resume ONLY the archived pre-apply variable failure; never reload/unload PL."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from p32_session import BoardConsole,ROOT


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('previous',type=Path)
    args=parser.parse_args()
    previous=json.loads(args.previous.read_text('utf-8'))
    if previous['status']!='failed' or previous.get('trial_overlay_applied') or not previous.get('guard_restored'):
        raise RuntimeError('wrong failed phase')
    if previous.get('error')!="RuntimeError('COM8 command failed rc=1: mkdir $d/pl')":
        raise RuntimeError('only the exact pre-apply path-variable error is resumable')
    expected=previous['held_boot']
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p32-dma4k-resume-'+stamp);out.mkdir(exist_ok=False)
    report=dict(status='checking_fresh_held_boot',stages=[],previous=str(args.previous.resolve()),
        held_boot=expected,trial_overlay_applied=False,hot_overlay_removal=False,
        PL_reloaded=False,TX_application_started=False,ordinary_reboots_issued=0)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def hashcheck(board,path,digest):
        board.command('p='+path)
        output=board.command('sha256sum $p')
        actual=re.search(r'^([0-9a-f]{64})\s',output,re.M)
        if not actual or actual[1]!=digest:raise RuntimeError('hash mismatch '+path)
    def identity(board,boot):
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=boot:
            raise RuntimeError('wrong board/boot')
        if board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('kernel tainted')
    def child(name,arguments):
        result=subprocess.run([sys.executable,*arguments],cwd=ROOT,capture_output=True,timeout=120)
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        report[name]=dict(exit_code=result.returncode,arguments=arguments);save()
        if result.returncode:raise RuntimeError(name+' failed')
        paths=[Path(line.strip()) for line in result.stdout.decode('utf-8',errors='replace').splitlines() if line.strip().startswith(str(ROOT/'results'))]
        if not paths:raise RuntimeError(name+' report path missing')
        report[name]['report']=str(paths[0]/'report.json');save()
        return paths[0]/'report.json'
    board=None;save()
    try:
        board=BoardConsole('COM8',report,save);identity(board,expected)
        if board.value('/run/p32-hold-boot')!=expected:raise RuntimeError('hold marker absent')
        guard=hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
        hashcheck(board,'/etc/rcS.d/S99board',guard)
        report['guard_restored']=True
        board.command('ov=/sys/kernel/config/device-tree/overlays')
        board.command('test -z "$(ls $ov)"')
        board.command('p=/sys/bus/iio/devices')
        names=board.command('for d in $p/iio:device*; do cat $d/name; done')
        if any(re.search(r'^'+re.escape(n)+r'\r?$',names,re.M) for n in ['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']):raise RuntimeError('RF already bound')
        if board.value('/sys/class/fpga_manager/fpga0/state')!='operating':raise RuntimeError('factory PL not operating')
        remote='/tmp/p32-dma-'+previous['backup'].split('T')[1][:6]+'/dma4k.dtbo'
        hashcheck(board,remote,previous['candidate_sha256'])
        report['status']='single_apply_intent_after_empty_RF_recheck';save()
        board.command('mkdir $ov/pl')
        board.command('cat '+remote+' > $ov/pl/dtbo',timeout=30)
        report['trial_overlay_applied']=True;save()
        board.command('sleep 2')
        board.command('/etc/rcS.d/S99board --check-rf')
        identity(board,expected)
        iomem=board.command('cat /proc/iomem')
        for address in ['7c400','7c420']:
            if not re.search(r'\b'+address+r'000-'+address+r'fff\b',iomem,re.I):raise RuntimeError('4KiB resource missing')
        board.command('dmesg | tail -n 100')
        report['DMA4K_probe_and_resource_verified']=True;save()
        print('DMA4K candidate probed with three RF devices; kernel taint zero.',flush=True)
        board.close();board=None
        child('restore_trial_rx',['experiments/p26_restore_rx_profile.py'])
        smoke=child('trial_smoke',['experiments/p27_smoke.py'])
        child('trial_archive',['experiments/p31_archive_sparse.py',str(smoke),'--boot-id',expected])
        report['DMA4K_RX_transfer_verified']=True;save()
        board=BoardConsole('COM8',report,save);identity(board,expected)
        hashcheck(board,'/etc/rcS.d/S99board',guard)
        board.command('cd /');board.command('sync',timeout=20)
        report['status']='factory_reboot_intent';save()
        board.port.write(b'reboot\r');report['ordinary_reboots_issued']=1;save()
        raw=board.read(55,r'login:\s*$')
        (out/'boot-factory-restore.txt').write_text(raw,encoding='utf-8')
        if not re.search(r'U-Boot|Linux version|Booting Linux',raw):raise RuntimeError('reboot evidence absent')
        board.shell()
        final=board.value('/proc/sys/kernel/random/boot_id')
        if final==expected:raise RuntimeError('boot unchanged')
        identity(board,final);report['factory_final_boot']=final
        board.command('/etc/rcS.d/S99board --check-rf')
        hashcheck(board,'/etc/rcS.d/S99board',guard)
        iomem=board.command('cat /proc/iomem')
        if '7c400000-7c40ffff' not in iomem or '7c420000-7c42ffff' not in iomem:raise RuntimeError('factory resource not restored')
        board.command('dmesg | tail -n 65')
        report['factory_restore_verified']=True;save()
        board.close();board=None
        child('restore_final_rx',['experiments/p26_restore_rx_profile.py'])
        report['status']='fresh_boot_DMA4K_RX_transfer_and_factory_restore_verified'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        report['serial_closed']=True;save();print(out);print(report['status'])
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
