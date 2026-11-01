"""Save P48 candidate evidence without claiming persistent migration complete."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,checkpoint,read,write,sha,rel
from p37_review_archives import archive_bytes


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--suite',type=Path,required=True);p.add_argument('--profile',type=Path,required=True);args=p.parse_args()
    suite=read(args.suite);profile=read(args.profile)
    if (suite['status']!='passed_P48_finite_display_units_candidate_and_original_startup_rearmed'
        or not suite['startup_selection_rearmed'] or not suite['RX_idle'] or not suite['serial_closed']
        or suite['TX_operations'] or suite['PL_changes'] or suite['reboots_issued']):raise ValueError('completed, rearmed, idle display-only trial required')
    for item in suite['stages']:
        if item['exit_code']!=0 or sha(ROOT/item['report'])!=item['report_sha256']:raise ValueError('suite child changed')
    build_path=ROOT/suite['inputs']['build']['path'];build=read(build_path)
    if sha(build_path)!=suite['inputs']['build']['sha256'] or build['test_count']!=32:raise ValueError('native build changed')
    for path,digest in build['inputs_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('native source changed')
    trial_path=ROOT/suite['trial'];trial=read(trial_path);review_path=ROOT/suite['review'];review=read(review_path);units_path=ROOT/suite['units'];units=read(units_path)
    if (units['trial_sha256']!=sha(trial_path) or units['review_sha256']!=sha(review_path)
        or not all(units['checks'].values()) or not trial['independent_final_idle_verified']):raise ValueError('unit/numerical proof differs')
    for item in review['stages']:
        if item['exit_code']!=0 or sha(Path(item['report']))!=item['report_sha256']:raise ValueError('review child changed')
        if item['label'].endswith('_archive'):archive_bytes(Path(item['report']))
    final=read(ROOT/suite['final_status'])
    if (final['boot_id']!=suite['expected_boot'] or final['taint']!='0' or final['RX_buffer']!='0' or final['RX_scans']!=['0']*4
        or final['native_process_observed'] or not final['persistent_wrapper_selected'] or final['pending_present'] or final['disabled_present']):raise ValueError('final state differs')
    if (profile['status']!='prepared_P48_complete_startup_profile_PC_only_not_installed'
        or profile['suite_sha256']!=sha(args.suite) or profile['installed_on_board'] or profile['board_operations']
        or any(v['exit_code'] for v in profile['syntax_checks'])):raise ValueError('prepared profile differs')
    for name,digest in profile['files_sha256'].items():
        if sha(args.profile.parent/'files'/name)!=digest:raise ValueError('prepared file changed')
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p48-checkpoint-%Y%m%dT%H%M%S%fZ')
    record='docs/experiments/EXP-P48-display-units.md';resume='docs/handoff/RESUME-P48-20261022.md'
    current=dict(status='P48_frequency_units_candidate_board_verified_persistent_migration_pending',updated_utc=now.isoformat(),
        expected_boot=suite['expected_boot'],reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in vars(args).items()},
        record=record,resume=resume,checkpoint=rel(out/'report.json'),RX_idle=True,serial_closed=True,board_shutdown_issued=False,
        TX_operations=False,RF_attribute_writes=False,PL_changes=False,reboots_issued=0,persistent_autostart_enabled=True,
        current_last_display_revision='p48',default_startup_display_revision='p42',persistent_native_replaced=False,
        persistent_P48_migration_complete=False,prepared_profile=rel(args.profile),screen_png=suite['screen_png'],
        displayed_units=units['displayed'],native_tests_passed=32,software_engine='p42',
        physical_P48_screen_confirmation=False,warm_boot_P48_verified=False,cold_boot_P48_verified=False,
        PRODUCT_ID_FF_root_cause_closed=False,ADC_gaps='unknown',lossless_proven=False,AI_inference=False,
        current_enable=rel(ROOT/suite['rearm']),current_status=rel(ROOT/suite['final_status']))
    root=read(ROOT/'TX-SOURCE-STATUS.json');root.update(status=current['status'],authoritative_current_field='p48_current',
        updated=now.isoformat(),record=record,p48_current=current,
        updated_note='P48 frequency units candidate: 32 native tests, finite on-board RX/LCD and exact pixel/numerical review; original cold-verified startup retained, new profile PC-only',
        status_note='当前画面P48，默认自启动仍P42。P48持久迁移尚未完成，不能按准备包称作已安装。')
    write(ROOT/'TX-SOURCE-STATUS.json',root);write(ROOT/'results/p48-active.json',current)
    summary=trial['native_summary']
    (ROOT/record).write_text(f'''# P48：小屏频偏单位改进与实板候选验证

日期：2026-10-22（北京时间）。继续用户同意的小任务，将显示的FFT频点编号换成直观的频偏和采样参数。本轮未开启旧板TX、未改变射频属性、PL、设备树、驱动或电源，不热卸载，不重启。

## 开始状态与实现

只读检查`results/p43-status-20261022T132457Z/report.json`：新板boot `{suite['expected_boot']}`，taint0、RX buffer/scan0、无接收进程、持久wrapper选中且无pending/disabled。沿用P37合并硬件及P44防休眠设置。

在独立目录embedded/arm_panel_p48、embedded/arm_live_panel_p48保留修改版，旧P42/P46代码和已验收二进制不改。采集和生命周期引擎仍P42，JSON显式增加display_revision=p48、实际采样率、FFT间隔和频偏Hz；不把绘图改进声称新采集算法。

采样率只在AD9361读回并验证后传入显示。1024点FFT、30.72MS/s意味着30kHz/格，+33格应显示+990.0kHz，−33格为−990.0kHz；零输入显示none，未知采样率不猜Hz。界面加入MHz横轴、采样率MS/s及FFT间隔kHz，保留RMS、数字功率口径与no AI。

## 检查与原始证据

构建`{rel(build_path)}`：32项主机C原生模拟检查通过，覆盖原P42资源释放/取消/错误/有界日志及10组正负、零、边界、未知/不同采样率格式检查；ARM ELF32/hard-float/运行库兼容检查通过。候选ELF SHA `{build['binary_sha256']}`，{build['binary_bytes']}字节。

主试验`{rel(args.suite)}`，短时原生接收/写屏{summary['elapsed_software_s']:.6f}秒、{summary['display_updates']}次更新，结束后资源释放、RF属性不变、taint0。只保留最后实际显示的8192个RX1复数点/32768字节前缀，不是全流录制。

原始前缀和1536000字节显存均回传：`{rel(review_path)}`。独立NumPy对FFT峰值、RMS、总功率检查通过。`{rel(units_path)}`用字体位图逐像素核对显示值：peak offset `{units['displayed']['peak_offset']}`、sample rate `{units['displayed']['sample_rate']}`、FFT spacing `{units['displayed']['FFT_spacing']}`；全部一致。显存图`{rel(Path(suite['screen_png']))}`已人工检查布局，属于回读图，不是实体小屏照片；本轮未新增实体可见性确认。

本轮没有已知源发射，因此+30kHz峰值只是当前未知输入/噪声的频谱结果，不能称作已识别目标，不能与P46已知单音的+990kHz直接当同条件频偏漂移。此改动不增加AI、EVM、绝对RF频率校准或带宽识别能力。

## 当前状态与持久化边界

为使用严格归档工具，试验期间只暂时将下一次S99board选择切回原guard，未执行original start、未改变当前运行硬件。结束后恢复已通过冷启动的P43 wrapper，`{suite['rearm']}`；只读终态`{suite['final_status']}`确认RX idle、无pending/disabled、串口关闭。板仍通电，未关机。

**当前最后画面是P48，但下次默认开机应用仍是P42；P48持久迁移尚未完成。** 不覆盖旧已验收profile的monitor。新完整启动候选包`{rel(args.profile)}`（提议目录`{profile['proposed_directory']}`）仅在电脑准备，含monitor/bringup/boot/control/run/original及全部SHA，4份shell语法检查通过；原P43硬件初始化和13项shell门禁源码保持不变。该包未上传、未切换，没有P48新启动验收。

下一步先扩展并测试启动工具，显式接受P48构建和当前boot，移除旧P42构建路径硬编码；以新目录安装完整profile，做两个相同profile的新启动、原始IQ/显存/时钟及单位复核后再启用。准备包绑定的是本次boot；若下次boot已变，先重新认板并重新渲染，不能盲重放。P48真正断电与实屏确认单独保留待验收，不复用P45来冒充。

保存包`{rel(out/'report.json')}`逐项SHA/ZIP CRC检查；P47离线学习包和一键入口继续可用。历史0xFF、波动根因、长稳/时序/连续性及独立真实AI仍开放。
''',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P48恢复清单（2026-10-22）

先读[实验记录](../experiments/EXP-P48-display-units.md)、TX-SOURCE-STATUS.json的p48_current和results/p48-active.json。候选已做实板短时验证，**持久迁移未完成**。

1. 最后实读boot `{suite['expected_boot']}`，RX idle、串口已关闭、板未关机。最后画面是P48的kHz/MS/s单位，默认下次开机仍P42。旧P43自启动和P44防休眠保持启用；P47离线演示入口不受影响。
2. 继续前先运行`experiments/p43_status.py --enable-report {suite['rearm']}`只读认板/boot/guard/进程/DMA。不假设旧boot仍有效；若正在接收，先用已核验control stop并确认释放，不开第二个COM8 owner。
3. 实板候选suite `{rel(args.suite)}`，新ARM构建 `{rel(build_path)}`，频偏/像素检查 `{rel(units_path)}`。只保留最后显示前缀，不声称全流。
4. 持久候选 `{rel(args.profile)}`只在电脑。现有P43启动工具硬编码旧构建和旧suite，不能原样重放来迁移P48。先参数化并测试新构建/boot/候选证据，安装新目录的完整哈希链，不单独替换旧profile的monitor。
5. 迁移后的两个软件新启动需分别确认板端自行启动、单位/原始IQ/显存/时钟及安全停止，再重新启用匹配profile；P48真断电/实屏确认仍单独待做。失败留原UART/锁定标记，不能热卸驱动或绑定中装PL。
6. 若只做软件学习，继续使用根目录run-rf-learning-demo.cmd。AI主线仍需不同源种子/独立真实采集会话，不把P47同周期数据随机拆分。

检查点：`{rel(out/'report.json')}`。results不在Git，直接读文件系统。断电前需正常关机确认System halted；本轮未执行关机。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';history=ROOT/now.strftime('START-HERE-BEFORE-P48-SAVE-%Y%m%dT%H%M%SZ.md');history.write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作

**当前硬件应用入口：P48（2026-10-22）频偏单位候选已实板验证，持久迁移待完成。** 先读[实验记录]({record})、[恢复清单]({resume})及TX-SOURCE-STATUS.json的p48_current。32项原生检查、ARM编译、10秒/20次写屏、原始前缀与显存独立复核、三项单位逐像素核对通过。

**当前最后画面是P48，默认自启动应用仍是P42。** RX idle、资源释放、串口关闭，板仍通电未关机；已恢复原已验收P43 wrapper及P44防休眠。P48完整新profile仅在电脑准备，未安装、未做P48新启动/真断电验收。恢复时重新读boot/进程/DMA，不重放旧身份，不热卸驱动或绑定中装PL。

下一步参数化并测试启动工具后迁移完整P48 profile，做新启动/时钟/单位/原始数据验证。历史0xFF/波动根因、长稳/时序/无损连续性、独立真实AI仍开放。本轮未开启TX，+30kHz峰值来自未知输入，不是已识别目标。

**P47软件学习包仍可使用：** 根目录`run-rf-learning-demo.cmd`；[中文说明](deliverables/rf-learning-kit-20261022T130520Z/README.md)；[交付记录](docs/experiments/EXP-P47-learning-kit.md)。它是离线学习工具，不改板卡，也不是独立AI测试集。

本轮检查点：`{rel(out/'report.json')}`。results不在Git，直接读文件系统。旧入口：[历史快照]({rel(history)})。
''',encoding='utf-8')
    reports=dict(suite=args.suite,profile=args.profile,build=build_path,trial=trial_path,review=review_path,units=units_path)
    result=checkpoint('p48-checkpoint',reports,destination=out)
    print(result);print(current['status'])


if __name__=='__main__':main()
