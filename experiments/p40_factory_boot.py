"""One ordinary factory warm boot after durable checkpoint/idle gates; no retry."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

from p32_session import ROOT, BoardConsole
from p35_once_merged_trial import AuditPort, FACTORY, OVERLAY_HASHES, RF_NAMES

ACTIVE = r'arm-latest|arm[-_]rx|arm[-_]panel|arm-tx-source|iio_readdev|p33-cancel|p35-p3[89]-\d+/a|p36-full'
CRITICAL = r'Internal error:|Kernel panic|Oops:|BUG:'


def classify_factory_boot(log, names, tainted, framebuffer):
    """A logged failed probe is evidence, never a ready or repair verdict."""
    if tainted != '0' or re.search(CRITICAL, log):
        raise ValueError('kernel fault/taint; no retry')
    if framebuffer:
        raise ValueError('unexpected display in factory RF-only mode')
    complete = RF_NAMES <= set(names)
    if 'Unsupported PRODUCT_ID 0xFF' in log:
        if complete:
            raise ValueError('unexpected mixed failed/successful probe history; investigate')
        return 'factory_PRODUCT_ID_FF_observed_no_hot_retry'
    if not complete or 'bring-up complete (mode=rf)' not in log or 'board-init: FAILED:' in log:
        raise ValueError('factory readiness incomplete/unexplained; no retry')
    if len(re.findall(r'overlay applied: /lib/firmware/pl\.dtbo \(attempt 1\)', log)) != 1:
        raise ValueError('expected exactly one factory overlay apply')
    return 'passed_factory_RF_single_apply_warm_boot_only'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--expected-boot',required=True)
    p.add_argument('--checkpoint-report',type=Path,required=True)
    args=p.parse_args()
    checkpoint=json.loads(args.checkpoint_report.read_text('utf-8'))
    if checkpoint['status']!='passed_local_incremental_checkpoint_ZIP_CRC_and_all_file_SHA' or checkpoint['all_ZIP_file_SHA_verified'] is not True:
        raise ValueError('verified durable checkpoint required')
    archive=ROOT/checkpoint['archive']['path']
    if archive.stat().st_size!=checkpoint['archive']['bytes'] or hashlib.sha256(archive.read_bytes()).hexdigest()!=checkpoint['archive']['sha256']:
        raise ValueError('checkpoint bytes changed')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p40-factory-boot-'+stamp);out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=args.expected_boot,
        checkpoint_report=str(args.checkpoint_report.resolve()),
        checkpoint_report_sha256=hashlib.sha256(args.checkpoint_report.read_bytes()).hexdigest(),
        ordinary_reboots_issued=0,hot_overlay_removal=False,automatic_retry=False,
        firmware_or_startup_writes=False,TX_operations=False,RF_attribute_writes=False,
        cold_power_cycle=False,PRODUCT_ID_FF_root_cause_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None
    def identity(expected=None):
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('wrong new board')
        actual=board.value('/proc/sys/kernel/random/boot_id')
        if expected and actual!=expected:raise ValueError('new board boot changed')
        if board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('kernel tainted')
        return actual
    def digest(path):
        board.command('p='+path)
        hashes=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $p'),re.M)
        if len(hashes)!=1:raise ValueError('ambiguous file digest')
        return hashes[0]
    guard_sha=hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
    def files():
        if board.value('/etc/board-mode')!='rf' or digest('/etc/rcS.d/S99board')!=guard_sha:
            raise ValueError('mode/guard changed')
        for name,wanted in {**FACTORY,**OVERLAY_HASHES}.items():
            if name=='system_wrapper.bin':continue
            if digest('/lib/firmware/'+name)!=wanted:raise ValueError('factory artifact changed: '+name)
        staged=digest('/lib/firmware/system_wrapper.bin')
        if staged not in (FACTORY['system_wrapper.bin'],FACTORY['ad9361.bin']):raise ValueError('unknown staging file')
        board.command('test ! -e /etc/rcS.d/.p35-restore')
        return staged
    def idle():
        if re.search(ACTIVE,board.command('ps -ef')):raise ValueError('active experiment; no reboot')
        board.command('ir=/sys/bus/iio/devices')
        text=board.command('for d in $ir/iio:device*;do echo $d;cat $d/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)
        if len({n for _,n in pairs})!=len(pairs):raise ValueError('ambiguous IIO names')
        names={n:path for path,n in pairs}
        if 'cf-ad9361-lpc' in names:
            board.command('cd '+names['cf-ad9361-lpc'])
            if board.value('buffer/enable')!='0' or any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):
                raise ValueError('active scan/buffer; no reboot')
        return names
    save()
    try:
        board=BoardConsole('COM9',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Linux pzp201' not in board.command('uname -a'):raise ValueError('wrong old board')
        if re.search(ACTIVE,board.command('ps')):raise ValueError('old board active; no reboot')
        r['old_board_boot']=board.value('/proc/sys/kernel/random/boot_id');board.close();board=None
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        identity(args.expected_boot);r['staging_before']=files();names=idle()
        if not RF_NAMES<=set(names):raise ValueError('starting state is not RF ready')
        board.command('/etc/rcS.d/S99board --check-rf')
        r['dmesg_before']=board.command('dmesg',timeout=25)
        if re.search(CRITICAL,r['dmesg_before']):raise ValueError('prior kernel fault')
        board.command('sync',timeout=20)
        r['status']='ordinary_reboot_intent_saved';save()
        board.port.write(b'reboot\r');r['ordinary_reboots_issued']=1;save()
        boot=''
        for _ in range(2):
            boot+=board.read(45,r'login:\s*$')
            (out/'factory-boot.txt').write_text(boot,encoding='utf-8')
            if re.search(r'login:\s*$',boot):break
        if not re.search(r'U-Boot|Linux version|Booting Linux',boot) or not re.search(r'login:\s*$',boot):
            raise ValueError('fresh ordinary boot/login not observed')
        board.shell();actual=identity()
        if actual==args.expected_boot:raise ValueError('boot identity did not change')
        r['boot_after']=actual;r['staging_after']=files()
        if r['staging_after']!=FACTORY['ad9361.bin']:raise ValueError('factory RF staging not restored')
        names=idle();r['IIO_names_after']=sorted(names)
        r['fabric_after']=board.value('/sys/class/fpga_manager/fpga0/state')
        if r['fabric_after']!='operating':raise ValueError('factory PL not operating')
        log=board.command('dmesg',timeout=25);r['dmesg_after']=log
        (out/'dmesg.txt').write_text(log,encoding='utf-8')
        frame=board.command('if test -e /dev/fb0;then echo FB;else echo NONE;fi')
        values=re.findall(r'^(FB|NONE)\r?$',frame,re.M)
        if len(values)!=1:raise ValueError('framebuffer state ambiguous')
        r['framebuffer_present']=values[0]=='FB'
        r['status']=classify_factory_boot(log,names,board.value('/proc/sys/kernel/tainted'),r['framebuffer_present'])
        r['kernel_tainted_after']=0;r['idle_verified_after']=True
        if r['status'].startswith('passed_'):board.command('/etc/rcS.d/S99board --check-rf')
    except Exception as exc:
        r.update(status='failed_or_state_unconfirmed',error=repr(exc))
        if board:
            try:r['passive_tail']=board.read(3)
            except Exception as tail:r['passive_tail_error']=repr(tail)
    finally:
        if board:board.close()
        r['serial_closed']=True;r['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    print(out);print(r['status'])
    return 0 if r['status'].startswith('passed_') else 1


if __name__=='__main__':raise SystemExit(main())
