"""Save P39 evidence, human observation and resume notes locally; no board I/O."""
import argparse
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

from p32_session import ROOT
from p37_review_archives import archive_bytes
from p39_run_latest_panel import validate_summary


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8'))


def write(path, value):
    path.write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')


def rel(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--final-review', type=Path, required=True)
    args = p.parse_args()
    review = read(args.final_review)
    if review['status'] != 'passed_archived_displayed_prefix_NumPy_review' or not all(review['checks'].values()):
        raise ValueError('accepted independent review required')
    evidence = {key: Path(value['path']) for key, value in review['evidence'].items()}
    for key, path in evidence.items():
        if sha(path) != review['evidence'][key]['sha256']:
            raise ValueError('review input changed: '+key)
    trial = read(evidence['board_report'])
    if trial['status'] != 'passed_latest_buffer_RX_LCD_and_independent_idle_readback' or not trial['independent_final_idle_verified'] or trial['native_completion_unconfirmed'] or not trial['serial_closed']:
        raise ValueError('final native release/independent idle required')
    summary = validate_summary(trial['native_summary'], trial['duration_ms'], trial['interval_ms'], trial['cancel_signal_sent'])
    build_path = Path(trial['build_report']); build = read(build_path)
    for path, digest in build['inputs_sha256'].items():
        if sha(ROOT/path) != digest:
            raise ValueError('current build source changed: '+path)
    if sha(Path(build['binary'])) != build['binary_sha256']:
        raise ValueError('current binary changed')
    for key in ('iq_archive', 'fb_archive'):
        archive_bytes(evidence[key])
    if not review.get('screen_png') or not Path(review['screen_png']).is_file():
        raise ValueError('final screen review required')

    # Preserve every displayed prefix retained by the five P39 board sessions.
    sessions = [
        ('p39-board-20261021T141057Z', 'p36-file-archive-20261021T142821Z', 'p39-offline-review-20261021T142959Z'),
        ('p39-board-20261021T141438Z', 'p36-file-archive-20261021T142830Z', 'p39-offline-review-20261021T142958Z'),
        ('p39-board-20261021T141547Z', 'p36-file-archive-20261021T141813Z', 'p39-offline-review-20261021T143033921539Z'),
        ('p39-board-20261021T142055Z', 'p36-file-archive-20261021T142618Z', 'p39-offline-review-20261021T142821Z'),
    ]
    session_rows = []
    for native_dir, archive_dir, review_dir in sessions:
        native_path=ROOT/'results'/native_dir/'report.json'
        archive_path=ROOT/'results'/archive_dir/'report.json'
        analysis_path=ROOT/'results'/review_dir/'report.json'
        native=read(native_path); analysis=read(analysis_path)
        if (native['expected_boot']!=trial['expected_boot'] or not native['independent_final_idle_verified']
            or analysis['status']!='passed_archived_displayed_prefix_NumPy_review' or not all(analysis['checks'].values())):
            raise ValueError('historical session not accepted')
        archive, raw = archive_bytes(archive_path)
        if archive['expected_boot']!=trial['expected_boot'] or len(raw)!=32768 or hashlib.sha256(raw).hexdigest()!=native['raw_sha256']:
            raise ValueError('retained prefix changed')
        session_rows.append(dict(board_report=rel(native_path), archive_report=rel(archive_path),
            review_report=rel(analysis_path), native_summary=native['native_summary']))
    session_rows.append(dict(board_report=rel(evidence['board_report']), archive_report=rel(evidence['iq_archive']),
        review_report=rel(args.final_review), native_summary=summary))
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=ROOT/'results'/('p39-checkpoint-'+stamp);out.mkdir(exist_ok=False)
    human=dict(schema='rfsig.p39_human_panel.v1', recorded_utc=datetime.now(timezone.utc).isoformat(),
        source='direct user message in current chat', prior_user_observation='只能看到停止画面，没观察到更新',
        latest_user_observation='这次可以看到运动的画面了',
        related_trial='results/p39-board-20261021T142055Z/report.json',
        association='follow-up to two-minute observation run; exact observation timestamp was not supplied',
        physical_LCD_dynamic_picture_user_confirmed=True,
        individual_counters_explicitly_confirmed=False, measured_LCD_FPS=False,
        continuous_stability_or_absence_of_flicker_explicitly_confirmed=False,
        known_target_or_AI_confirmed=False)
    write(out/'human-observation.json',human);write(out/'sessions.json',session_rows)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    record_path='docs/experiments/EXP-HW-029-latest-prefix-RX-LCD.md'
    resume_path='docs/handoff/RESUME-P39-20261021.md'
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    state['authoritative_current_field']='p39_current'
    state['p38_current']['software_checkpoint_superseded_by']='p39_current'
    state['p39_current']=dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        status='single_RX_buffer_latest_prefix_monitor_120s_and_physical_motion_confirmed_UI_stop_label_corrected',
        record=record_path,resume_record=resume_path,checkpoint_report=rel(out/'report.json'),
        hardware_baseline='p37_current',last_identified_boot=trial['expected_boot'],
        fresh_factory_identification='results/p32-preflight-20261021T135359Z/report.json',
        controlled_merged_trial='results/p35-once-merged-20261021T135711Z/report.json',
        clock_acceptance='results/p37-clock-accept-20261021T140135Z/report.json',
        build_report=rel(build_path),binary_sha256=build['binary_sha256'],binary_bytes=build['binary_bytes'],
        native_mock_tests_passed=build['test_count'],
        final_trial_report=rel(evidence['board_report']),final_native_summary=summary,
        longest_duration_test='results/p39-board-20261021T142055Z/report.json',
        longest_duration_test_software_s=120.006055,longest_duration_display_updates=235,
        longest_test_binary='85b227471ca6ec86f2c8e8b35d2751d6d185c9871ca3a4cbf8ebb9b93b5611fc',
        final_binary_hardware_duration_ms=trial['duration_ms'],
        cancellation_trial='results/p39-board-20261021T141438Z/report.json',
        all_five_retained_displayed_prefixes_host_archived_and_NumPy_checked=True,
        full_IQ_stream_archived=False,retention_policy='only last displayed 8192-frame prefix per session; full refills and overwritten UI prefixes are not retained',
        source_frames_per_refill=65536,displayed_prefix_frames=8192,UI_interval_ms_requested=500,
        UI_overwrites_are_not_hardware_loss_counts=True,ADC_gaps='unknown',lossless_proven=False,
        single_context_and_buffer_per_session=True,physical_LCD_dynamic_picture_user_confirmed=True,
        human_observation=rel(out/'human-observation.json'),measured_LCD_FPS=False,
        screen_png=rel(Path(review['screen_png'])),final_independent_review=rel(args.final_review),
        RX_idle_after_trial_and_archival=True,RF_configuration_unchanged_during_monitor=True,
        RX_LO_Hz=2450000000,RX_sample_rate_Hz=30720000,RX_bandwidth_Hz=18000000,
        RX_gain_mode='manual',RX_gain_dB=0,RX_port='A_BALANCED',kernel_tainted_last_read=0,
        serial_closed=True,no_background_trial=True,native_completion_unconfirmed=False,
        screen_end_state='RX STOPPED in top and bottom status lines; last displayed prefix retained',
        TX_started_this_round=False,default_factory_startup_and_firmware_preserved=True,
        original_guard_restored_before_PL_load=True,controlled_reboots_this_round=1,
        PL_programming_this_round=1,overlay_applications_this_round=1,
        running_mode='rf',autostart_implemented=False,poweroff_issued=False,
        next_ordinary_reboot='factory RF-only; reidentify fresh boot then controlled P37 merged initialization and same-boot clock validation',
        factory_cold_start_PRODUCT_ID_FF_root_cause_closed=False,physical_external_PCLK_measured=False,
        CDC_Critical_remaining=58,external_input_delay_missing=7,external_output_delay_missing=29,
        long_term_stability_verified=False,known_target_proven=False,real_AI_verified=False,
        next_tasks=['repeat-boot and PRODUCT_ID_FF diagnosis','longer bounded receive/display plus fault recovery',
                    'rollback-capable standalone startup','known-source RF quality and real AI integration'])
    write(state_path,state)
    header='''# HW-029：单接收缓冲、最新数据频谱与实体LCD动态确认

日期：2026-10-21（北京时间）。本轮由用户授权继续推进；先处理COM8连接问题，受控新启动恢复P37合并配置，再推进板端监测软件。没有启动TX，没有改默认厂家固件或BOOT，没有设置自动启动。

## 验收结论

从P38每轮重建接收上下文推进到P39一个会话只创建一个RX上下文和一个65,536帧缓冲：工作线程反复refill，界面按500ms请求节奏消费最新8,192帧前缀，FFT和绘图不阻塞接收线程。两分钟硬件试验完成235次分析/写屏，结束后独立读取同boot、taint0、RF参数未变、buffer/scan全0；SIGTERM取消另有实板记录。用户先答“只能看到停止画面，没观察到更新”，后来明确回复“这次可以看到运动的画面了”，因此补充实体动态画面确认；没有据此宣称实际LCD FPS、全部数字变化或全程无闪烁已人工测量。

这是有界单缓冲监测，不是整流无损记录：每次refill仅将前8,192/65,536帧放进一个最新值信箱，界面未消费的旧前缀允许被覆盖。每会话只保留最后实际显示的32,768原始字节，均已电脑归档和独立NumPy复算。其余refill内容没有保存，UI覆盖计数不是ADC丢样计数，无硬件ADC序号/overrun证明，lossless=false、ADC gaps unknown。未知RF输入，不把DC附近峰当作已知目标，不输出校准dBm或AI类别。

## 启动与连接证据

- `results/p32-preflight-20261021T134617Z/report.json`及`...T134838Z/report.json`：CH340的COM8开口前报Windows设备错误，COM9仍可读。用户重插后仍失败，换USB接口后恢复；没有重装驱动、没有把连接恢复当作固件修复或认定唯一线材根因。
- `results/p32-preflight-20261021T135359Z/report.json`：新厂家启动036b1129-6524-443f-8b07-f724341ff1fd，RF_READY、taint0、idle。
- `results/p35-once-merged-20261021T135711Z/report.json`：一次hold新启动，boot=3c107af6-dcab-4ab0-8269-7f0f3a050390；恢复原guard后确认空绑定，单次装P37安全位流及配对显式overlay，RF+fb0通过。新增可选复用已验证板端产物，前后读SHA，不复用旧boot/保护状态。此次PL上传0字节但确实执行1次PL配置；不把“免重复上传”写成“免配置”。
- `results/p36-clockwiz-readback-20261021T135909Z/report.json`和`results/p37-clock-accept-20261021T140135Z/report.json`：LOCK1，M16.5/D2/O25，软件率与寄存器一致；不是仪器实测PCLK。
- `results/p35-finite-rx-prep-20261021T140136Z/report.json`：有限RX测试配置读回；`results/p33-rx-cancel-board-20261021T140459Z/report.json`：8轮取消/重建；`results/p36-sparse-smoke-20261021T140545Z/report.json`及`results/p36-panel-snapshot-20261021T140748Z/report.json`：布局/分析/绘图基线。

## 实现与测试

- `embedded/arm_latest_panel_p39/arm_latest_panel_p39.c`：互斥信箱+原子停止标记；refill逐次核验长度、布局、I/Q位置；low12掩码后符号扩展；RX结束先cancel并限时join，再销毁buffer/context。取消卡死走保守退出，不能提前销毁工作线程占用资源；RF前后读值一致、无TX API。
- `tests/test_native_latest_panel_p39.py`：18项实际C+mock动态库测试，覆盖单buffer、源序列/原始字节、独立数值、覆盖计数、异常布局/读取错误、真实SIGTERM、RF变化、不返回线程及参数边界。
- `tests/test_p39_summary_gate.py`：9项；`tests/test_p39_artifact_reuse.py`及`tests/test_p32_hold.py`：14项；`tests/test_p38_runner_gate.py`：更新后5项。保留严格路径、身份、同boot/idle截图父证据门槛。
- 第一构建`results/p39-build-20261021T140358Z`用于3秒基线；`results/p39-build-20261021T141323Z`用于取消、60秒和120秒；源/二进制SHA及输入快照保留。18项测试通过，ELF32/ARMhf/小端及GLIBC<=2.23检查通过。

## 实板结果（各次均单独结束并独立确认idle）

| 报告目录 | 软件时长/结束方式 | 发布/显示/覆盖/末尾待消费 | 验收范围 |
| --- | --- | --- | --- |
| p39-board-20261021T141057Z | 3.005秒，正常 | 1408/6/1401/1 | 初始单缓冲短测 |
| p39-board-20261021T141438Z | 3.015秒，SIGTERM | 1413/6/1406/1 | 主动取消、join和释放，summary=stopped，非时长完成 |
| p39-board-20261021T141547Z | 60.004秒，正常 | 28126/118/28007/1 | 固定配置一分钟监测 |
| p39-board-20261021T142055Z | 120.006秒，正常 | 56252/235/56016/1 | 两分钟监测与后续用户动态画面确认 |

以上均满足发布=消费+UI覆盖+末尾待消费。120秒记录maxrss=2588KiB；不能用单个进程峰值证明长期无内存泄漏。处理/绘图计时只对应CPU段，不能换算物理LCD FPS或ADC吞吐、端到端延迟。

## 屏幕复核后的小修复

两分钟结束后的framebuffer回读`results/p39-offline-review-20261021T142821Z/screen.png`显示底部RX STOPPED，但顶部残留RX active。这是状态提示缺陷，旧图/旧报告保留。已将顶部同步改成RX STOPPED或请求停止/失败并保留最后update/source序号；最终构建和短测证据见下方当前交付。两分钟实板证据属于修复前二进制，不能宣称修复后的精确SHA已经运行两分钟。

离线并行复核曾同秒创建相同输出目录而报FileExistsError，没有覆盖旧结果；目录时间戳增加微秒后60秒数据复核通过。未把此主机归档问题归因硬件。

## 剩余边界和下一步

厂家冷启动PRODUCT_ID_FF根因仍未关闭；此次厂家重入和hold成功仅增加启动样本。无自动合并启动、无无限运行/故障自恢复验收、无ADC连续性证明；58项Critical CDC、7输入/29输出延迟缺项、外部PCLK仪器验证仍开放。已知源RF质量和真实AI是后续独立验收任务。禁止热卸载RF/ADC/PWM/显示驱动或在驱动绑定时重配PL，禁止活动DMA改时钟。先做受控重复启动/0xFF诊断及有界长测恢复，再做可回退启动和已知信号/AI。
'''
    tail=f'''
## 当前交付与可恢复记录

- 最终构建：`{rel(build_path)}`，SHA `{build['binary_sha256']}`，{build['binary_bytes']}字节；18项native mock测试通过。
- 状态提示修复后的{trial['duration_ms']/1000:g}秒实板短测：`{rel(evidence['board_report'])}`；显示{summary['display_updates']}次，正常停止并独立idle核验。
- 最终IQ归档：`{rel(evidence['iq_archive'])}`；最终framebuffer快照/归档：`{rel(evidence['fb_snapshot'])}`、`{rel(evidence['fb_archive'])}`。
- 最终独立复核及回读图：`{rel(args.final_review)}`、`{rel(Path(review['screen_png']))}`；五项NumPy比较通过，图已人工查看，顶部/底部均停止。回读图不是实体照片。
- 五次会话的最后显示前缀、原始UART、机器摘要与独立复核索引：`{rel(out/'sessions.json')}`；用户原话及范围：`{rel(out/'human-observation.json')}`。
- 当前权威状态：TX-SOURCE-STATUS.json的p39_current；恢复步骤：`{resume_path}`。当前无后台RX/TX，串口已关，未发关机/断电命令。普通重启仍回厂家RF-only，临时RAM和PL应用状态不能靠断电保存。
'''
    (ROOT/record_path).write_text(header+tail,encoding='utf-8')
    resume=f'''# P39恢复步骤（2026-10-21）

先读START-HERE、TX-SOURCE-STATUS.json的p39_current和[HW-029](../experiments/EXP-HW-029-latest-prefix-RX-LCD.md)。P38/P37旧boot记录只供历史追溯。

当前最后实读新板boot={trial['expected_boot']}，P37安全M16.5/D2/O25合并配置，RF+800×480 LCD；LO2450MHz、Fs30.72MS/s、BW18MHz、manual0dB、A_BALANCED。最终试验结束，buffer/scan全0、taint0、原guard恢复，串口关闭，没有后台TX/RX。程序停止画面已修正顶部和底部均RX STOPPED；用户本轮另明确确认实体动态画面。

1. 每次先只读重新认两板、端口/实际boot、taint、guard、绑定和进程；不要复用上述boot作为参数。COM8独占，DTR/RTS在打开前false。若Windows再报设备错误，先排查USB枚举/连接；不开口失败时发送盲命令。
2. 若板仍处本次P37状态，核对身份/idle和同boot时钟证据，现有绑定下运行P39软件即可，禁止重新装PL或热卸驱动。最终软件构建`{rel(build_path)}`、最终短测`{rel(evidence['board_report'])}`。执行前runner会核对当前源文件、二进制SHA及同boot时钟证据，不能放宽门槛。
3. 若已普通重启，默认仍为厂家RF-only，LCD/应用不自动恢复。先检查RF_READY和0xFF并保留失败原件。按p35_once_merged_trial.py受控hold一次新启动，原guard恢复、空绑定门槛通过后只装1次P37安全bin+配对无firmware overlay；位流报告`results/p37-safe-bin-20261021T085630Z/report.json`及同目录overlay-report.json。可选--reuse-verified-board-artifacts引用`results/p35-once-merged-20261021T135711Z/report.json`以省重复串口上传，但只有板端文件SHA前后精确匹配才复用；不能复用旧boot、旧hold或略过单次PL配置。缺文件/哈希不符先停并排查，不热重试。
4. 新boot重新做p36_clockwiz_readback.py与p37_accept_clock_readback.py，然后有限RX配置读回、取消/重建、稀疏smoke和panel snapshot基线。console仅解绑已验证的framebuffer vtcon，不影响UART控制台。上述全部本boot通过，再用p39_run_latest_panel.py，传实际--expected-boot、最终--build-report、新--clock-acceptance、--duration-ms与--interval-ms（目前有界1..120秒，250..1000ms）。不要直接复制旧boot命令。
5. 先短测，验证正常停止/独立idle，再延长。每会话只保留最后显示的8192帧前缀，原始32KiB及SHA、metadata、UART、fb回读和NumPy复核归档电脑；不以UI skipped估算ADC丢样。需要完整IQ实验须另走受控完整记录器，不能把P39当无损录制器。
6. 优先解决重复启动/0xFF与有界长测/异常恢复，再做可回退独立开机显示和已知源/AI。全部默认厂家文件未改；不要为绕过失败而卸ADC/PWM或在绑定时重配PL。串口无回应时先保存被动尾迹，失联才用既有恢复步骤。

本次本地checkpoint：`{rel(out/'report.json')}`。它是P38保存包基础上的增量源码/证据快照；P38父包及原工程仍保留，非跨电脑一键安装包。电脑资料可断电保存，板RAM/运行PL不能。需停工时先正常关机再断电，本脚本没有关机或重启。
'''
    (ROOT/resume_path).write_text(resume,encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    if not old.startswith('# 从这里恢复项目工作\n'):
        raise ValueError('unexpected START-HERE heading')
    intro=f'''# 从这里恢复项目工作

**P39为当前软件状态（2026-10-21晚）：** 先读[HW-029](docs/experiments/EXP-HW-029-latest-prefix-RX-LCD.md)、[P39恢复步骤](docs/handoff/RESUME-P39-20261021.md)和TX-SOURCE-STATUS.json的p39_current。一个RX上下文/缓冲反复refill，最新前缀与频谱写屏分线程；两分钟235次更新、SIGTERM取消/释放及最后显示数据的独立NumPy复核通过，用户明确确认“这次可以看到运动的画面了”。已修复停止后顶部残留RX active，最终精确二进制另有3秒实板短测和回读证据。当前已停止、RX空闲、串口关闭，普通重启仍须按新boot初始化P37合并配置。

本轮五次会话只保留各自最后实际显示的32KiB原始前缀，均电脑归档，不是全流无损录制；ADC gaps未知，UI覆盖不是硬件丢样。厂家0xFF根因、长期稳定性、可回退自动启动、CDC/外部时序、已知源质量和真实AI仍未全部验收。P38停工保存包完整保留，作为历史父检查点；下方P38及更早“当前”字样均为历史状态，以本段和p39_current为准。

'''
    start.write_text(intro+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')

    parent=ROOT/'results/p38-stop-20261021T102648Z/checkpoint.zip'
    if not parent.is_file():raise ValueError('P38 parent checkpoint missing')
    selected=set()
    for directory in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        selected.update(path for path in (ROOT/directory).rglob('*') if path.is_file() and '__pycache__' not in path.parts)
    selected.update(path for path in ROOT.iterdir() if path.is_file() and path.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd'))
    for directory in (ROOT/'results').iterdir():
        if directory.is_dir() and (directory.name.startswith('p39-') or
            directory.name in ('p32-preflight-20261021T134617Z','p32-preflight-20261021T134838Z','p32-preflight-20261021T135359Z',
                'p35-once-merged-20261021T135711Z','p36-clockwiz-readback-20261021T135909Z','p37-clock-accept-20261021T140135Z',
                'p35-finite-rx-prep-20261021T140136Z','p33-rx-cancel-board-20261021T140459Z',
                'p36-sparse-smoke-20261021T140545Z','p36-panel-snapshot-20261021T140748Z') or
            (directory.name.startswith(('p36-file-archive-20261021T14','p36-fb-snapshot-20261021T14')))):
            selected.update(path for path in directory.rglob('*') if path.is_file())
    selected.update(path for path in (ROOT/'results').glob('p39-*.xml'))
    selected.discard(out/'report.json')
    manifest=[dict(path=rel(path),bytes=path.stat().st_size,sha256=sha(path)) for path in sorted(selected)]
    write(out/'manifest.json',manifest)
    zipped=out/'checkpoint.zip'
    with zipfile.ZipFile(zipped,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for item in manifest:z.write(ROOT/item['path'],item['path'])
        z.write(out/'manifest.json','manifest.json')
    with zipfile.ZipFile(zipped) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for item in manifest:
            content=z.read(item['path'])
            if len(content)!=item['bytes'] or hashlib.sha256(content).hexdigest()!=item['sha256']:
                raise ValueError('ZIP bytes changed')
    report=dict(status='passed_local_incremental_checkpoint_ZIP_CRC_and_all_file_SHA',board_operations=False,
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent)),
        archive=dict(path=rel(zipped),bytes=zipped.stat().st_size,sha256=sha(zipped)),
        files=len(manifest),all_ZIP_file_SHA_verified=True,final_review=rel(args.final_review),
        human_observation=rel(out/'human-observation.json'),sessions=rel(out/'sessions.json'),
        board_runtime_not_persisted=True,ordinary_reboot_autostart=False,poweroff_issued=False)
    write(out/'report.json',report)
    print(out);print(report['status'])


if __name__=='__main__':main()
