"""Accept exact warm-boot AI evidence, arm that profile, checkpoint before cold test."""
import argparse,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel,checkpoint

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);args=ap.parse_args();review=read(args.review)
    if review['status']!='passed_controlled_runtime_AI_full_history_pixels_and_Python_replay' or not review.get('board_started_RX'):raise ValueError('independent board-started RX review required')
    bootpath=ROOT/review['boot_report'];boot=read(bootpath)
    if sha(bootpath)!=review['boot_report_sha256']:raise ValueError('boot proof changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-final-%Y%m%dT%H%M%SZ');out.mkdir()
    cp=ROOT/'results'/datetime.now(timezone.utc).strftime('p57-checkpoint-%Y%m%dT%H%M%S%fZ')
    r=dict(status='verifying_idle_and_arming',stages=[],boot=rel(bootpath),boot_sha256=sha(bootpath),review=rel(args.review),review_sha256=sha(args.review),
        expected_boot=boot['expected_boot'],TX_expected_boot=boot['TX_expected_boot'],true_power_cycle_verified=False,
        independent_RF_accuracy_unchanged='P52 INT8 52/54; P57 is controlled deployment regression',checkpoint_planned=rel(cp/'report.json'))
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
        idle=run('idle','p46_preflight.py')
        if read(idle)['boards']['COM8']['boot_id']!=boot['expected_boot']:raise ValueError('final boot mismatch')
        selected=run('arm-P57','p57_profile_control.py','--boot',bootpath,'--action','arm','--review',args.review)
        r.update(status='passed_P57_persistent_AI_warm_boot_calibration_RF_LCD_cold_pending',selection=rel(selected),selection_sha256=sha(selected),
            installed_directory=boot['installed_directory'],wrapper_sha256=boot['installed_files_sha256']['boot'],RX_and_TX_idle=True,
            serial_closed=True,persistent_AI_selected=True,board_shutdown=False,physical_LCD_confirmed=False,
            display_updates=review['display_updates'],session_seconds=review['session_seconds'],
            classified_observations=review['classified_observations'],correct_observations=review['correct_observations'],
            coverage=review['coverage'],conditional_accuracy=review['conditional_accuracy'],source_off_observations=review['source_off_observations'])
    except Exception as e:r.update(status='failed_P57_finalization',error=repr(e));write(out/'report.json',r);print(out);print(r['status']);return 1
    write(out/'report.json',r)
    active=dict(status=r['status'],report=rel(out/'report.json'),report_sha256=sha(out/'report.json'),boot=rel(bootpath),expected_boot=boot['expected_boot'],
        TX_expected_boot=boot['TX_expected_boot'],selection=rel(selected),persistent_AI_selected=True,RX_and_TX_idle=True,serial_closed=True,
        board_shutdown=False,true_power_cycle_verified=False,checkpoint=rel(cp/'report.json'))
    write(ROOT/'results/p57-active.json',active);s=read(ROOT/'TX-SOURCE-STATUS.json');s.update(status=r['status'],authoritative_current_field='p57_current',p57_current=active);write(ROOT/'TX-SOURCE-STATUS.json',s)
    notes=ROOT/'docs/handoff/RESUME-P57-20261024.md'
    notes.write_text('# P57 恢复与真正断电验证\n\n当前权威：results/p57-active.json，TX-SOURCE-STATUS.json 的 p57_current。\n\n'
        '已完成：独立 AI 开机配置，两次普通重启均由板卡初始化程序自行开启 RX/屏幕；本轮新启动重新采背景/单音，再完成三类真实 RF 和屏幕复核。'
        '没有替换冻结的 P56 native 二进制或模型。初始没有校准时不报类别。\n\n'
        '新配置：`'+boot['installed_directory']+'`，原 P48 仍在 `'+boot['previous_directory']+'`，新目录 previous-boot 保存原选择。'
        '普通开机默认最多 15 分钟（900000 ms），UI 500 ms 间隔、外层 930 秒，4096 条日志上限；停止后需要新会话。不会自动发射。\n\n'
        '校准/停止控制：新配置目录 control 脚本；工作区仍为 /run/p42-000043。calibrate 只接收 32 位十六进制令牌，绑定实际当前 boot 与模型，不能输入调制真值。'
        '控制器必须先确认旧发射源关闭，再采背景与发单音。\n\n'
        '复核：`'+rel(args.review)+'`。首轮因断信号观察段太短，未通过原背景样本门槛；只增加末尾 6 秒观察后另开新启动复测，未改变模型或门槛。'
        '失败记录 results/p57-review-20261024T094313Z/report.json 保留。\n\n'
        '当前已停止收发、关闭串口并重新选择 P57，下次启动会自动接收并等待新校准。最后 boot '+boot['expected_boot']+'。'
        '这里的普通重启验收不证明真正断电后正常，也没有本轮物理屏幕目视确认。若随后执行关机准备，以其更新状态为准。\n\n'
        '下一步：正常 poweroff 并保存 halt 记录，先开启 p43_capture_power_on.py 的纯监听，再请用户只对新板断电约10秒后上电。'
        '用户回复是物理动作证据，不能把普通 reboot 当成断电。新启动先从 passive console/boot_id/启动日志认板，禁止先 reboot 或热加载。'
        '原 p43_accept_power_on.py 旧验收假定 P48，不能直接套给 P57；需结合新 P57 固定二进制/900000 ms/65536 prefix 的实际合同。\n\n'
        '真正断电后继续：确认当前控制请求不存在、AI 为 CALIBRATION_REQUIRED、接收与曲线在更新；用新的源身份复核和单音校准，'
        '验证三类及至少 6 秒稳定断信号，再检查10分钟显示需求。新的 controller/reviewer 必须据新 boot 生成。'
        '如旧板也断过电，需先重新上传已冻结源，禁止重放旧 boot-session。\n\n'
        '稳定硬件仍为安全 TTL33 M16.5/D2/O25；绝不热卸载 ADC 或重载 PL。通用未知识别、跨条件独立测试及正式 PL FFT 是后续独立事项。\n',encoding='utf-8')
    (ROOT/'START-HERE.md').write_text('# 从这里恢复项目工作\n\n2026-10-24：'+r['status']+'。\n\n'
        '先读 [恢复清单](docs/handoff/RESUME-P57-20261024.md)、[实验记录](docs/experiments/EXP-P57-boot-AI-20261024.md)、results/p57-active.json。'
        '权威字段：TX-SOURCE-STATUS.json 的 p57_current。\n\n'
        'AI 已加入独立的开机配置；两次普通重启通过，第二次本次校准/三类RF/像素复核通过。真正断电项仍待用户动作及新启动证据。'
        '收发已停止、串口关闭、P57 下次开机选择启用；此时尚未关机，若后续有 halt 记录应以新状态为准。\n\n'
        '15 分钟默认有时限接收，不自动发射。开机先等待本次校准；不复用旧 boot 身份或 IF。results/ 被 Git 忽略，直接读文件系统。\n\n'
        '检查点：`'+rel(cp/'report.json')+'`。\n',encoding='utf-8')
    with (ROOT/'docs/experiments/EXP-P57-boot-AI-20261024.md').open('a',encoding='utf-8') as f:
        f.write('\n\n## 第二轮结果与收尾\n\n复核：`'+rel(args.review)+'`。boot：`'+rel(bootpath)+'`。\n\n'
            '完整会话 '+str(review['session_seconds'])+' 秒、'+str(review['display_updates'])+' 次显示更新；包括开机等待校准时间。'
            '固定有效区间 '+str(review['known_signal_observations'])+' 次观察，'+str(review['classified_observations'])+' 次报类别、'
            +str(review['correct_observations'])+' 次正确，覆盖率 '+str(review['coverage'])+'。稳定背景观察 '+str(review['source_off_observations'])+' 次均不报类别。'
            '原始 IQ 的冻结 Python 重算与帧缓冲像素一致。不是新的独立模型准确率验收。\n\n'
            '已正常停止并独立验证 RX/TX 空闲，P57 下一次开机配置启用，原 P48 文件保留。软件重启验证完成，真正断电与本轮物理 LCD 目视仍待确认。\n')
    checkpoint('p57-checkpoint',dict(final=out/'report.json',review=args.review,boot=bootpath,active=ROOT/'results/p57-active.json'),cp)
    print(out);print(r['status']);print(cp/'report.json');return 0
if __name__=='__main__':raise SystemExit(main())
