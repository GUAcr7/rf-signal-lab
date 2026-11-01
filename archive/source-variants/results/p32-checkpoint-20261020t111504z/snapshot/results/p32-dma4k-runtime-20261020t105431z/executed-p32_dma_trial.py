"""One fresh-boot factory-PL DMA4K trial; no hot unload, no transmission.

The temporary boot hold restores the prior guarded S99board before any trial.
The factory DTBO, bitstream, BOOT.BIN and base DTB are never replaced.
"""
import argparse
import base64
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import subprocess
import sys
from p32_session import BoardConsole, ROOT


def sha(data):return hashlib.sha256(data).hexdigest()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--build',type=Path,required=True)
    parser.add_argument('--boot-id',required=True)
    args=parser.parse_args()
    if not re.fullmatch(r'[0-9a-f-]{36}',args.boot_id):raise ValueError('boot identity')
    build=json.loads(args.build.read_text('utf-8'))
    candidate=Path(build['dtbo']);data=candidate.read_bytes()
    if build['status']!='factory_resource_only_candidate_verified' or sha(data)!=build['candidate_sha256']:
        raise RuntimeError('candidate validation required')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p32-dma4k-runtime-'+stamp);out.mkdir(exist_ok=False)
    backup='/etc/p32-guard-'+stamp
    guard=(ROOT/'board/boot/S99board').read_bytes();guard_sha=sha(guard)
    template=(ROOT/'board/boot/p32-once-hold.sh.in').read_text('utf-8')
    wrapper=template.replace('@@GUARD@@',backup).replace('@@GUARD_SHA@@',guard_sha).replace('@@ARMED_BOOT@@',args.boot_id).encode()
    (out/'S99board.once').write_bytes(wrapper);(out/'S99board.guard').write_bytes(guard)
    (out/'factory-rf-dma4k.dtbo').write_bytes(data)
    report=dict(status='preflight',stages=[],build=str(args.build.resolve()),armed_boot=args.boot_id,
        guard_sha256=guard_sha,wrapper_sha256=sha(wrapper),backup=backup,
        candidate_sha256=sha(data),ordinary_reboots_issued=0,hot_overlay_removal=False,
        TX_application_started=False,base_DTB_or_BOOT_modified=False,
        factory_firmware_modified=False,trial_overlay_applied=False,guard_restored=False)
    def save(): (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def expect_hash(board,path,digest):
        board.command('p='+path)
        actual=re.search(r'^([0-9a-f]{64})\s',board.command('sha256sum $p'),re.M)
        if not actual or actual[1]!=digest:raise RuntimeError('hash mismatch '+path)
    def boot(board,expected):
        if board.value('/proc/sys/kernel/random/boot_id')!=expected:raise RuntimeError('boot changed')
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        if board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('tainted kernel')
    def idle(board):
        processes=board.command('ps -ef')
        if any(re.search(r'p27-rx|arm-rx-capture|iio_readdev',s) for s in processes.splitlines()):raise RuntimeError('RX process present')
        board.command('p=/sys/bus/iio/devices')
        listing=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        pairs={n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',listing)}
        if 'cf-ad9361-lpc' in pairs:
            board.command('cd '+pairs['cf-ad9361-lpc'])
            if board.value('buffer/enable')!='0':raise RuntimeError('buffer active')
            if any(board.value(f'scan_elements/in_voltage{i}_en')!='0' for i in range(4)):raise RuntimeError('scan active')
        return pairs
    def upload(board,name,payload):
        board.command('s='+ram+'/'+name+'.b64')
        board.command('test ! -e $s')
        for start in range(0,len(payload),36):
            board.command('echo '+base64.b64encode(payload[start:start+36]).decode()+' >> $s')
        remote=ram+'/'+name
        board.command('n='+remote);board.command('base64 -d $s > $n')
        expect_hash(board,remote,sha(payload))
        return remote
    def reboot(board,expected,reason):
        boot(board,expected)
        board.command('cd /')
        board.command('sync',timeout=20)
        report['status']='reboot_intent_'+reason;save()
        board.port.write(b'reboot\r')
        report['ordinary_reboots_issued']+=1;save()
        raw=board.read(55,r'login:\s*$')
        (out/('boot-'+reason+'.txt')).write_text(raw,encoding='utf-8')
        if not re.search(r'U-Boot|Linux version|Booting Linux',raw):raise RuntimeError('no reboot evidence')
        board.shell()
        new=board.value('/proc/sys/kernel/random/boot_id')
        if new==expected:raise RuntimeError('reboot identity unchanged')
        boot(board,new)
        return new
    def run_child(name,command,timeout=120):
        result=subprocess.run([sys.executable,*command],cwd=ROOT,capture_output=True,timeout=timeout)
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        report[name]=dict(exit_code=result.returncode,command=command);save()
        if result.returncode:raise RuntimeError(name+' failed')
        text=result.stdout.decode('utf-8',errors='replace')
        paths=[Path(line.strip()) for line in text.splitlines() if line.strip().startswith(str(ROOT/'results'))]
        if not paths:raise RuntimeError(name+' result path absent')
        report[name]['report']=str(paths[0]/'report.json');save()
        return paths[0]/'report.json'
    board=None;armed=False;held_boot=None
    save()
    try:
        old=BoardConsole('COM9',report,save)
        try:
            if 'Linux pzp201' not in old.command('uname -a'):raise RuntimeError('old board identity')
            if 'arm-tx-source' in old.command('ps'):raise RuntimeError('old TX process active')
        finally:old.close()
        board=BoardConsole('COM8',report,save)
        boot(board,args.boot_id);idle(board)
        if board.value('/etc/board-mode')!='rf':raise RuntimeError('not factory RF mode')
        expect_hash(board,'/etc/rcS.d/S99board',guard_sha)
        expect_hash(board,'/lib/firmware/pl.dtbo',build['original_sha256'])
        expect_hash(board,'/lib/firmware/ad9361.bin','65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a')
        ram='/tmp/p32-arm-'+stamp[9:15]
        board.command('mkdir '+ram)
        remote=upload(board,'once',wrapper)
        board.command('sh -n '+remote)
        board.command('b='+backup);board.command('test ! -e $b')
        board.command('cp -p /etc/rcS.d/S99board $b')
        expect_hash(board,backup,guard_sha)
        board.command('u=/etc/rcS.d/.p32-once')
        board.command('test ! -e $u');board.command('cp '+remote+' $u')
        board.command('chmod 755 $u');expect_hash(board,'/etc/rcS.d/.p32-once',sha(wrapper))
        report['status']='backup_and_staging_verified';save()
        board.command('mv $u /etc/rcS.d/S99board');armed=True
        board.command('sync',timeout=20)
        expect_hash(board,'/etc/rcS.d/S99board',sha(wrapper))
        print('One-shot hold installed with verified persistent factory guard backup.',flush=True)
        held_boot=reboot(board,args.boot_id,'hold')
        report['held_boot']=held_boot
        expect_hash(board,'/etc/rcS.d/S99board',guard_sha)
        report['guard_restored']=True;armed=False;save()
        if board.value('/run/p32-hold-boot')!=held_boot:raise RuntimeError('one-shot marker absent')
        board.command('test -d /sys/kernel/config/device-tree/overlays || true')
        # configfs is not necessarily mounted when S99board is held.
        board.command('mount -t configfs none /sys/kernel/config || true')
        board.command("grep ' configfs ' /proc/mounts")
        overlays=board.command('ls /sys/kernel/config/device-tree/overlays')
        if re.search(r'^pl\r?$',overlays,re.M):raise RuntimeError('existing overlay')
        board.command('d=/sys/kernel/config/device-tree/overlays')
        board.command('test -z "$(ls $d)"')
        names=idle(board)
        if any(n in names for n in ['ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc']):raise RuntimeError('RF already bound')
        board.command('cat /proc/interrupts')
        report['empty_RF_fresh_boot_verified']=True;save()
        print('Fresh boot held; original guard restored; no bound RF driver/overlay.',flush=True)
        ram='/tmp/p32-dma-'+stamp[9:15];board.command('mkdir '+ram)
        remote=upload(board,'dma4k.dtbo',data)
        boot(board,held_boot)
        expect_hash(board,'/lib/firmware/ad9361.bin','65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a')
        board.command('f=/sys/class/fpga_manager/fpga0')
        report['status']='fresh_boot_single_apply_intent';save()
        board.command('echo ad9361.bin > $f/firmware',timeout=30)
        if board.value('$f/state')!='operating':raise RuntimeError('factory PL not operating')
        board.command('mkdir $d/pl')
        board.command('cat '+remote+' > $d/pl/dtbo',timeout=30)
        report['trial_overlay_applied']=True;save()
        board.command('sleep 2')
        board.command('/etc/rcS.d/S99board --check-rf')
        boot(board,held_boot)
        names=idle(board)
        iomem=board.command('cat /proc/iomem')
        for address in ['7c400','7c420']:
            if not re.search(r'\b'+address+r'000-'+address+r'fff\b',iomem,re.I):raise RuntimeError('4KiB resource absent '+address)
        board.command('dmesg | tail -n 100')
        report['DMA4K_probe_and_resource_verified']=True;save()
        print('Both DMA4K resources bound with three RF devices and untainted kernel.',flush=True)
        board.close();board=None
        run_child('restore_trial_rx',['experiments/p26_restore_rx_profile.py'])
        smoke=run_child('trial_smoke',['experiments/p27_smoke.py'])
        run_child('trial_archive',['experiments/p31_archive_sparse.py',str(smoke),'--boot-id',held_boot])
        report['DMA4K_RX_transfer_verified']=True;save()
        board=BoardConsole('COM8',report,save);boot(board,held_boot);idle(board)
        expect_hash(board,'/etc/rcS.d/S99board',guard_sha)
        final_boot=reboot(board,held_boot,'factory_restore')
        report['factory_final_boot']=final_boot
        board.command('/etc/rcS.d/S99board --check-rf')
        expect_hash(board,'/etc/rcS.d/S99board',guard_sha)
        iomem=board.command('cat /proc/iomem')
        if '7c400000-7c40ffff' not in iomem or '7c420000-7c42ffff' not in iomem:raise RuntimeError('factory resource not restored')
        idle(board);board.command('dmesg | tail -n 70')
        report['factory_restore_verified']=True;save()
        board.close();board=None
        run_child('restore_final_rx',['experiments/p26_restore_rx_profile.py'])
        report['status']='fresh_boot_DMA4K_RX_transfer_and_factory_restore_verified'
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
        # No automatic hot rollback. Restored guarded startup handles a later
        # normal reboot; if hold was never booted the recorded backup is intact.
        if armed:report['pending_boot_hold']=True
    finally:
        if board:board.close()
        report['serial_closed']=True;save()
        print(out);print(report['status'],flush=True)
    return 0 if report['status'].endswith('_verified') else 1


if __name__=='__main__':raise SystemExit(main())
