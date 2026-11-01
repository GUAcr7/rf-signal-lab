"""Save controlled cold-start evidence without conflating machine and human checks."""
import argparse,json
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from p43_finish_enable import reviewed
from p45_checkpoint import checkpoint,read,write,sha,rel

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('cycle','review','clock','verification','enable','status'):p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--human-display',type=Path)
    args=p.parse_args();cycle,review=reviewed(args.cycle,args.review,require_clock=False)
    clock=read(args.clock);verification=read(args.verification);enable=read(args.enable);status=read(args.status)
    if (cycle['startup_origin']!='user_confirmed_power_cycle' or cycle['power_cycles_observed']!=1 or cycle['reboots_issued']!=0
        or cycle['minimum_running_seconds_requested']<660 or cycle['native_summary']['elapsed_software_s']<660
        or clock['status']!='passed_user_power_cycle_gated_clock_driver_register_consistency'
        or clock['trial_sha256']!=sha(args.cycle) or clock['boot_id']!=cycle['expected_boot']
        or verification['status']!='passed_user_power_cycle_over_600s_no_X_console_blank_disabled_backlight_enabled'
        or verification['inputs']['cycle']['sha256']!=sha(args.cycle) or verification['inputs']['review']['sha256']!=sha(args.review)
        or verification['inputs']['cold_clock']['sha256']!=sha(args.clock)
        or enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or not enable['true_power_cycle_verified'] or not enable['persistent_autostart_enabled']
        or enable['inputs']['current_cycle']['sha256']!=sha(args.cycle)
        or status['status']!='read_only_persistent_profile_state_collected' or status['boot_id']!=cycle['expected_boot']
        or status['enable_report_sha256']!=sha(args.enable) or status['taint']!='0' or status['RX_buffer']!='0'
        or status['RX_scans']!=['0']*4 or status['native_process_observed'] or not status['persistent_wrapper_selected']
        or status['pending_present'] or status['disabled_present'] or not status['serial_closed']):raise ValueError('cold verification/idle chain differs')
    physical=False
    if args.human_display:
        human=read(args.human_display)
        physical=bool(human.get('expected_boot')==cycle['expected_boot'] and human.get('elapsed_software_s_at_question',0)>=600
            and human.get('physical_visibility_after_600s_confirmed') is True and human.get('physical_updates_after_600s_confirmed') is True)
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p45-checkpoint-%Y%m%dT%H%M%S%fZ')
    record='docs/experiments/EXP-HW-035-cold-display-verification.md';resume='docs/handoff/RESUME-P45-20261022.md'
    phase_status='controlled_cold_boot_RX_and_physical_display_over_600s_verified' if physical else 'cold_machine_boot_verified_physical_confirmation_pending'
    current=dict(status=phase_status,updated_utc=now.isoformat(),expected_boot=cycle['expected_boot'],
        installed_directory=cycle['installed_directory'],reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in vars(args).items() if isinstance(v,Path)},
        record=record,resume=resume,checkpoint=rel(out/'report.json'),RX_idle=True,serial_closed=True,board_shutdown_issued=False,
        persistent_autostart_enabled=True,cold_machine_boot_verified=True,physical_visibility_after_600s_confirmed=physical,
        physical_updates_after_600s_confirmed=physical,new_cold_boot_after_fix_verified=physical,
        PRODUCT_ID_FF_root_cause_closed=False,failure_fallback_verified_on_real_board=False,ADC_gaps='unknown',lossless_proven=False,
        TX_started_this_round=False,hardware_reboots_issued_by_host=0,physical_poweroff_interval_instrument_measured=False)
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    state.update(status=phase_status,authoritative_current_field='p45_current',record=record,updated=now.isoformat(),
        updated_note='P45: controlled user power cycle, >600s autonomous RX/display, post-stop archives and clock/blanking checks; see physical confirmation flag',
        status_note='以p45_current及其恢复清单为准。一次受控断电成功不能推导0xFF根因关闭。',p45_current=current)
    state['p44_current'].update(status='superseded_by_P45_controlled_cold_verification',new_cold_boot_after_fix_verified=physical)
    state['session_stop']=dict(active=False,superseded_by='p45_current',board_shutdown_issued=False,halt_observed=False,
        note='Previous stop/halt is historical; new cold cycle is complete and board remains powered.')
    write(state_path,state);write(ROOT/'results/p45-active.json',current)
    for name in ('p43-active.json','p44-active.json'):
        write(ROOT/'results'/name,dict(status='superseded_by_p45_current',report=rel(args.enable),status_report=rel(args.status),
            expected_boot=cycle['expected_boot'],RX_idle=True,native_completion_unconfirmed=False,wrapper_may_be_installed=True))
    s=cycle['native_summary'];humanpower=read(Path(cycle['inputs']['human_event']['path']));passive=Path(cycle['inputs']['passive_capture']['path'])
    with (ROOT/record).open('a',encoding='utf-8') as f:
        f.write(f'''\n## 受控真断电后的结果（本节覆盖前述“进行中”）

正常关机与保存记录见被动捕获报告所引用的poweroff_report。用户直接回复“{humanpower.get('answer','已断电并重新上电')}”；断电间隔由用户执行，未由仪器测量。被动启动UART记录`{rel(passive)}`，发送字节0，捕获新内核及P43首次READY，随后实际boot `{cycle['expected_boot']}`；主机没有发重启、装PL或启动接收命令。

板端自动接收并绘图，运行{s['elapsed_software_s']:.3f}秒、更新{s['display_updates']}次、RSS高水位{s['maxrss_kib']}KiB后受控停止，资源释放、RF参数不变、taint0。主试验`{rel(args.cycle)}`；原始IQ/显存完整回传、最后显示前缀独立数值核对`{rel(args.review)}`；受控冷启动同boot时钟寄存器/驱动率验收`{rel(args.clock)}`。

超过600秒后防休眠策略回读`{rel(args.verification)}`确认P44文件SHA和选用入口不变、consoleblank0、无Xorg/xinit、PWM2仍enabled；**实体屏超过600秒仍亮且持续更新的用户确认={physical}**，本字段False时不能把机器证据写成实体显示通过。

持久wrapper已重新启用：`{rel(args.enable)}`；最终只读`{rel(args.status)}`确认RX idle、buffer/scan0、没有pending/disabled，串口关闭。当前板卡仍通电，未再次关机。恢复入口为P45，保存包`{rel(out/'report.json')}`。本轮没有启动旧P201发射。

结论仅覆盖这一次受控真断电及十分钟以上自动RX/频谱显示。厂家偶发0xFF根因、实际故障回退、更多冷启动与长稳、CDC/外部IO时序、物理PCLK、无损连续性、已知源质量和真实AI未据此关闭。
''')
    (ROOT/resume).write_text(f'''# P45恢复步骤（2026-10-22）

先读[HW-035](../experiments/EXP-HW-035-cold-display-verification.md)和TX-SOURCE-STATUS.json的p45_current。本次受控真断电后的软件链通过；600秒后实体动态确认={physical}。当前boot `{cycle['expected_boot']}`只是最后实读身份，下次接电必须重新读取。

1. 当前RX停止、资源释放、串口关闭，板仍通电，未再次关机。P43自动初始化/接收和P44防休眠均已启用，下一次新boot会尝试自动运行。需要断电先正常关机并确认System halted。
2. 使用`experiments/p43_status.py --enable-report {rel(args.enable)}`只读检查实际boot、配置SHA、pending/disabled、进程和buffer/scan。单一COM8 owner，打开前DTR/RTS false；若running，不重复起流或装PL。
3. /etc/p43-20261022T030856Z是持久启动目录，/etc/p44-20261022T040536Z是显示策略目录。仅在当前boot的READY成立时跳过X桌面；consoleblank应0、PWM2 enabled。不能只凭显存截图或brightness值判断实体显示。
4. running进程用已核验control stop停止，再独立检查idle及taint。/run只保留最后显示前缀，断电丢失；保存本轮原始IQ/显存并独立复核后才换boot。原型仍非全流无损记录，ADC gaps未知。
5. 若0xFF/启动失败，保存原UART、pending/disabled和dmesg，不热卸驱动、不在绑定时重配PL，不把下一次正常重启称作根因修复。故障回退仍只做过软件用例，实板演练待做。
6. 下一步按项目验收依赖，优先完成已知源质量和指标可靠性，再接真实AI；0xFF对照、更多冷启动/长稳、时序问题单独跟踪。本次成功不能等同所有问题已根治。

检查点：`{rel(out/'report.json')}`。results不在Git，原始证据和保存包必须按文件系统保留。旧P44/P43“当前状态”都是历史。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    start.write_text(f'''# 从这里恢复项目工作

**当前入口：P45受控断电验证（2026-10-22）。** 先读[HW-035]({record})、[P45恢复步骤]({resume})和p45_current。修复后一次人工真正断电，零UART发送被动记录新启动，板端自行接收/频谱显示{s['elapsed_software_s']:.1f}秒、{s['display_updates']}次更新。原始IQ/显存、时钟和防休眠状态复核通过；600秒后实体屏仍亮且动态更新的人工确认={physical}。

当前RX idle、串口关闭、板仍通电，未再次关机；持久启动及防休眠策略已启用。一次成功不代表0xFF根因、故障回退、全流连续性或真实AI已通过。下方所有旧停工/关机/等待断电/旧boot均为历史，不重放旧命令。

---

'''+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    reports={k:v for k,v in vars(args).items() if isinstance(v,Path)}
    result=checkpoint('p45-checkpoint',reports,destination=out)
    print(result);print(phase_status)
if __name__=='__main__':main()
