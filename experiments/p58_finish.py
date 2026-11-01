"""Accept cold boot + actual RF + pixels + human visual event, then checkpoint."""
import argparse,subprocess,sys,xml.etree.ElementTree as ET
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel,checkpoint
from p58_boot_contract import validate_boot

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);args=ap.parse_args();review=read(args.review)
    if review['status']!='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay' or not review.get('ten_minute_duration_verified') or review['session_seconds']<630:raise ValueError('independent cold ten-minute review required')
    bootpath=ROOT/review['boot_report'];boot=validate_boot(bootpath)
    if not boot['true_power_cycle_verified'] or sha(bootpath)!=review['boot_report_sha256']:raise ValueError('cold startup proof changed')
    previous=read(ROOT/'results/p58-active.json');human=ROOT/previous['human_visual'];event=read(human)
    if sha(human)!=previous['human_visual_sha256'] or event['expected_boot']!=boot['expected_boot'] or not event['physical_updates_observed']:raise ValueError('matching direct visual confirmation required')
    tests=ROOT/'results/p58-cold-contract-20261024T100300Z.xml';cases=list(ET.parse(tests).getroot().iter('testcase'))
    if len(cases)!=11 or any(list(c.iter(k)) for c in cases for k in ('failure','error','skipped')):raise ValueError('cold evidence negative-control tests required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p58-final-%Y%m%dT%H%M%SZ');out.mkdir()
    cp=ROOT/'results'/datetime.now(timezone.utc).strftime('p58-checkpoint-%Y%m%dT%H%M%S%fZ')
    r=dict(status='final_idle_checks',stages=[],boot=rel(bootpath),boot_sha256=sha(bootpath),review=rel(args.review),review_sha256=sha(args.review),
        human_visual=rel(human),human_visual_sha256=sha(human),checkpoint_planned=rel(cp/'report.json'),expected_boot=boot['expected_boot'],TX_expected_boot=boot['TX_expected_boot'],
        true_power_cycle_verified=True,host_reboots_issued_this_cold_cycle=0,physical_screen_lit_and_updating_confirmed=True,
        cold_contract_tests=dict(path=rel(tests),sha256=sha(tests),passed=11,source_sha256=sha(ROOT/'tests/test_p58_cold_contract.py'),contract_sha256=sha(ROOT/'experiments/p58_boot_contract.py')),
        human_watched_full_ten_minutes_claimed=False,model_changed=False,native_binary_changed=False,independent_model_accuracy='P52 INT8 52/54; current seed2315 results are deployment regression')
    def run(label,script,*opts):
        q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,opts)],cwd=ROOT,capture_output=True,timeout=150)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        reports=[Path(s.strip())/'report.json' for s in q.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        row=dict(label=label,exit_code=q.returncode)
        if len(reports)==1:row.update(report=rel(reports[0]),report_sha256=sha(reports[0]))
        r['stages'].append(row);write(out/'report.json',r)
        if q.returncode or len(reports)!=1:raise ValueError(label+' failed')
        return reports[0]
    write(out/'report.json',r)
    try:
        idle=run('idle','p46_preflight.py');p=read(idle)
        if p['boards']['COM8']['boot_id']!=boot['expected_boot'] or p['boards']['COM9']['boot_id']!=boot['TX_expected_boot']:raise ValueError('current boot differs')
        selection=run('arm-P57','p57_profile_control.py','--boot',bootpath,'--action','arm','--review',args.review)
        r.update(status='passed_P58_user_power_cycle_autonomous_AI_RF_LCD_10min_checkpoint_ready',selection=rel(selection),selection_sha256=sha(selection),
            installed_directory=boot['installed_directory'],wrapper_sha256=boot['installed_files_sha256']['boot'],persistent_AI_selected=True,
            RX_and_TX_idle=True,serial_closed=True,board_shutdown=False,session_seconds=review['session_seconds'],display_updates=review['display_updates'],
            known_signal_observations=review['known_signal_observations'],classified_observations=review['classified_observations'],correct_observations=review['correct_observations'],
            coverage=review['coverage'],conditional_accuracy=review['conditional_accuracy'],source_off_observations=review['source_off_observations'],
            scope='cold autonomous RX/display at least630s including waiting/calibration/background; three controlled known modulation segments, not630s of uninterrupted classification')
    except Exception as e:r.update(status='failed_P58_finalization',error=repr(e));write(out/'report.json',r);print(out);print(r['status']);return 1
    write(out/'report.json',r)
    active=dict(status=r['status'],report=rel(out/'report.json'),report_sha256=sha(out/'report.json'),boot=rel(bootpath),expected_boot=boot['expected_boot'],
        TX_expected_boot=boot['TX_expected_boot'],selection=rel(selection),persistent_AI_selected=True,true_power_cycle_verified=True,
        RX_and_TX_idle=True,serial_closed=True,board_shutdown=False,physical_screen_updates_confirmed=True,human_visual=rel(human),human_visual_sha256=sha(human),
        checkpoint=rel(cp/'report.json'))
    write(ROOT/'results/p58-active.json',active);state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(status=r['status'],authoritative_current_field='p58_current',p58_current=active);write(ROOT/'TX-SOURCE-STATUS.json',state)
    notes=ROOT/'docs/handoff/RESUME-P58-20261024.md'
    notes.write_text('# P58 恢复清单\n\n权威入口：results/p58-active.json、TX-SOURCE-STATUS.json 的 p58_current。\n\n'
        '本轮完成真正断电后自动接收/显示启动、新校准、三类真实 RF 切换、超过630秒接收会话、原始 IQ/像素复核。'
        '用户明确确认本次小屏亮起并持续更新。人眼只证明当时可见更新，不声称用户持续盯看十分钟。\n\n'
        '冷启动证据：`'+rel(bootpath)+'`；独立复核：`'+rel(args.review)+'`。模型与native二进制沿用 P56，独立识别率仍为 P52 INT8 52/54。'
        '本轮使用已暴露seed2315，属于部署回归。630秒包含等待校准及源关闭观察，不是630秒连续分类或无丢样证明。\n\n'
        '当前：收发停止、DMA/扫描空闲、旧板DDS零源有独立检查，串口关闭。两板仍通电，没有关机。P57 下一次启动仍启用：`'+boot['installed_directory']+'`。'
        '原P48 `'+boot['previous_directory']+'` 及 previous-boot 备份保留。\n\n'
        '开机默认最多15分钟接收（900000ms，外层930s），不会自动发射；先显示 CALIBRATION_REQUIRED。本次boot/模型/新令牌通过后采四块背景，等待独立单音公共IF，再做三帧一致性判别。'
        '背景、单音、削顶、三帧不一致和停止时不显示确定类别。它不等于通用未知信号检测。\n\n'
        '下次：先只读认板、boot_id、当前进程和接收状态，不先重启或热重载。若开机程序正在运行，沿用已有接收上下文，禁止再开第二个 RX。'
        '如果当前会话已经停止，需要先建立新受控会话，不能把旧 exit/AI.json 当成当前接收。每次上电都需新的背景/单音校准和新令牌。'
        '若旧板也断过电，源文件在RAM中已消失，先重新识别并上传冻结源，核对guard和波形SHA，不复用旧boot-session。\n\n'
        '保持原衰减接线、TX峰值256/-10dB、RX手动0dB；禁止热卸载 ADC 或重载 PL。安全硬件仍为TTL33 M16.5/D2/O25。\n\n'
        '后续优先：整理无需临时生成脚本的一键演示/恢复入口；扩展未见频偏、强度、符号率、非三类/多信号独立验收；正式自研PL FFT/功率谱按赛题独立验收。'
        '不是因本次冷启动通过就宣称历史所有上电故障的物理根因已消失。\n\n'
        '实验：docs/experiments/EXP-P58-cold-AI-20261024.md。results/ 被Git忽略，直接读文件系统；完整恢复需保留前期和本次检查点。\n',encoding='utf-8')
    (ROOT/'START-HERE.md').write_text('# 从这里恢复项目工作\n\n2026-10-24 最新：'+r['status']+'。\n\n'
        '先读 [恢复清单](docs/handoff/RESUME-P58-20261024.md)、[实验记录](docs/experiments/EXP-P58-cold-AI-20261024.md)、results/p58-active.json。'
        '权威字段：TX-SOURCE-STATUS.json 的 p58_current。旧P57“等待断电/已经关机”是历史。\n\n'
        '已通过用户真正断电后的AI自动接收/显示启动、新校准、三类RF与十分钟会话检查，且有本次人眼更新确认。'
        '当前收发已停、串口关闭，两板仍通电未关机；P57下次启动仍选中。\n\n'
        '开机最多15分钟接收，先等待本次校准，不自动发射；模型通用未知拒识、无丢样、绝对功率及正式PL FFT不在本项结论内。'
        '独立识别率仍为P52 INT8 52/54。results/被Git忽略，要读文件系统。\n\n检查点：`'+rel(cp/'report.json')+'`。\n',encoding='utf-8')
    doc=ROOT/'docs/experiments/EXP-P58-cold-AI-20261024.md'
    doc.write_text(doc.read_text(encoding='utf-8').replace('待整段原始数据归档、独立重算、像素检查和收尾后追加。',
        '本轮复核：`'+rel(args.review)+'`；最终状态：`'+rel(out/'report.json')+'`。\n\n'
        '本次会话 '+str(review['session_seconds'])+' 秒、'+str(review['display_updates'])+' 次显示更新。计分区间 '
        +str(review['known_signal_observations'])+' 次观察，'+str(review['classified_observations'])+' 次报类别、'+str(review['correct_observations'])+' 次正确，'
        '覆盖率 '+str(review['coverage'])+'；稳定背景 '+str(review['source_off_observations'])+' 次均未报类别。原始IQ冻结Python重算及像素一致。\n\n'
        '正常受控停止、独立复核收发空闲后重新启用P57下一次开机选择。两板仍通电，串口关闭。人眼确认另存 `'+rel(human)+'`。\n'),encoding='utf-8')
    checkpoint('p58-checkpoint',dict(final=out/'report.json',boot=bootpath,review=args.review,active=ROOT/'results/p58-active.json',human_visual=human),cp)
    print(out);print(r['status']);print(cp/'report.json');return 0
if __name__=='__main__':raise SystemExit(main())
