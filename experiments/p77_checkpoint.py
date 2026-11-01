"""Seal the distinct real-cold-start confirmation; never rewrite P76 certificate."""
import argparse,hashlib,re,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p67_board_trial import control
from p70_cold_prepare import passive_startup_ready


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--cold',type=Path,required=True);a=ap.parse_args();t=read(a.cold)
    if (t['status']!='passed_P77_user_real_power_cycle_P76_autonomous_fresh_AI_display'
        or not all(t[k] for k in ('serial_closed','true_power_cycle_verified','physical_LCD_confirmed','RX_running','TX_stopped'))
        or t['monitor_process_count']!=1 or t['host_RX_starts']!=0 or t['reboots_issued']!=0 or t['RF_transmissions']!=0):
        raise ValueError('read-only actual cold confirmation required')
    human_path=ROOT/t['human'];human=read(human_path);passive_path=ROOT/t['passive'];passive=read(passive_path)
    if sha(human_path)!=t['human_sha256'] or sha(passive_path)!=t['passive_sha256']:raise ValueError('human/passive changed')
    raw=passive_path.parent/'uart.rx.bin';sent=passive_path.parent/'uart.tx.bin'
    transcript=raw.read_bytes().decode('ascii',errors='replace')
    if (sha(raw)!=t['passive_RX_sha256'] or sha(sent)!=t['passive_TX_sha256'] or sent.read_bytes()!=b''
        or not passive_startup_ready(transcript) or not passive['serial_closed'] or passive['UART_bytes_sent']!=0
        or not human['screen_lit_dynamic_confirmed'] or not human['new_board_powercycled_by_user']
        or human['host_reboot_substituted']):raise ValueError('cold observation evidence invalid')
    ids=re.findall(r'ORIGINAL_BACKUP_VERIFIED boot=([0-9a-f-]{36})',transcript)
    if ids!=[t['expected_boot']] or t['expected_boot']==t['old_boot']:raise ValueError('cold boot differs')
    boot_path=Path(t['selected_boot']);boot=read(boot_path)
    if sha(boot_path)!=t['selected_boot_sha256']:raise ValueError('immutable warm certificate changed')
    profile,provenance=control.load_profile()
    if profile['schema']!='rfsig.receiver_profile.p76.v1' or provenance['accepted_boot_report_sha256']!=sha(boot_path):
        raise ValueError('selected installed profile differs')
    parent_path=ROOT/'results/p76-final-20261026T125153Z/report.json';parent=read(parent_path)
    if sha(ROOT/parent['checkpoint'])!=parent['checkpoint_sha256']:raise ValueError('parent recovery ZIP changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p77-final-%Y%m%dT%H%M%SZ');out.mkdir()
    experiment=ROOT/'docs/experiments/EXP-P77-real-cold-confirmation-20261026.md'
    experiment.write_text(f'''# P77：用户真实断电后P76自主启动确认

日期：2026-10-26晚。本轮只完成P76最后的实际断电确认，不新增算法、发射或重复十一分钟实验。

用户对上一轮准备好的物理操作问题直接回答：**{human['user_answer']}**。原回答及事件归档`{rel(human_path)}`，确认只对新板断电/上电且实际小屏亮起、数字或曲线更新。

## 证据和验证

- P76先前已正常System halted并逐文件核对备份，原关机报告`{t['halt']}`。P76普通重启/十一分钟RF验收的启动证书仍保持原SHA `{sha(boot_path)}`，没有将本轮结果合写进去。
- 被动启动监听`{rel(passive_path)}`已正常结束并释放串口；完整原始UART收到字节SHA `{sha(raw)}`，发送文件为空（0字节）。原始字节同时包含新kernel、PERSISTENT_MONITOR_READY及自动登录，排除由主机发送start/reboot代替自主启动。
- 旧boot `{t['old_boot']}`；这次新boot `{t['expected_boot']}`。用户物理断电声明与新启动字节、唯一新boot标记相互对应。
- 只读板卡验证`{rel(a.cold)}`：当前P76所有安装文件及WORK/monitor SHA、init boot marker/各启动守卫唯一性通过；实际monitor可执行进程为1；RX手动0dB/Fs30.72MS/s/LO2450MHz/18MHz配置匹配，内核检查正常；旧板仍为DDS零源。
- 三次观察中同块AI/指标始终CALIBRATION_REQUIRED、ready=false、无旧token/类别/ROI数值，progress持续递增。检查末软件elapsed {t['autonomous_duration_s_observed']:.6f}秒、更新{t['display_updates_observed']}次。这个短冷启动确认与P76此前666.488秒/1153次的十一分钟测试是**不同开机会话**，未合并声称冷启动也做了十一分钟。
- 用户实际屏幕动态确认与软件/显存证据分别记录。本轮无需再向用户重复询问同一画面。

## 验收结论与最后状态

**P76比赛演示版固化、普通启动/十一分钟受控RF及本次真实断电自主启动均完成各自验收。** 保留P75早期16QAM仍有2/65次不确定及受控三类的范围，不新增独立准确率或通用未知拒识声明。

检查时新板RX仍在唯一自主会话运行，串口已释放；开机接收最多15分钟，到时显示RX STOPPED属于正常结束。旧板供电保持、零源，没有新RF发射。没有再次poweroff/reboot，也没有改电脑选择、PL、驱动或持久文件。

接下来的实际收尾是队友TJC控制屏联调（含上电背景/单音校准与发射操作衔接），再做最终整机彩排；频谱仪分路对照按需要放后。既有受控参数先用已验收值，不在此轮继续追求零不确定或增加新调制。

恢复包：`{rel(out/'checkpoint.zip')}`，增量父包P76。冷启动UART监听已封存，不再占串口。
''',encoding='utf-8')
    handoff=ROOT/'docs/handoff/RESUME-P77-20261026.md'
    handoff.write_text(f'''# 最新恢复：P76新版固化及实际断电启动验收已完成

先读[本轮实验](../experiments/EXP-P77-real-cold-confirmation-20261026.md)、`results/p77-active.json`和主流程。P76旧交接中的等待断电/监听独占状态已被本轮取代。

## 已完成

1. P75八相位候选已作为独立P76开机版本保存，旧P70/P57回退保留。
2. P76普通重启后同一自主会话666.488秒/1153次更新，三类各40/40接受正确、单音拒判、完整历史/FFT/实显存/指标清空/停止清理通过。
3. 本次用户真实断电后，新kernel及零UART发送的自主启动证据通过；新boot `{t['expected_boot']}`，唯一monitor、校准清空、持续更新和人眼动态均确认。

上述为不同开机会话的分别验收，不把P76十一分钟说成本次冷启动十一分钟；P75仍有少量不确定的事实保留，不增加独立准确率声明。

## 现在状态及再次工作

- 检查时新板唯一RX仍运行，旧板供电保持、DDS零源，无新RF发射；所有电脑串口均已释放，被动监听已结束。新板开机接收最多15分钟，之后RX STOPPED正常。
- RX新boot `{t['expected_boot']}`；旧P201 boot `{t['initial_TX']['boot_id']}`。下次编号/boot重新识别，不套用当前值。
- 电脑选择仍指向`{rel(boot_path)}`，SHA `{sha(boot_path)}`。该普通启动证书保持不可变，冷启动另存于`{rel(a.cold)}`；不要修改旧证书导致选择失效。
- 再次工作先status；若自动RX仍运行，不启动第二个。若已到时停止，按固定start创建新会话。旧板断过电先prepare-source重新上传并核当前boot源，再做新背景和单音校准。断电不能保留旧校准，开机也不会自动发射。
- 所有新增程序/记录及完整启动字节已经保存到电脑，P76开机版本保存在新板持久存储，重新上电无需重新下载该接收程序。

## 后续只做必要收尾

队友交付TJC控制屏后，用已验收参数联调三类选择/启停，并明确新接收会话背景/单音校准的操作顺序；随后做一次包含控制屏的最终整机彩排、整理简短演示说明。需要时再做TX1功分与RSA3030对照。算法深度扩展和新独立研究暂缓。

## 追溯

用户回答：`{rel(human_path)}`；只读启动监听：`{rel(passive_path)}`；冷启动验证：`{rel(a.cold)}`；原P76运行复核：`results/p76-review-20261026T124554Z/report.json`。

本次恢复包：`{rel(out/'checkpoint.zip')}`，接在P76检查点后；results被Git忽略，直接读文件系统。P76交接仍保留回退文件的位置与恢复方法。
''',encoding='utf-8')
    for prior_name in ('docs/handoff/RESUME-P76-20261026.md','docs/experiments/EXP-P76-persistent-demo-20261026.md'):
        prior=ROOT/prior_name;body=prior.read_text(encoding='utf-8')
        note='\n\n2026-10-26后续：P77已确认用户真实断电后的自主启动与实际屏幕动态，见最新P77交接和实验记录；本文件中等待断电/监听进行中的表述为P76归档时历史状态。\n'
        if note not in body:prior.write_text(body+note,encoding='utf-8')
    acceptance=dict(status='passed_P77_actual_power_cycle_confirmation_demo_receiver_finalized',
        cold=rel(a.cold),cold_sha256=sha(a.cold),human=rel(human_path),human_sha256=sha(human_path),
        passive=rel(passive_path),passive_sha256=sha(passive_path),warm_boot=rel(boot_path),warm_boot_sha256=sha(boot_path),
        true_power_cycle_verified=True,physical_LCD_confirmed=True,RX_running_at_last_check=True,RX_halted=False,
        RX_boot=t['expected_boot'],TX_boot=t['initial_TX']['boot_id'],TX_stopped=True,serial_closed=True,
        passive_listener_closed=True,persistent_selected=True,previous_warm_11min_proof_separate=True,
        cold_short_confirmation_s=t['autonomous_duration_s_observed'],cold_updates_observed=t['display_updates_observed'],
        receiver_selection_sha256=sha(ROOT/'configs/receiver-profile.json'),independent_accuracy_newly_claimed=False,
        handoff=rel(handoff),experiment=rel(experiment),checkpoint=rel(out/'checkpoint.zip'),parent=rel(parent_path),
        next_task='teammate TJC source-control integration/calibration workflow, final whole-system demo')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=rel(handoff),checkpoint=acceptance['checkpoint'],true_power_cycle_verified=True,physical_LCD_confirmed=True,
        RX_running_at_last_check=True,RX_halted=False,TX_stopped=True,serial_closed=True,passive_listener_closed=True,
        persistent_selected=True,updated_utc=datetime.now(timezone.utc).isoformat())
    write(ROOT/'results/p77-active.json',pointer)
    for name in ('p76-active.json','p70-active.json'):
        write(ROOT/'results'/name,dict(pointer,current_via='results/p77-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';d=read(source)
    d.update(status=pointer['status'],authoritative_current_field='p77_current',p77_current=pointer,
        updated=datetime.now(timezone.utc).isoformat(),updated_note='P76 persistent demo app cold boot actually confirmed by user and zero-write startup bytes; warm eleven-minute RF proof separate; RX autonomous and TX zero source, all serial released.',
        status_note='P76新版固化、普通启动十一分钟和本次真实断电启动均分别通过；用户确认屏幕动态，接收在运行，旧板零源，串口释放。')
    write(source,d)
    start=ROOT/'START-HERE.md';old=start.read_text(encoding='utf-8')
    old='\n'.join(s for s in old.splitlines() if not s.startswith('2026-10-26 **P77最新**'))+'\n'
    prefix=f'''2026-10-26 **P77最新**：用户已真实断电上电并确认屏幕亮且持续更新；零UART写入的新kernel/自主启动、新boot `{t['expected_boot']}`、唯一RX、P76文件SHA、校准清空和更新推进均通过。P76开机版本固化/普通启动十一分钟与本次短冷启动分别验收完成，P70/P57回退保留。检查时RX在自主运行、旧板零源、串口全部释放，15分钟到时停止正常。先读[P77恢复]({rel(handoff)})、[实验记录]({rel(experiment)})及`results/p77-active.json`。下方P76已关机/等待断电为历史；后续仅控制屏联调和整机彩排，不继续算法扩展。

'''
    start.write_text(old.replace('# 从这里恢复项目工作\n','# 从这里恢复项目工作\n\n'+prefix,1),encoding='utf-8')
    paths={start,source,handoff,experiment,ROOT/'docs/handoff/RESUME-P76-20261026.md',
        ROOT/'docs/experiments/EXP-P76-persistent-demo-20261026.md',ROOT/'configs/receiver-profile.json',
        ROOT/'results/p77-active.json',ROOT/'results/p76-active.json',ROOT/'results/p70-active.json',human_path,
        ROOT/'results/p59-source-active.json',out/'acceptance.json',parent_path,boot_path}
    paths.update((ROOT/'experiments').glob('p77_*.py'))
    for folder in (a.cold.parent,passive_path.parent):
        paths.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths={p.resolve() for p in paths}
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths)}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=rel(parent_path),parent_sha256=sha(parent_path),files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(paths):z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or z.testzip() is not None:raise ValueError('ZIP unique names/CRC failed')
        for n,item in manifest.items():
            data=z.read(n)
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:raise ValueError('ZIP member SHA failed')
    write(out/'report.json',dict(status='passed_P77_recovery_unique_names_CRC_all_member_SHA',checkpoint=rel(archive),
        checkpoint_sha256=sha(archive),checkpoint_bytes=archive.stat().st_size,verified_members=len(manifest),
        acceptance=rel(out/'acceptance.json'),acceptance_sha256=sha(out/'acceptance.json'),true_power_cycle_verified=True))
    print(out);print('verified members: '+str(len(manifest)))


if __name__=='__main__':main()
