"""Verify idle, restore unchanged P48 startup, write handoff and verified checkpoint."""
import argparse,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel,checkpoint

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path)
    ap.add_argument('--regression',required=True,type=Path);args=ap.parse_args();review=read(args.review)
    regression=read(args.regression)
    if regression['status']!='passed_targeted_frozen_AI_and_P48_display_regressions':raise ValueError('targeted regression gate required')
    archive=read(ROOT/review['archive']);trial_path=ROOT/archive['trial'];trial=read(trial_path)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-final-%Y%m%dT%H%M%SZ');out.mkdir()
    cp=ROOT/'results'/datetime.now(timezone.utc).strftime('p56-checkpoint-%Y%m%dT%H%M%S%fZ')
    r=dict(status='verifying_idle_and_restoring_stable_startup',stages=[],review=rel(args.review),review_sha256=sha(args.review),
        trial=rel(trial_path),trial_sha256=sha(trial_path),regression=rel(args.regression),regression_sha256=sha(args.regression),board_shutdown=False,power_removed=False,
        candidate_persistently_installed=False,checkpoint_planned=rel(cp/'report.json'))
    def run(label,script,*opts):
        q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,opts)],capture_output=True,timeout=150)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        reports=[Path(s.strip())/'report.json' for s in q.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        item=dict(label=label,exit_code=q.returncode)
        if len(reports)==1:item.update(report=rel(reports[0]),report_sha256=sha(reports[0]))
        r['stages'].append(item);write(out/'report.json',r)
        if q.returncode or len(reports)!=1:raise ValueError(label+' failed')
        return reports[0]
    write(out/'report.json',r)
    try:
        idle=run('idle','p46_preflight.py')
        enabled=run('restore-P48','p55_rearm_profile.py','--recovery',ROOT/'results/p55-recovery-flow-20261024T075938Z/report.json')
        status=run('startup-state','p43_status.py','--enable-report',enabled)
        s=read(status)
        if s['status']!='read_only_persistent_profile_state_collected':raise ValueError('final startup status differs')
        passed=review['status']=='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay' and review.get('ten_minute_duration_verified')
        r.update(status='passed_runtime_AI_10minute_controlled_demo_checkpoint_ready' if passed else 'saved_runtime_AI_review_failed_stable_startup_restored',
            runtime_AI_accepted=bool(passed),stable_P48_startup_restored=True,all_serial_closed=True,RX_and_TX_idle=True,
            expected_boot=trial['expected_boot'],TX_expected_boot=trial['TX_expected_boot'],current_startup=rel(enabled),
            display_updates=review.get('display_updates'),session_seconds=review.get('session_seconds'),
            coverage=review.get('coverage'),conditional_accuracy=review.get('conditional_accuracy'),
            independent_accuracy_still_P52='52/54 INT8; this P56 deployment regression is not an independent test',
            remaining=['AI candidate persistent startup and fresh power-cycle calibration acceptance',
                'broader independent RF conditions and unknown/OOD handling',
                'formal self-designed PL FFT/power-spectrum requirement remains separate'],
            next_session='Freshly identify boot IDs and idle state; use a current source restore report and fresh background/pilot calibration. Do not reuse a compiled P53 IF or stale boot identity.')
    except Exception as e:
        r.update(status='failed_finalization_state_requires_review',error=repr(e));write(out/'report.json',r);print(out);print(r['status']);return 1
    write(out/'report.json',r)
    current=dict(status=r['status'],report=rel(out/'report.json'),report_sha256=sha(out/'report.json'),
        review=rel(args.review),review_sha256=sha(args.review),expected_boot=trial['expected_boot'],TX_expected_boot=trial['TX_expected_boot'],
        stable_P48_startup_restored=True,persistent_AI_default=False,serial_closed=True,RX_and_TX_idle=True,
        board_powered_not_shutdown=True,checkpoint=rel(cp/'report.json'))
    write(ROOT/'results/p56-active.json',current);source=read(ROOT/'TX-SOURCE-STATUS.json')
    source.update(status=r['status'],authoritative_current_field='p56_current',p56_current=current);write(ROOT/'TX-SOURCE-STATUS.json',source)
    handoff=ROOT/'docs/handoff/RESUME-P56-20261024.md'
    handoff.write_text('# P56 恢复清单\n\n权威入口：`results/p56-active.json`、`TX-SOURCE-STATUS.json` 的 p56_current。\n\n'
        '本轮结论：'+r['status']+'。\n\n'
        '十分钟实际收发记录：`'+rel(args.review)+'`。受控部署回归：'+str(review.get('display_updates'))+' 次显示更新，'
        +str(review.get('session_seconds'))+' 秒；覆盖率 '+str(review.get('coverage'))+'，已报类别正确率 '+str(review.get('conditional_accuracy'))+'。'
        '这些相邻更新不能当成独立 RF 试验，也不能替代 P52 独立测试的 52/54。\n\n'
        '本轮修复：校准绑定本次启动身份；四个背景 DMA 块和两个单音块自动校准；背景、纯单音、削顶、判别不一致与停止时暂缓/清除类别。'
        '波形、模型、量化和有效输入的前端处理均未改变。模型通用未知拒识未实现。\n\n'
        '停止状态：两板收发均已停、串口关闭、原 P48 开机选择恢复。板仍通电，没有关机。AI 候选只在 RAM，不是默认开机程序。\n\n'
        '下次先只读识别两板和 boot_id；检查是否有原 P48 运行进程。不能在接收占用时直接启动候选。'
        '若重启过，旧源 RAM 文件消失，需重新上传源、核验 SHA/guard 和已确认的原衰减接线。保持 TX 峰值 256、-10 dB，RX 手动 0 dB。'
        '用新的背景与单音重新校准，禁止重放旧 boot-session。\n\n'
        '后续优先：将已验收候选与受控校准控制器做成可恢复的一键入口/持久启动，并做新的真实断电后验收；'
        '再扩充未见频偏、强度、符号率及非三类信号。正式自研 PL FFT/功率谱是独立任务。\n\n'
        '实验记录：`docs/experiments/EXP-P56-runtime-AI-20261024.md`。'
        '完整恢复仍需保留前期 P52 和本次 P56 检查点。results/ 被 Git 忽略，要读文件系统。\n',encoding='utf-8')
    (ROOT/'START-HERE.md').write_text('# 从这里恢复项目工作\n\n2026-10-24 最新：'+r['status']+'。\n\n'
        '先读 [恢复清单](docs/handoff/RESUME-P56-20261024.md)、[实验记录](docs/experiments/EXP-P56-runtime-AI-20261024.md) 和 results/p56-active.json。'
        '权威字段是 TX-SOURCE-STATUS.json 的 p56_current。\n\n'
        '已停止收发、关闭串口并恢复原 P48 下一次开机选择；板仍通电，未关机。AI 候选尚未设为开机默认。'
        '断电后重新认板并重做背景/单音校准，不复用旧身份或 IF。\n\n'
        '本轮是受控三类信号部署回归，独立识别率仍为 P52 INT8 52/54；不宣称通用未知拒识、无丢样或正式 PL FFT 完成。\n\n'
        'results/ 被 Git 忽略，直接读文件系统。检查点：`'+rel(cp/'report.json')+'`。\n',encoding='utf-8')
    doc=ROOT/'docs/experiments/EXP-P56-runtime-AI-20261024.md'
    doc.write_text(doc.read_text(encoding='utf-8').replace('待追加。未完成的环节不得用离线结果替代上板验收。','实际结果见下方最终验收及其完整原始档案。'),encoding='utf-8')
    with doc.open('a',encoding='utf-8') as f:
        f.write('\n\n## 最终验收与收尾\n\n'+r['status']+'。\n\n审查：`'+rel(args.review)+'`；最终状态：`'+rel(out/'report.json')+'`。\n\n'
            '实际运行 '+str(review.get('session_seconds'))+' 秒、'+str(review.get('display_updates'))+' 次显示更新。有效区间 '
            +str(review.get('known_signal_observations'))+' 次观察，'+str(review.get('classified_observations'))+' 次报类别、'
            +str(review.get('correct_observations'))+' 次正确。背景不报类别 '+str(review.get('source_off_observations'))+' 次。'
            '像素及快照的 Python 前端/判别已复核；没有本轮人眼物理屏幕确认。\n\n'
            '电脑端保留前端、模型及 P48 显示回归：78 项通过，记录 `'+rel(args.regression)+'`。\n\n'
            '两板均已停止收发，DMA/扫描与 DDS 清零状态有独立检查，串口关闭，原 P48 开机选择恢复。没有关机或断电。'
            '未把 RAM 候选当成开机持久化交付。后续新上电还需新的校准/源恢复及 AI 开机部署验收。\n')
    reports=dict(final=out/'report.json',review=args.review,active=ROOT/'results/p56-active.json',trial=trial_path,archive=ROOT/review['archive'])
    checkpoint_path=checkpoint('p56-checkpoint',reports,cp)
    print(out);print(r['status']);print(checkpoint_path);return int(not r['runtime_AI_accepted'])
if __name__=='__main__':raise SystemExit(main())
