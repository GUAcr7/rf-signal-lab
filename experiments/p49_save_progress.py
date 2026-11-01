"""Save a reviewed P48 persistent migration and its limits; no board access."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
import xml.etree.ElementTree as ET
from p45_checkpoint import ROOT,checkpoint,read,write,sha,rel
from p43_finish_enable import reviewed,checked_units


def test_cases(p):
    return list(ET.parse(p).getroot().iter('testcase'))


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('cycle-one','review-one','units-one','cycle-two','review-two','units-two',
                 'enable','status','observation','observation-review','preflight','tests','timing-retest','human-event'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args()
    one,_=reviewed(args.cycle_one,args.review_one);two,_=reviewed(args.cycle_two,args.review_two)
    for trial,review,units in ((args.cycle_one,args.review_one,args.units_one),(args.cycle_two,args.review_two,args.units_two)):
        checked_units(trial,review,units)
    if (one.get('display_revision')!='p48' or two.get('display_revision')!='p48'
        or two['armed_boot']!=one['expected_boot'] or two['expected_boot']==one['expected_boot']
        or one['installed_files_sha256']!=two['installed_files_sha256']
        or one['installed_directory']!=two['installed_directory']):raise ValueError('two sequential exact P48 boots required')
    enable=read(args.enable);state=read(args.status);human=read(args.human_event)
    if (enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or enable.get('display_revision')!='p48' or not enable['persistent_autostart_enabled']
        or enable['installed_files_sha256']!=two['installed_files_sha256'] or enable['expected_boot']!=two['expected_boot']
        or enable['true_power_cycle_verified']):raise ValueError('accepted enabled warm profile required')
    if (state['status']!='read_only_persistent_profile_state_collected' or state['enable_report_sha256']!=sha(args.enable)
        or state['boot_id']!=two['expected_boot'] or state['taint']!='0' or state['RX_buffer']!='0' or state['RX_scans']!=['0']*4
        or state['native_process_observed'] or not state['persistent_wrapper_selected']
        or state['pending_present'] or state['disabled_present'] or not state['serial_closed']):raise ValueError('final idle selected profile required')
    if human['trial_sha256']!=sha(args.cycle_one) or not human['P48_units_visible_confirmed']:
        raise ValueError('human confirmation must reference this migration')
    cases=test_cases(args.tests);retry=test_cases(args.timing_retest)
    failed=[c for c in cases if any(list(c.iter(k)) for k in ('failure','error','skipped'))]
    key=lambda c:(c.get('classname'),c.get('name'))
    if (len(cases)!=93 or len(failed)!=1 or failed[0].get('name')!='test_until_signal_atomic_progress_and_constant_log_storage'
        or not retry or any(any(list(c.iter(k)) for k in ('failure','error','skipped')) for c in retry)
        or not {key(c) for c in failed}<={key(c) for c in retry}):raise ValueError('preserved initial failure and passing targeted retest required')
    now=datetime.now(timezone.utc)
    out=ROOT/'results'/now.strftime('p49-checkpoint-%Y%m%dT%H%M%S%fZ')
    reports={k:v.resolve() for k,v in vars(args).items()}
    current=dict(status='P49_P48_persistent_profile_verified_two_warm_boots_cold_test_pending',updated_utc=now.isoformat(),
        reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in reports.items()},
        record='docs/experiments/EXP-P49-persistent-units.md',resume='docs/handoff/RESUME-P49-20261023.md',checkpoint=rel(out/'report.json'),
        expected_boot=two['expected_boot'],current_enable=rel(args.enable),current_status=rel(args.status),
        installed_directory=enable['installed_directory'],binary_sha256=two['binary_sha256'],
        current_last_display_revision='p48',default_startup_display_revision='p48',persistent_native_replaced=True,
        original_profile_preserved='/etc/p43-20261022T030856Z',persistent_autostart_enabled=True,
        warm_boot_P48_verified=True,warm_boot_count=2,cold_boot_P48_verified=False,
        physical_P48_units_confirmation=True,physical_P48_animation_confirmation=False,
        RX_idle=True,serial_closed=True,board_shutdown_issued=False,TX_operations=False,
        RF_attribute_writes=False,reboots_issued=2,PL_changes='same accepted safe design loaded once per new boot; no hot load',
        initial_host_tests=dict(total=93,passed=92,failed=1),targeted_timing_retest_passed=True,
        timing_test_flakiness_root_cause_closed=False,PRODUCT_ID_FF_root_cause_closed=False,
        historical_EVM_variation_root_cause_closed=False,ADC_gaps='unknown',lossless_proven=False,AI_inference=False)
    root=read(ROOT/'TX-SOURCE-STATUS.json')
    root.update(status=current['status'],authoritative_current_field='p49_current',updated=now.isoformat(),
        record=current['record'],p49_current=current,
        status_note='P48显示已迁移为默认自启动，两个软件重启/时钟/原始数据/显存单位复核通过；当前安全停止，未做P48真正断电验收。',
        updated_note='COM8 recovered after USB port change; two exact-profile P48 warm boots, independent archive/clock/glyph reviews and physical units confirmed. Initial timing-test failure preserved with passing targeted retest.')
    write(ROOT/'TX-SOURCE-STATUS.json',root);write(ROOT/'results/p49-active.json',current)
    record=ROOT/current['record']
    with record.open('a',encoding='utf-8') as f:
        f.write(f'''\n## 完成结果\n\n新版完整目录`{enable['installed_directory']}`已安装并重新选为默认自启动。旧目录`/etc/p43-20261022T030856Z`未覆盖。两轮boot分别为`{one['expected_boot']}`、`{two['expected_boot']}`，同一profile的全部文件SHA完全相同。两轮分别运行{one['native_summary']['elapsed_software_s']:.3f}秒/{one['native_summary']['display_updates']}次更新、{two['native_summary']['elapsed_software_s']:.3f}秒/{two['native_summary']['display_updates']}次更新，板端init自行启动，主机不在启动后加载PL或启动应用。每次PL/DT只在新启动中各加载一次。\n\n两轮均经软件时钟/寄存器一致性、原始8192复数点前缀、1536000字节显存、独立NumPy及三项单位逐像素核对通过。报告与SHA见results/p49-active.json的reports。用户已确认首轮实体屏幕频谱和kHz/MS/s单位可见、画面正常；没有用此确认冒充新版运动画面或冷启动确认。\n\n最终终态：boot `{two['expected_boot']}`，taint0、RX buffer/scan0，无接收进程、串口已关闭、无pending/disabled，P48 wrapper已重新选中，板仍通电，未关机。当前保留停止画面；下次正常启动将运行P48。没有开启旧板TX或改动RF参数。\n\n## 检查中发现的额外问题\n\n完整针对性回归首次93项中92通过、1项失败。失败是主机模拟的进度轮询测试要求每次150ms读到的计数都严格增加；此要求受调度影响，失败记录原样保留，单独复测该项通过。未修改旧测试或冻结C源码来制造全绿，也不声称首次93项全通过；主机调度抖动是可能原因，尚未根治/证明。真实板卡两轮的进度、数据和退出检查均通过，不能由这个主机时序测试推断硬件连续性。\n\n## 尚未完成及下次步骤\n\nP48真正断电重启、超过十分钟背光与动态画面验证待做；P45旧P42的冷启动成功不能直接计为新版通过。先保存检查点并正常关机，再人工断电，提前被动抓取启动，确认新boot及实际显示版本，观察动态画面、复核时钟与数据。不要在有绑定驱动时重装PL。历史0xFF启动故障及大幅EVM波动根因、长期稳定性、无损连续采集、校准和独立真实AI仍未关闭。\n''')
    (ROOT/current['resume']).write_text(f'''# P49恢复清单（2026-10-23）\n\n先读[本轮记录](../experiments/EXP-P49-persistent-units.md)、TX-SOURCE-STATUS.json的p49_current及results/p49-active.json。results被gitignore排除，直接读文件系统。\n\n1. P48显示已成为默认自启动，完整目录`{enable['installed_directory']}`，两个软件重启及原始I/Q、显存、时钟、单位验收通过。旧P42 profile保留。\n2. 最后boot `{two['expected_boot']}`，RX idle、串口关闭、板仍通电未关机。下次上电先只读检查，不假设这个boot仍有效。新启动会自动接收，先核验身份与owned control再停止，不启动第二个接收进程。\n3. 只读入口：experiments/p43_status.py --enable-report {rel(args.enable)}。禁止重放旧身份或覆盖原始证据；COM8若不通先排查USB设备层，不反复发命令。\n4. 下一项为P48真正断电/背光/运动画面持续十分钟验收；需先保存并正常关机确认System halted，然后零UART输入被动抓启动。原P45/P48只作为历史证据，不能冒充本profile冷启动通过。p43_prepare_power_cycle目前仅识别P43/P45检查点，扩展格式兼容并测试后才能用于本P49检查点。\n5. 主机回归首次93项中一项时序断言失败，单独复测通过，保留两份XML。没有改动已冻结的C源码/原测试。避免把有界UI最新前缀当无损流或AI输出。\n6. 检查点：{rel(out/'report.json')}。代码、今日证据与旧报告引用均包含在校验ZIP里。P47学习包继续可用。\n''',encoding='utf-8')
    start=ROOT/'START-HERE.md';(ROOT/now.strftime('START-HERE-BEFORE-P49-SAVE-%Y%m%dT%H%M%SZ.md')).write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作\n\n**当前入口：P49（2026-10-23）P48显示已迁移为默认自启动，两个软件重启验收通过。** 先读[实验记录](docs/experiments/EXP-P49-persistent-units.md)、[恢复清单](docs/handoff/RESUME-P49-20261023.md)、TX-SOURCE-STATUS.json的p49_current。\n\n完整profile `{enable['installed_directory']}`；旧P42目录未覆盖。两次启动分别独立核对时钟、原始I/Q、显存和kHz/MS/s单位。用户确认新版实体屏幕内容正常。**新版真正断电及动态画面十分钟验收仍待完成**。\n\n最后boot `{two['expected_boot']}`，RX idle、资源释放、串口关闭、无pending/disabled，P48 wrapper重新选中。板仍通电，未执行关机。再次工作先认板/读boot与进程，不重放旧身份。\n\n回归首次93项中92通过、1项主机时序断言失败，单独复测通过；两份原始XML均保留，不称首次全绿。历史0xFF/质量波动根因、长稳、连续性与独立真实AI仍开放。\n\nP47离线学习包入口仍是run-rf-learning-demo.cmd。本轮检查点：`{rel(out/'report.json')}`；results不在Git，直接读取。\n''',encoding='utf-8')
    check=checkpoint('p49-checkpoint',reports,out)
    print(check);print(current['status'])


if __name__=='__main__':main()
