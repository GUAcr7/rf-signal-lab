"""Normal receiver halt after a verified warm checkpoint, for human power cycling."""
import argparse,re,zipfile,hashlib
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_console import Console
from p35_once_merged_trial import AuditPort
from p46_preflight import parse_names
from p36_full_rx_run import RF_EXPECTED,CRITICAL_KERNEL

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--final',required=True,type=Path);ap.add_argument('--checkpoint',required=True,type=Path);args=ap.parse_args()
    final=read(args.final);cp=read(args.checkpoint);boot=read(ROOT/final['boot'])
    if final['status']!='passed_P57_persistent_AI_warm_boot_calibration_RF_LCD_cold_pending' or not final['RX_and_TX_idle']:raise ValueError('accepted idle warm state required')
    if cp['status']!='passed_P57_checkpoint_ZIP_CRC_and_all_member_SHA' or not cp['all_member_SHA_verified'] or sha(ROOT/cp['archive']['path'])!=cp['archive']['sha256']:raise ValueError('verified checkpoint ZIP required')
    if cp['reports']['final']['sha256']!=sha(args.final) or sha(ROOT/final['boot'])!=final['boot_sha256']:raise ValueError('checkpoint/boot identity differs')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-poweroff-%Y%m%dT%H%M%SZ');out.mkdir()
    r=dict(status='checking',stages=[],expected_boot=final['expected_boot'],final=rel(args.final),final_sha256=sha(args.final),checkpoint=rel(args.checkpoint),checkpoint_sha256=sha(args.checkpoint),
        halt_observed=False,poweroff_issued=False,old_board_accessed=False,physical_power_cycle_performed=False,serial_closed=False)
    def save():write(out/'report.json',r)
    def digest(path):
        b.command('v='+path);rows=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(rows)!=1:raise ValueError('ambiguous digest')
        return rows[0]
    b=None;save()
    try:
        b=Console('COM8',r,save);b.port=AuditPort(b.port,out);b.shell();b.command('p57halt_prompt=$PS1');b.command("PS1=''");b.command('stty -echo')
        if b.value('/proc/sys/kernel/random/boot_id')!=final['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('boot changed; no shutdown')
        if digest('/etc/rcS.d/S99board')!=final['wrapper_sha256']:raise ValueError('next boot selection changed')
        for name,digest_expected in boot['installed_files_sha256'].items():
            if digest(boot['installed_directory']+'/'+name)!=digest_expected:raise ValueError('installed profile changed')
        b.command('d='+boot['installed_directory']);b.command('test ! -e $d/pending');b.command('test ! -e $d/disabled')
        if b.value('/run/p42-000043/exit') not in ('0','143'):raise ValueError('owned completion missing')
        if '/run/p42-000043/monitor' in b.command('ps -ef'):raise ValueError('RX still running')
        b.command('ir=/sys/bus/iio/devices');n=parse_names(b.command('for n in $ir/iio:device*;do echo __D__$n:$(cat $n/name)__E__;done'))
        for name in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):
            if b.value(n[name]+'/buffer/enable')!='0':raise ValueError('DMA active')
        b.command('cd '+n['cf-ad9361-lpc'])
        if any(b.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX scans active')
        b.command('cd '+n['ad9361-phy'])
        if {k:b.value(k) for k in RF_EXPECTED}!=RF_EXPECTED or re.search(CRITICAL_KERNEL,b.command('dmesg | tail -n 160')):raise ValueError('RF/kernel changed')
        b.command('sync',timeout=20);b.command('stty echo');b.command('PS1=$p57halt_prompt')
        r.update(status='saved_idle_normal_shutdown_intent',poweroff_issued=True);save();b.port.write(b'poweroff\r')
        text=b.read(40,r'System halted|system halted|Power down');(out/'shutdown.txt').write_text(text,encoding='utf-8')
        if not re.search(r'System halted|system halted|Power down',text):raise ValueError('normal halt not observed')
        r.update(status='receiver_halted_checkpoint_verified_awaiting_manual_power_cycle',halt_observed=True)
    except Exception as e:r.update(status='failed_or_unconfirmed_P57_poweroff',error=repr(e))
    finally:
        if b:b.close()
        r['serial_closed']=True;save()
    if r['halt_observed']:
        active=read(ROOT/'results/p57-active.json');active.update(status=r['status'],report=rel(out/'report.json'),report_sha256=sha(out/'report.json'),
            board_shutdown=True,halt_observed=True,poweroff_record=rel(out/'report.json'),true_power_cycle_verified=False,new_boot_must_be_identified=True)
        write(ROOT/'results/p57-active.json',active);s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=r['status'],authoritative_current_field='p57_current',p57_current=active);write(ROOT/'TX-SOURCE-STATUS.json',s)
        entry=ROOT/'START-HERE.md';prior=entry.read_text(encoding='utf-8')
        entry.write_text('# 从这里恢复项目工作\n\n**最新：新板已正常关机，确认 System halted，等待用户仅对新板真正断电约10秒再上电。旧板未关机。**\n\n'
            '先读 results/p57-active.json 及其 poweroff_record；原检查点已核验，P57 AI 开机配置仍启用。下方“尚未关机”是此前历史。'
            '上电后先认新 boot 与开机日志，不先 reboot 或热加载；应先看到等待校准，不能沿用旧 IF/令牌。\n\n'+prior.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
        notes=ROOT/'docs/handoff/RESUME-P57-20261024.md'
        with notes.open('a',encoding='utf-8') as f:f.write('\n## 正常关机更新\n\n新板已正常 halt；记录 `'+rel(out/'report.json')+'`。P57 仍选中，旧板未动。'
            '先开启 `p43_capture_power_on.py --poweroff-report '+rel(out/'report.json')+' --max-seconds 600`，该工具纯监听；再请用户只对新板断电约10秒后上电。'
            '监听期间独占 COM8，不能同时另开会话。用户动作尚未完成前不得把真正断电项写成通过。\n')
        with (ROOT/'docs/experiments/EXP-P57-boot-AI-20261024.md').open('a',encoding='utf-8') as f:f.write('\n正常关机准备：`'+rel(out/'report.json')+'`；确认 System halted，等待真人电源动作。\n')
        members=[out/'report.json',out/'shutdown.txt',ROOT/'results/p57-active.json',ROOT/'TX-SOURCE-STATUS.json',entry,notes,ROOT/'docs/experiments/EXP-P57-boot-AI-20261024.md',Path(__file__)]
        packet=out/'halt-packet.zip'
        with zipfile.ZipFile(packet,'x',compression=zipfile.ZIP_DEFLATED) as z:
            for p in members:z.write(p,rel(p))
        with zipfile.ZipFile(packet) as z:
            if z.testzip() is not None or any(hashlib.sha256(z.read(rel(p))).hexdigest()!=sha(p) for p in members):raise ValueError('halt packet verification failed')
        write(out/'packet-report.json',dict(status='passed_P57_halt_packet_CRC_and_member_SHA',packet=rel(packet),sha256=sha(packet),parent_checkpoint=rel(args.checkpoint)))
    print(out);print(r['status']);return int(not r['halt_observed'])
if __name__=='__main__':raise SystemExit(main())
