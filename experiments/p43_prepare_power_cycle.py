"""Verify saved P43 checkpoint and idle identity, then halt ONLY the receiver.

No physical power cycle is claimed. The old P201 board is never accessed.
"""
import argparse
from datetime import datetime,timezone
import hashlib,json,re,zipfile
from pathlib import Path
from p32_session import ROOT
from p35_once_merged_trial import TrialConsole,RF_NAMES

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def checkpoint_phase(enable_path,checkpoint):
    """Accept explicit saved enable identities; no serial or power operation."""
    status=checkpoint['status']
    if status=='passed_P43_checkpoint_ZIP_CRC_and_all_member_SHA':
        if rel(enable_path)!=checkpoint['enable_report']:raise ValueError('checkpoint has different enabled profile')
        return 'p43'
    phases={'passed_P45_checkpoint_ZIP_CRC_and_all_member_SHA':'p45',
            'passed_P49_checkpoint_ZIP_CRC_and_all_member_SHA':'p50',
            'passed_P50_checkpoint_ZIP_CRC_and_all_member_SHA':'p50'}
    if status not in phases:raise ValueError('accepted checkpoint required')
    reference=checkpoint['reports']['enable']
    if reference['path']!=rel(enable_path) or reference['sha256']!=sha(enable_path):
        raise ValueError('checkpoint has different enabled profile')
    if phases[status]=='p50':
        enabled=read(enable_path)
        if enabled.get('display_revision')!='p48' or not enabled.get('persistent_autostart_enabled') or not enabled.get('serial_closed'):
            raise ValueError('saved P48 enabled profile required')
    return phases[status]

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-report',type=Path,required=True);p.add_argument('--checkpoint-report',type=Path,required=True)
    args=p.parse_args();enable=read(args.enable_report);checkpoint=read(args.checkpoint_report)
    if enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots':raise ValueError('accepted enable required')
    phase=checkpoint_phase(args.enable_report,checkpoint)
    archive=ROOT/checkpoint['archive']['path']
    if sha(archive)!=checkpoint['archive']['sha256']:raise ValueError('checkpoint ZIP changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime(phase+'-power-cycle-prepare-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],expected_boot=enable['expected_boot'],enable_report=rel(args.enable_report),
        checkpoint_report=rel(args.checkpoint_report),checkpoint_report_sha256=sha(args.checkpoint_report),
        checkpoint_ZIP_sha256=sha(archive),old_board_accessed=False,poweroff_issued=False,halt_observed=False,
        physical_power_cycle_performed=False,persistent_autostart_enabled=True)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():write(out/'report.json',r)
    board=None;save()
    try:
        board=TrialConsole('COM8',r,save,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=enable['expected_boot'] or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity changed; no shutdown')
        if phase in ('p45','p50'):
            policy=read(ROOT/'TX-SOURCE-STATUS.json')['p44_current']
            for name,wanted in policy['display_policy_sha256'].items():
                board.command('f='+policy['display_policy_directory']+'/'+name)
                if not re.search(r'^'+wanted+r'\s',board.command('sha256sum $f'),re.M):raise ValueError('display policy differs')
            board.command('f=/etc/init.d/xserver-nodm')
            if not re.search(r'^'+policy['display_policy_sha256']['boot']+r'\s',board.command('sha256sum $f'),re.M):raise ValueError('display policy not selected')
        if re.search(r'/run/p42-\d+/monitor|arm-latest|arm[-_]rx|arm[-_]panel|arm-tx-source|iio_readdev',board.command('ps -ef')):raise ValueError('application active; no shutdown')
        board.command('f=/etc/rcS.d/S99board')
        if not re.search(r'^'+enable['wrapper_sha256']+r'\s',board.command('sha256sum $f'),re.M):raise ValueError('startup selection changed')
        if phase=='p50':
            for name,wanted in enable['installed_files_sha256'].items():
                board.command('f='+enable['installed_directory']+'/'+name)
                if not re.search(r'^'+wanted+r'\s',board.command('sha256sum $f'),re.M):raise ValueError('installed startup profile changed')
        board.command('ir=/sys/bus/iio/devices');t=board.command('for n in $ir/iio:device*;do echo $n;cat $n/name;done')
        pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',t)
        if any(sum(n==wanted for _,n in pairs)!=1 for wanted in RF_NAMES):raise ValueError('RF names differ')
        for path,name in pairs:
            if name not in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):continue
            board.command('cd '+path)
            if board.value('buffer/enable')!='0':raise ValueError('DMA active')
            if name=='cf-ad9361-lpc' and any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX scans active')
        board.command('sync',timeout=20);r['status']='verified_idle_saved_checkpoint_shutdown_intent';save()
        board.port.write(b'poweroff\r');r['poweroff_issued']=True;save()
        text=board.read(40,r'(?:System halted|system halted|Power down)');(out/'shutdown.txt').write_text(text,encoding='utf-8')
        r['halt_observed']=bool(re.search(r'System halted|system halted|Power down',text))
        if not r['halt_observed']:raise ValueError('normal halt not observed')
        r['status']='receiver_halted_checkpoint_verified_awaiting_manual_power_cycle'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r.update(serial_closed=True,ended_utc=datetime.now(timezone.utc).isoformat());save()
    if r['halt_observed']:
        state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
        field=phase+'_current'
        if phase=='p50':
            state[field]=dict(state.get('p50_current',state['p49_current']),expected_boot=enable['expected_boot'],
                current_enable=rel(args.enable_report),record='docs/experiments/EXP-P50-cold-units.md',resume='docs/handoff/RESUME-P50-20261023.md')
        state.setdefault(field,dict(expected_boot=enable['expected_boot'],enable_report=rel(args.enable_report),
            record='docs/experiments/EXP-HW-035-cold-display-verification.md',new_cold_boot_after_fix_verified=False))
        state[field].update(status=r['status'],RX_idle=True,board_shutdown_issued=True,halt_observed=True,
            power_cycle_prepare_record=rel(out/'report.json'),next_boot_must_be_reidentified=True)
        state.update(status=r['status'],authoritative_current_field=field,updated=r['ended_utc']);write(state_path,state)
        if phase=='p50':write(ROOT/'results/p50-active.json',state[field])
        start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
        start.write_text('# 从这里恢复项目工作\n\n**最新状态：新板已正常关机，等待人工真正断电再上电做'+phase.upper()+'冷启动验证。** 记录`'+rel(out/'report.json')+'`已确认System halted；旧P201板未操作。P43持久wrapper及P44显示策略仍启用，最后boot只是停机前历史。接电后先按当前恢复说明只读认板/新boot/首次进度；不先重启、不热重装。下方“板仍通电/未关机”是此前历史状态。\n\n'+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
        notes=ROOT/({'p45':'docs/handoff/RESUME-P45-20261022.md','p50':'docs/handoff/RESUME-P50-20261023.md'}.get(phase,'docs/handoff/RESUME-P43-20261022.md'))
        with notes.open('a',encoding='utf-8') as f:f.write('\n## 冷启动准备更新\n\n已保存并核验P43主检查点，随后新板正常halt，等待人工断电约10秒再接电。记录`'+rel(out/'report.json')+'`；旧板未动，持久wrapper未禁用。本文前述未关机为历史；下一次须采集新boot与p43启动日志/进度，不重放旧boot。\n')
        packet=out/'power-cycle-packet.zip'
        members=[out/'report.json',out/'executed.py',out/'shutdown.txt',state_path,start,notes,ROOT/'experiments/p43_prepare_power_cycle.py']
        if phase=='p50':
            members += [ROOT/'experiments/p43_accept_power_on.py',ROOT/'experiments/p43_finish_enable.py',
                ROOT/'tests/test_p50_checkpoint_gate.py',ROOT/'results/p50-host-gates-20261023.xml',
                ROOT/'docs/experiments/EXP-P50-cold-units.md']
        with zipfile.ZipFile(packet,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for member in members:z.write(member,rel(member))
        with zipfile.ZipFile(packet) as z:
            if z.testzip() is not None or any(hashlib.sha256(z.read(rel(m))).hexdigest()!=sha(m) for m in members):raise ValueError('stop packet verification failed')
        write(out/'packet-report.json',dict(status='passed_halt_packet_ZIP_CRC_and_member_SHA',packet=rel(packet),sha256=sha(packet),parent_checkpoint=rel(args.checkpoint_report)))
    print(out);print(r['status']);return 0 if r['halt_observed'] else 1
if __name__=='__main__':raise SystemExit(main())
