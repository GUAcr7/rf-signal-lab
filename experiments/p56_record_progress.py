"""Point handoff at an in-progress bounded candidate instead of stale idle claims."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,rel

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--trial',required=True,type=Path);args=ap.parse_args();t=read(args.trial)
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    entry=ROOT/'START-HERE.md';backup=ROOT/('START-HERE-BEFORE-P56-'+stamp+'.md');backup.write_bytes(entry.read_bytes())
    current=dict(status='bounded_P56_trial_in_progress_read_report_for_latest_state',report=rel(args.trial),
        expected_boot=t['expected_boot'],TX_expected_boot=t['TX_expected_boot'],startup_selection_paused=True,
        persistent_AI_default=False,previous_stable_profile='results/p43-enabled-20261024T081307Z/report.json',
        native_duration_ms=t['duration_ms'],entry_before_trial=rel(backup))
    write(ROOT/'results/p56-active.json',current);s=read(ROOT/'TX-SOURCE-STATUS.json')
    s.update(status=current['status'],authoritative_current_field='p56_current',p56_current=current);write(ROOT/'TX-SOURCE-STATUS.json',s)
    entry.write_text('# 从这里恢复项目工作\n\n2026-10-24：P56 运行时 AI 候选正在做有时限的实际两板试验。\n\n'
        '先读 `results/p56-active.json` 以及其中 report 指向的实时记录；不要沿用 P52 的“当前停止”状态。\n\n'
        '本次已暂停下一次开机的 P48 选择，仅在 RAM 运行候选，没有热加载 PL 或替换原 P48 二进制。结束后必须核验收发停止并用 p55_rearm_profile.py 恢复 P48 开机选择。\n\n'
        '实验方案和离线证据：`docs/experiments/EXP-P56-runtime-AI-20261024.md`。模型冻结及独立测试仍以 P52 为准。\n\n'
        'results/ 被 Git 忽略，直接读文件系统。原入口：`'+rel(backup)+'`。\n',encoding='utf-8')
    print(rel(ROOT/'results/p56-active.json'))
if __name__=='__main__':main()
