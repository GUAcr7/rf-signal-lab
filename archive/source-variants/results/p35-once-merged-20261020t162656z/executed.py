"""One fresh-boot TTL33 explicit-load trial. Run only by the parent operator.

No default firmware/overlay/BOOT/base-DTB replacement, permanent mode change,
automatic TX, hot overlay removal, automatic apply retry, or hot rollback.
The temporary S99 hold restores the verified original guard before this trial.
After success the merged design stays running for separately authorized tests;
a later ordinary reboot uses unchanged factory RF disk files and original guard.
"""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import time
from p30_display_profile import properties
from p32_session import BoardConsole, ROOT
from p35_restore_vendor_files import EXPECTED as FACTORY
from p35_uart_files import upload

OVERLAY_HASHES={
    'pl.dtbo':'434855ac7488369a4a782c2f6be5c742e4ea62861773d3b671d0792e971e139f',
    'd480p.dtbo':'7e740c420973a09630575c416f7acf8ab74ff91a9fd058e6227e09eccd4d03f5'}
RF_NAMES={'ad9361-phy','cf-ad9361-lpc','cf-ad9361-dds-core-lpc'}

def sha(data):return hashlib.sha256(data).hexdigest()

def validate_inputs(bit_path,overlay_path):
    bit=json.loads(bit_path.read_text('utf-8'))
    overlay=json.loads(overlay_path.read_text('utf-8'))
    if bit.get('schema')!='rfsig.p35_ttl_bitstream.v1' or bit.get('status')!='passed_TTL33_native_bin_not_deployed':
        raise RuntimeError('unaccepted native TTL33 bitstream report')
    for key in ['native_bin_verified','TTL33_clock_verified','no_auxiliary_LVDS_PLL']:
        if bit.get(key) is not True:raise RuntimeError('bitstream gate not passed: '+key)
    if bit.get('factory_firmware_sha256')!=FACTORY:
        raise RuntimeError('factory firmware hash contract mismatch')
    if overlay.get('schema')!='rfsig.p35_explicit_overlay.v1' or overlay.get('status')!='passed_PC_only_explicit_load_overlay_not_deployed':
        raise RuntimeError('unaccepted explicit-load overlay report')
    if not overlay.get('checks') or not all(c.get('passed') is True for c in overlay['checks']):
        raise RuntimeError('overlay structural checks missing/failed')
    if overlay.get('candidate_BD_sha256')!=bit.get('candidate_BD_sha256'):
        raise RuntimeError('bitstream/overlay BD mismatch')
    for record in [bit,overlay]:
        bd=Path(record['candidate_BD'])
        if sha(bd.read_bytes())!=record['candidate_BD_sha256']:
            raise RuntimeError('paired BD changed since validation')
    paired=Path(overlay['paired_report'])
    if sha(paired.read_bytes())!=overlay['paired_report_sha256']:
        raise RuntimeError('paired P33 overlay provenance changed')
    source=Path(overlay['candidate_source'])
    if sha(source.read_bytes())!=overlay['candidate_source_sha256']:
        raise RuntimeError('overlay source changed')
    binary=Path(bit['bitstream']).read_bytes()
    dtbo=Path(overlay['dtbo']).read_bytes()
    if sha(binary)!=bit['bitstream_sha256'] or len(binary)!=bit['bitstream_bytes']:
        raise RuntimeError('native bitstream bytes changed')
    # This is the pinned native loader format, not a generic .bit-header trim.
    if len(binary)>8*1024*1024 or not binary.startswith(b'\xff'*32+b'\x00\x00\x00\xbb\x11\x22\x00\x44'):
        raise RuntimeError('unsupported native bitstream prefix/size')
    if sha(dtbo)!=overlay['dtbo_sha256']:
        raise RuntimeError('overlay bytes changed')
    if any(p.endswith('/firmware-name') for p in properties(dtbo)):
        raise RuntimeError('overlay must not trigger a second FPGA programming')
    return bit,overlay,binary,dtbo

def render_hold(backup,digest,boot_id):
    if not re.fullmatch(r'/etc/p35-guard-[0-9TZ]+',backup):raise ValueError('backup path')
    if not re.fullmatch(r'[0-9a-f]{64}',digest):raise ValueError('guard SHA')
    if not re.fullmatch(r'[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}',boot_id):raise ValueError('boot ID')
    source=(ROOT/'board/boot/p35-once-hold.sh.in').read_text('utf-8')
    text=source.replace('@@GUARD@@',backup).replace('@@GUARD_SHA@@',digest).replace('@@ARMED_BOOT@@',boot_id)
    if '@@' in text:raise RuntimeError('unsubstituted hold placeholder')
    return text.encode('ascii')

def clock_rates(text):
    # Supplied 4.9 clk_summary: name, enable_cnt, prepare_cnt, rate, accuracy,
    # phase. A different column contract is not silently interpreted.
    if not re.search(r'clock\s+enable_cnt\s+prepare_cnt\s+rate\s+accuracy\s+phase',text):
        raise RuntimeError('unknown clk_summary column contract')
    rates={}
    for name,rate in re.findall(r'^\s*(\S+)\s+\d+\s+\d+\s+(\d+)\s+\d+\s+[-\d]+',text,re.M):
        if name in rates:raise RuntimeError('duplicate clock name '+name)
        rates[name]=int(rate)
    return rates

class AuditPort:
    """Record every UART byte actually read, including upload drain traffic."""
    def __init__(self,port,out):
        self.wrapped=port
        self.rx=(out/'uart.rx.bin').open('ab',buffering=0)
        self.tx=(out/'uart.tx.bin').open('ab',buffering=0)
        self.redact_next=False
    def __getattr__(self,name):return getattr(self.wrapped,name)
    def read(self,*args):
        data=self.wrapped.read(*args)
        self.rx.write(data)
        if b'Password:' in data:self.redact_next=True
        return data
    def write(self,data):
        sensitive=self.redact_next or data==b'analog\r'
        self.tx.write(b'<credential redacted>\r' if sensitive else data)
        self.redact_next=False
        return self.wrapped.write(data)
    def close(self):
        try:self.wrapped.close()
        finally:self.rx.close();self.tx.close()

class TrialConsole(BoardConsole):
    def __init__(self,port,record,save,out):
        super().__init__(port,record,save)
        self.port=AuditPort(self.port,out)
    def read(self,seconds,pattern=None):
        if seconds>45:raise ValueError('UART reads are bounded to 45 seconds')
        return super().read(seconds,pattern)

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--expected-boot',required=True)
    parser.add_argument('--bitstream-report',type=Path,required=True)
    parser.add_argument('--overlay-report',type=Path,required=True)
    args=parser.parse_args()
    bit,overlay,binary,dtbo=validate_inputs(args.bitstream_report,args.overlay_report)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p35-once-merged-'+stamp);out.mkdir(exist_ok=False)
    guard=(ROOT/'board/boot/S99board').read_bytes();guard_sha=sha(guard)
    backup='/etc/p35-guard-'+stamp
    wrapper=render_hold(backup,guard_sha,args.expected_boot)
    firmware_name='p35-ttl-'+stamp+'.bin'
    overlay_name='p35-merged-'+stamp+'.dtbo'
    report=dict(schema='rfsig.p35_once_merged.v1',status='preflight',stages=[],
        expected_boot=args.expected_boot,bitstream_report=str(args.bitstream_report.resolve()),
        bitstream_report_sha256=sha(args.bitstream_report.read_bytes()),
        overlay_report=str(args.overlay_report.resolve()),overlay_report_sha256=sha(args.overlay_report.read_bytes()),
        candidate_BD_sha256=bit['candidate_BD_sha256'],
        bitstream_sha256=sha(binary),overlay_sha256=sha(dtbo),guard_sha256=guard_sha,
        wrapper_sha256=sha(wrapper),backup=backup,factory_firmware_sha256=FACTORY,
        unique_firmware_name=firmware_name,unique_overlay_name=overlay_name,
        default_firmware_replaced=False,BOOT_or_base_DTB_modified=False,mode_modified=False,
        hot_overlay_removal=False,automatic_TX=False,automatic_retry=False,temporary_startup_hold_installed=False,
        guard_restored=False,reboots_issued=0,PL_programming_attempts=0,overlay_apply_attempts=0,
        limits=['Probe and software clock readback only; no physical LOCK/pixel-frequency proof',
            'No RF data capture or simultaneous sustained throughput in this script',
            'After success merged design remains live; a later ordinary reboot returns factory RF startup'])
    for name,data in [('S99board.guard',guard),('S99board.once',wrapper),('candidate.bin',binary),('candidate.dtbo',dtbo),('executed.py',Path(__file__).read_bytes()),('hold-template.sh.in',(ROOT/'board/boot/p35-once-hold.sh.in').read_bytes()),('bitstream-report.json',args.bitstream_report.read_bytes()),('overlay-report.json',args.overlay_report.read_bytes())]:
        (out/name).write_bytes(data)
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def phase(value):report['status']=value;report['phase_utc']=datetime.now(timezone.utc).isoformat();save()
    def expect_hash(path,digest):
        board.command('p='+path)
        matches=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',board.command('sha256sum $p'),re.M)
        if matches!=[digest]:raise RuntimeError('hash mismatch '+path)
    def identity(expected):
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong board')
        actual=board.value('/proc/sys/kernel/random/boot_id')
        if actual!=expected:raise RuntimeError('boot changed')
        if board.value('/proc/sys/kernel/tainted')!='0':raise RuntimeError('kernel tainted')
    def factory_files():
        for name,digest in {**FACTORY,**OVERLAY_HASHES}.items():expect_hash('/lib/firmware/'+name,digest)
        if board.value('/etc/board-mode')!='rf':raise RuntimeError('factory RF mode required')
    def idle_names():
        if re.search(r'arm[-_]panel|arm[-_]rx|p27-rx|iio_readdev|arm-tx-source',board.command('ps -ef')):
            raise RuntimeError('an experiment application is active')
        board.command('p=/sys/bus/iio/devices')
        text=board.command('for d in $p/iio:device*; do echo $d; cat $d/name; done')
        names={n:p for p,n in re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',text)}
        if 'cf-ad9361-lpc' in names:
            board.command('cd '+names['cf-ad9361-lpc'])
            if board.value('buffer/enable')!='0' or any(board.value(f'scan_elements/in_voltage{i}_en')!='0' for i in range(4)):
                raise RuntimeError('RX buffer or scan is active')
        return names
    board=None;armed=False
    save()
    try:
        board=TrialConsole('COM8',report,save,out);board.shell()
        # Echo may have been disabled by an interrupted earlier upload.
        board.port.write(b'stty echo\r');board.read(.4)
        identity(args.expected_boot);idle_names();factory_files()
        expect_hash('/etc/rcS.d/S99board',guard_sha)
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('test ! -e /etc/rcS.d/.p35-restore')
        ram='/tmp/p35-'+stamp[9:15];board.command('mkdir '+ram)
        phase('uploading_independent_artifacts')
        for name,data,destination in [('pl',binary,'/lib/firmware/'+firmware_name),('ov',dtbo,'/lib/firmware/'+overlay_name)]:
            remote=ram+'/'+name
            upload(board,remote,data)
            board.command('p='+destination);board.command('test ! -e $p')
            board.command('cp '+remote+' $p');expect_hash(destination,sha(data))
        remote=ram+'/once';upload(board,remote,wrapper);board.command('sh -n '+remote)
        # A long upload must not silently bind an arm/reboot to a changed boot.
        identity(args.expected_boot);idle_names();factory_files()
        expect_hash('/etc/rcS.d/S99board',guard_sha)
        board.command('b='+backup);board.command('test ! -e $b')
        board.command('cp -p /etc/rcS.d/S99board $b');expect_hash(backup,guard_sha)
        board.command('u=/etc/rcS.d/.p35-once')
        board.command('test ! -e $u');board.command('cp '+remote+' $u');board.command('chmod 755 $u')
        expect_hash('/etc/rcS.d/.p35-once',sha(wrapper))
        phase('verified_one_shot_arm_intent')
        board.command('mv $u /etc/rcS.d/S99board');armed=True
        report['temporary_startup_hold_installed']=True;save()
        expect_hash('/etc/rcS.d/S99board',sha(wrapper));board.command('sync',timeout=20)
        phase('ordinary_reboot_to_fresh_hold_intent')
        board.port.write(b'reboot\r');report['reboots_issued']=1;save()
        boot_text=''
        for _ in range(2):
            boot_text+=board.read(45,r'login:\s*$')
            (out/'hold-boot.txt').write_text(boot_text,encoding='utf-8')
            if re.search(r'login:\s*$',boot_text):break
        if not re.search(r'U-Boot|Linux version|Booting Linux',boot_text):raise RuntimeError('no reboot evidence')
        if not re.search(r'login:\s*$',boot_text):raise RuntimeError('fresh boot did not reach login')
        board.shell()
        held=board.value('/proc/sys/kernel/random/boot_id')
        if held==args.expected_boot:raise RuntimeError('boot identity unchanged')
        identity(held);report['held_boot']=held
        expect_hash('/etc/rcS.d/S99board',guard_sha)
        report['guard_restored']=True;armed=False;save()
        if board.value('/run/p35-hold-boot')!=held:raise RuntimeError('fresh hold marker absent')
        factory_files()
        board.command('mount -t configfs none /sys/kernel/config || true')
        board.command("grep ' /sys/kernel/config configfs ' /proc/mounts")
        board.command('ov=/sys/kernel/config/device-tree/overlays')
        board.command('test -z "$(ls -A $ov)"')
        board.command('test ! -e /dev/fb0');board.command('test ! -e /dev/dri/card0')
        if RF_NAMES & set(idle_names()):raise RuntimeError('RF driver already bound in hold boot')
        board.command('cat /proc/interrupts',timeout=15)
        board.command('dmesg',timeout=20)
        report['fresh_empty_boot_verified']=True
        expect_hash('/lib/firmware/'+firmware_name,sha(binary))
        expect_hash('/lib/firmware/'+overlay_name,sha(dtbo))
        # Refuse any host-source changes since this operator's input gate.
        if sha(args.bitstream_report.read_bytes())!=report['bitstream_report_sha256'] or sha(args.overlay_report.read_bytes())!=report['overlay_report_sha256']:
            raise RuntimeError('pinned input report changed during upload/reboot')
        validate_inputs(args.bitstream_report,args.overlay_report)
        phase('explicit_single_PL_programming_intent')
        board.command('f=/sys/class/fpga_manager/fpga0')
        report['PL_programming_attempts']=1;save()
        board.command('echo '+firmware_name+' > $f/firmware',timeout=35)
        if board.value('$f/state')!='operating':raise RuntimeError('paired native PL not operating')
        report['explicit_PL_operating_verified']=True;save()
        # Exactly one application, without firmware-name and without retries.
        board.command('mkdir $ov/p35')
        board.command('p=/lib/firmware/'+overlay_name)
        phase('single_device_overlay_apply_intent')
        report['overlay_apply_attempts']=1;save()
        board.command('cat $p > $ov/p35/dtbo',timeout=35)
        report['overlay_apply_returned']=True;save()
        board.command('sleep 2')
        identity(held);names=idle_names()
        if not RF_NAMES <= set(names):raise RuntimeError('PHY/ADC/DDS names missing')
        board.command('/etc/rcS.d/S99board --check-rf')
        board.command('test -e /dev/dri/card0');board.command('test -e /dev/fb0')
        if board.value('/sys/class/graphics/fb0/virtual_size')!='800,480':raise RuntimeError('unexpected framebuffer geometry')
        report['fb_bits_per_pixel']=board.value('/sys/class/graphics/fb0/bits_per_pixel')
        board.command('ls /sys/class/backlight')
        report['clock_summary']=summary=board.command('cat /sys/kernel/debug/clk/clk_summary',timeout=20)
        rates=clock_rates(summary);report['clock_rates']=rates
        for name,expected in [('fclk0',100000000),('fclk1',200000000),('clk_out1',33000000)]:
            if name not in rates or abs(rates[name]-expected)>1000:
                raise RuntimeError('software clock readback differs '+name)
        report['current_clocksource']=board.value('/sys/devices/system/clocksource/clocksource0/current_clocksource')
        board.command('cat /proc/interrupts',timeout=15)
        board.command('cat /proc/iomem',timeout=15)
        report['final_dmesg']=log=board.command('dmesg',timeout=20)
        if re.search(r'Internal error:|Kernel panic|Oops:|BUG:',log):raise RuntimeError('kernel failure evidence')
        identity(held);factory_files();expect_hash('/etc/rcS.d/S99board',guard_sha)
        report.update(status='passed_fresh_boot_merged_probe_and_software_clocks_only',
            observed_RF_names=sorted(RF_NAMES),observed_DRM_fb0=True,
            later_ordinary_reboot_uses_factory_RF=True,merged_design_left_running=True,
            RF_capture_verified=False,physical_display_or_LOCK_verified=False)
    except Exception as exc:
        report['failure_phase']=report['status']
        report.update(status='failed_or_state_unconfirmed',error=repr(exc),pending_boot_hold=armed)
        if board:
            # Do not send more commands into an unresponsive configuration or
            # pretend postchecks succeeded. Passive tail only, then release UART.
            try:
                report['passive_failure_tail']=board.read(12)
            except Exception as tail_error:report['passive_tail_error']=repr(tail_error)
    finally:
        if board:board.close()
        report['serial_closed']=True;report['ended_utc']=datetime.now(timezone.utc).isoformat()
        save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
