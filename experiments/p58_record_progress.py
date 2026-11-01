"""Keep live cold-trial handoff and direct human visual confirmation distinct."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p58_boot_contract import validate_boot

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);ap.add_argument('--execution',required=True,type=Path)
    ap.add_argument('--paused-selection',type=Path);args=ap.parse_args();t=read(args.trial);e=read(args.execution)
    boot=validate_boot(ROOT/t['boot_report'])
    if not boot['true_power_cycle_verified'] or sha(args.trial.parent/'executed.py')!=e['controller_sha256']:raise ValueError('cold controller provenance differs')
    if args.paused_selection:
        selection=read(args.paused_selection)
        if t['status']!='captured_runtime_AI_pending_byte_archives_and_independent_review' or selection['status']!='passed_idle_P57_next_boot_selection_pause' or selection['expected_boot']!=boot['expected_boot']:raise ValueError('stopped matching paused session required')
        a=read(ROOT/'results/p58-active.json');a.update(status='P58_cold_session_stopped_paused_pending_archives',report=rel(args.trial),report_sha256=sha(args.trial),
            serial_owned_by_trial=False,serial_closed=True,RX_and_TX_idle=True,persistent_AI_selected=False,startup_paused_for_archiving=True,selection=rel(args.paused_selection))
        write(ROOT/'results/p58-active.json',a);s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=a['status'],authoritative_current_field='p58_current',p58_current=a);write(ROOT/'TX-SOURCE-STATUS.json',s)
        (ROOT/'START-HERE.md').write_text('# 从这里恢复项目工作\n\nP58 真正断电后的自动接收/显示会话已正常停止，正在归档和独立复核。\n\n'
            '先读 results/p58-active.json 和所指 report，TX-SOURCE-STATUS.json 的 p58_current 是权威。收发已停止，串口由归档工具按需独占。'
            'P57 下一次开机选择临时暂停，归档验收后需恢复；不要在此阶段先重启或热加载。\n\n'
            '本次用户已确认小屏亮起并持续更新。最终验收与检查点尚未完成。记录：docs/experiments/EXP-P58-cold-AI-20261024.md。results/ 被 Git 忽略，读文件系统。\n',encoding='utf-8')
        print(a['status']);return
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p58-visual-%Y%m%dT%H%M%SZ');out.mkdir()
    human=out/'human-event.json';write(human,dict(source='direct user reply in current conversation',expected_boot=boot['expected_boot'],
        question='本次重新上电后，小屏是否亮起，能看到RF SIGNAL LAB、RX active及持续更新的update/source block数字或曲线',
        answer='屏幕亮着，数字或曲线持续更新',physical_screen_illuminated=True,physical_updates_observed=True,
        observed_during_native_RX=True,ten_minute_human_observation_claimed=False))
    a=dict(status='P58_user_power_cycle_and_visual_progress_confirmed_RF_trial_running',report=rel(args.trial),
        execution=rel(args.execution),execution_sha256=sha(args.execution),boot=t['boot_report'],expected_boot=boot['expected_boot'],
        TX_expected_boot=t['TX_expected_boot'],true_power_cycle_verified=True,persistent_AI_selected=True,board_shutdown=False,
        human_visual=rel(human),human_visual_sha256=sha(human),serial_owned_by_trial=True,automatic_TX_at_boot=False)
    write(ROOT/'results/p58-active.json',a);s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=a['status'],authoritative_current_field='p58_current',p58_current=a);write(ROOT/'TX-SOURCE-STATUS.json',s)
    entry=ROOT/'START-HERE.md';backup=ROOT/('START-HERE-BEFORE-P58-'+out.name.removeprefix('p58-visual-')+'.md');backup.write_bytes(entry.read_bytes())
    entry.write_text('# 从这里恢复项目工作\n\nP58：用户已对新板真正断电上电，已观察小屏亮起并持续更新。\n\n'
        '当前受控识别/十分钟观察试验正在进行。先读 results/p58-active.json 及其 report；TX-SOURCE-STATUS.json 的 p58_current 是权威。'
        '不要沿用旧 P57 的“已经关机”状态，不要重复重启或热加载。\n\n'
        '本次控制器独占 COM8/COM9，原始结果在 results/ 文件系统中。模型与已验收 native 未更改，原 P48 配置仍保留。\n\n'
        '实验：docs/experiments/EXP-P58-cold-AI-20261024.md。此前入口：`'+rel(backup)+'`。\n',encoding='utf-8')
    print(rel(human))
if __name__=='__main__':main()
