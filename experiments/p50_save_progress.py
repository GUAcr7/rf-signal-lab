"""Save P48 controlled cold-start verification; preserve separate machine/human claims."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from p45_checkpoint import ROOT,checkpoint,read,write,sha,rel
from p43_finish_enable import reviewed,checked_units


def machine_chain(cycle,clock,policy,enable,status,watch,cycle_sha,review_sha,clock_sha,units_sha,enable_sha):
    if (cycle.get('display_revision')!='p48' or cycle.get('startup_origin')!='user_confirmed_power_cycle'
        or cycle['power_cycles_observed']!=1 or cycle['reboots_issued']!=0
        or cycle['minimum_running_seconds_requested']<660 or cycle['native_summary']['elapsed_software_s']<660
        or clock['status']!='passed_user_power_cycle_gated_clock_driver_register_consistency'
        or clock['trial_sha256']!=cycle_sha or clock['boot_id']!=cycle['expected_boot']
        or policy['status']!='passed_user_power_cycle_over_600s_no_X_console_blank_disabled_backlight_enabled'
        or policy['inputs']['cycle']['sha256']!=cycle_sha or policy['inputs']['review']['sha256']!=review_sha
        or policy['inputs']['cold_clock']['sha256']!=clock_sha
        or enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or not enable['true_power_cycle_verified'] or not enable['persistent_autostart_enabled'] or enable.get('display_revision')!='p48'
        or enable['inputs']['current_cycle']['sha256']!=cycle_sha or enable['inputs']['current_units']['sha256']!=units_sha
        or status['status']!='read_only_persistent_profile_state_collected' or status['boot_id']!=cycle['expected_boot']
        or status['enable_report_sha256']!=enable_sha or status['taint']!='0' or status['RX_buffer']!='0'
        or status['RX_scans']!=['0']*4 or status['native_process_observed'] or not status['persistent_wrapper_selected']
        or status['pending_present'] or status['disabled_present'] or not status['serial_closed']
        or watch['status']!='passed_cold_P48_progress_over_660s_RX_left_running'
        or watch['expected_boot']!=cycle['expected_boot'] or watch['elapsed_software_s']<660):
        raise ValueError('complete matching P48 cold/clock/units/policy/idle chain required')
    return True


def physical_claim(human,boot):
    return bool(human.get('expected_boot')==boot and human.get('elapsed_software_s_at_question',0)>=660
        and human.get('physical_visibility_after_600s_confirmed') is True
        and human.get('physical_updates_after_600s_confirmed') is True)


def passed_host_tests(path,minimum=71):
    cases=list(ET.parse(path).getroot().iter('testcase'))
    if len(cases)<minimum or any(list(c.iter(k)) for c in cases for k in ('failure','error','skipped')):
        raise ValueError('P50 host tests incomplete')
    return len(cases)


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('cycle','review','clock','units','verification','enable','status','watch','tests'):
        p.add_argument('--'+key,type=Path,required=True)
    p.add_argument('--human-display',type=Path)
    args=p.parse_args();cycle,review=reviewed(args.cycle,args.review,require_clock=False)
    units=checked_units(args.cycle,args.review,args.units)
    clock=read(args.clock);verification=read(args.verification);enable=read(args.enable);status=read(args.status);watch=read(args.watch)
    machine_chain(cycle,clock,verification,enable,status,watch,sha(args.cycle),sha(args.review),sha(args.clock),sha(args.units),sha(args.enable))
    for name in ('trial','readback'):
        if sha(Path(clock[name]))!=clock[name+'_sha256']:raise ValueError('clock child changed')
    for report in (watch,verification):
        for item in report['inputs'].values():
            source=Path(item['path']);source=source if source.is_absolute() else ROOT/source
            if sha(source)!=item['sha256']:raise ValueError('input archive changed')
    test_count=passed_host_tests(args.tests)
    physical=physical_claim(read(args.human_display),cycle['expected_boot']) if args.human_display else False
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p50-checkpoint-%Y%m%dT%H%M%S%fZ')
    reports={k:v.resolve() for k,v in vars(args).items() if isinstance(v,Path)}
    label='P50_P48_controlled_cold_RX_units_and_physical_display_over_660s_verified' if physical else 'P50_P48_cold_machine_verified_physical_confirmation_pending'
    current=dict(status=label,updated_utc=now.isoformat(),expected_boot=cycle['expected_boot'],
        installed_directory=cycle['installed_directory'],reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in reports.items()},
        record='docs/experiments/EXP-P50-cold-units.md',resume='docs/handoff/RESUME-P50-20261023.md',checkpoint=rel(out/'report.json'),
        current_enable=rel(args.enable),current_status=rel(args.status),default_startup_display_revision='p48',current_last_display_revision='p48',
        RX_idle=True,serial_closed=True,board_shutdown_issued=False,persistent_autostart_enabled=True,
        warm_boot_P48_verified=True,cold_boot_P48_verified=True,controlled_power_cycles_this_round=1,
        physical_visibility_after_600s_confirmed=physical,physical_updates_after_600s_confirmed=physical,
        elapsed_software_s=cycle['native_summary']['elapsed_software_s'],display_updates=cycle['native_summary']['display_updates'],
        display_units=units['displayed'],native_binary_sha256=cycle['binary_sha256'],host_tests_passed=test_count,
        host_reboots_issued=0,TX_operations=False,RF_attribute_writes=False,hot_PL_changes=False,
        PRODUCT_ID_FF_root_cause_closed=False,historical_EVM_variation_root_cause_closed=False,
        ADC_gaps='unknown',lossless_proven=False,AI_inference=False,absolute_RF_frequency_calibrated=False,
        physical_poweroff_interval_instrument_measured=False,physical_PCLK_measured=False)
    state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(status=label,authoritative_current_field='p50_current',
        updated=now.isoformat(),record=current['record'],p50_current=current,
        updated_note='P50: captured user power cycle, P48 >660s autonomous RX, independent IQ/framebuffer/clock/units and no-blanking verification; machine and physical flags separate.',
        status_note='P48新版已验证真正断电后自主启动；当前接收安全停止、自启动重新启用。单次成功不代表历史故障根因关闭。')
    state['session_stop']=dict(active=False,board_shutdown_issued=False,halt_observed=False,superseded_by='p50_current')
    write(ROOT/'TX-SOURCE-STATUS.json',state);write(ROOT/'results/p50-active.json',current)
    human=read(Path(cycle['inputs']['human_event']['path']));s=cycle['native_summary']
    record=ROOT/current['record'];text=record.read_text('utf-8').split('\n## 完成结果\n')[0]
    text=text.replace('进行中；未完成前不把P49的软件重启结果写成真断电结果。','本轮已完成，结果见下文；P49软件重启与本轮真断电证据分别保留。')
    record.write_text(text+f'''\n## 完成结果\n\n正常关机记录见被动启动报告所引用的poweroff_report。用户回复“{human['answer']}”，断电约10秒由用户执行，未用仪器测量。被动捕获发送UART字节0，含新内核和首次READY；新boot `{cycle['expected_boot']}`，没有主机重启或启动后装PL/启动应用。\n\nP48原始ELF哈希`{cycle['binary_sha256']}`匹配既有完整profile `{cycle['installed_directory']}`。连续观察到{s['elapsed_software_s']:.3f}秒、{s['display_updates']}次显示更新；前后防休眠配置一致：consoleblank0、无X桌面抢屏、PWM背光启用。实体屏幕超过660秒仍亮且动态更新的人工确认：{physical}。\n\n安全停止后，原始8192个复数样本前缀及1536000字节显存回传、SHA校验、独立NumPy、kHz/MS/s单位逐像素核对通过；时钟驱动与寄存器一致性及P44防休眠复核通过。仅归档最后显示前缀，不是全流录像。显示峰值来自未知输入/噪声，本轮未访问旧板或发射，不是已知目标识别或AI结果。\n\n同一完整profile已重新启用。终态taint0、RX buffer/scan0、无接收进程、串口关闭、无pending/disabled；板仍通电，未再次关机。下次默认仍P48自启动。原P42目录未覆盖。主机针对性检查{test_count}项通过；P49此前时序断言首次失败及复测通过记录均保留，本轮没有据此宣称问题根治。\n\n## 仍开放的问题\n\n这是新版的一次受控冷启动成功，不足以关闭历史0xFF偶发启动故障或EVM波动根因。更长期/多次冷启动稳定性、ADC无损连续性、绝对功率/频率校准、独立真实数据AI及最终整体验收仍待完成。\n\n完整报告/SHA见results/p50-active.json。检查点：{rel(out/'report.json')}。\n''',encoding='utf-8')
    (ROOT/current['resume']).write_text(f'''# P50恢复清单（2026-10-23）\n\n先读[实验记录](../experiments/EXP-P50-cold-units.md)、TX-SOURCE-STATUS.json的p50_current、results/p50-active.json。results未纳入Git，直接读取。\n\n1. P48完整profile `{cycle['installed_directory']}`已做两个软件重启和一次受控真断电验证；本轮运行{s['elapsed_software_s']:.1f}秒/{s['display_updates']}次更新。机器链通过，超过660秒的实体亮屏/运动确认：{physical}。\n2. 最后boot `{cycle['expected_boot']}`，当前RX idle、串口关闭、板仍通电未关机，自启动wrapper已重新选中。当前保留停止画面，下次启动会自动接收。再次工作先只读认板，不能假定这个boot仍有效。\n3. 只读入口：experiments/p43_status.py --enable-report {rel(args.enable)}。RX运行时先核验owned control再停；保持串口单一owner，DTR/RTS false，不热卸驱动或有绑定时装PL。\n4. 旧P42 profile和旧证据均保留。一次成功不能称0xFF或历史EVM波动已根治；不把UI丢弃旧前缀当ADC丢样率，不把本轮噪声峰值当已知目标或AI。\n5. 后续优先多次冷启动与更长接收稳定性；若做已知源试验，先检查旧板身份与既有TX保护，保留固定低功率/有界发射。不自动提高功率。AI需要独立采集会话和种子，P47学习包不是独立测试集。\n6. 检查点：{rel(out/'report.json')}，ZIP及成员SHA校验。断电前正常关机；本轮没有为结束工作再次关机。\n''',encoding='utf-8')
    start=ROOT/'START-HERE.md';(ROOT/now.strftime('START-HERE-BEFORE-P50-SAVE-%Y%m%dT%H%M%SZ.md')).write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作\n\n**当前入口：P50（2026-10-23）新版P48已完成一次受控真正断电后的自主接收/显示验证。** 先读[实验记录](docs/experiments/EXP-P50-cold-units.md)、[恢复清单](docs/handoff/RESUME-P50-20261023.md)和TX-SOURCE-STATUS.json的p50_current。\n\n新boot `{cycle['expected_boot']}`，本次自主运行{s['elapsed_software_s']:.1f}秒/{s['display_updates']}次更新，原始I/Q、显存、软件时钟/寄存器、显示单位和防休眠复核通过。超过660秒实体屏幕亮着且更新的人工确认：**{physical}**。\n\n完整profile `{cycle['installed_directory']}`已重新启用，默认P48。当前RX安全停止、串口关闭、taint0、无pending/disabled，板仍通电未关机；下次工作先读身份/boot/进程，不重放旧值。\n\n一次冷启动成功不关闭历史0xFF/质量波动根因。长稳、多次冷启动、无损连续性、校准与独立真实AI仍开放。P47学习包仍可用。\n\n检查点：`{rel(out/'report.json')}`。results不在Git，直接读文件系统。\n''',encoding='utf-8')
    result=checkpoint('p50-checkpoint',reports,out);print(result);print(label)


if __name__=='__main__':main()
