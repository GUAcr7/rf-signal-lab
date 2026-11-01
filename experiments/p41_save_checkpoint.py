"""Save accepted P41 scope, experiment/resume notes and a verified local ZIP."""
import argparse
from datetime import datetime,timezone
import hashlib,json,zipfile
from pathlib import Path
from p32_session import ROOT
from p36_fb_snapshot_run import accepted_panel_parent
from p37_review_archives import archive_bytes


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text('utf-8'))
def rel(path):return path.resolve().relative_to(ROOT).as_posix()
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--post-review',type=Path,required=True);args=p.parse_args()
    review=read(args.post_review)
    if review['status']!='passed_autonomous_boot_post_clocks_archives_and_independent_NumPy':raise ValueError('accepted post review required')
    trial_path=Path(review['trial']);trial=read(trial_path);boot=trial['expected_boot']
    if sha(trial_path)!=review['trial_sha256'] or not accepted_panel_parent(trial,boot):raise ValueError('parent trial changed')
    for stage in review['stages']:
        path=Path(stage['report'])
        if sha(path)!=stage['report_sha256']:raise ValueError('post-review stage changed')
        if stage['label'] in ('IQ_archive','framebuffer_archive'):archive_bytes(path)
    final_path=Path(review['final_review']);final=read(final_path)
    if not all(final['checks'].values()):raise ValueError('NumPy comparisons failed')
    summary=trial['native_summary'];stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S%fZ')
    out=ROOT/'results'/('p41-checkpoint-'+stamp);out.mkdir(exist_ok=False)
    human=dict(source='direct user reply to P41 autonomous-boot screen question',
        quote='只看到 RX STOPPED，没观察到更新',related_trial=rel(trial_path),
        physical_stopped_picture_seen=True,physical_dynamic_update_confirmed=False,measured_FPS=False,
        prior_P39_dynamic_confirmation_is_historical=True)
    write(out/'human-observation.json',human);(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    record='docs/experiments/EXP-HW-031-autonomous-once-startup.md'
    resume='docs/handoff/RESUME-P41-20261021.md'
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    state['authoritative_current_field']='p41_current';state.pop('active_trial_report',None)
    state['p40_current'].update(active_trial_is_not_accepted=False,active_trial_completed=True,
        software_checkpoint_superseded_by='p41_current')
    state['p41_current']=dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        status='one_shot_autonomous_init_and_120s_monitor_accepted_stopped_normally',record=record,resume_record=resume,
        trial_report=rel(trial_path),post_review=rel(args.post_review),last_identified_boot=boot,
        clock_acceptance=rel(Path(review['clock_acceptance'])),final_NumPy_review=rel(final_path),
        screen_png=rel(Path(review['screen_png'])),native_summary=summary,
        native_build='results/p39-build-20261021T142930Z/report.json',native_binary_sha256=trial['binary_sha256'],
        board_init_loaded_merged_PL_and_launched_monitor=True,
        host_sent_PL_or_overlay_commands_after_boot=False,host_launched_monitor_after_boot=False,
        startup_launch_uptime_log='7.76 s before launch, from /proc/uptime; not measured time-to-first-visible-frame',
        original_guard_restored_before_PL=True,fresh_empty_bindings_verified=True,
        software_reboots_in_P41=1,PL_programming_attempts=1,overlay_apply_attempts=1,
        default_firmware_replaced=False,BOOT_or_base_DTB_modified=False,mode_modified=False,
        installed_dormant_directory=trial['installed_directory'],persistent_autostart_enabled=False,
        infinite_duration_monitor_implemented=False,automatic_fault_recovery_verified=False,
        next_ordinary_reboot='factory RF-only with original S99board; does not automatically repeat P41',
        RX_idle=True,RF_configuration=dict(sample_rate_Hz=30720000,bandwidth_Hz=18000000,LO_Hz=2450000000,gain_mode='manual',gain_dB=0,port='A_BALANCED'),
        last_kernel_taint=0,serial_closed=True,no_background_monitor=True,native_completion_unconfirmed=False,
        screen_end_state='RX STOPPED; last displayed prefix',
        physical_stopped_picture_user_confirmed=True,physical_dynamic_update_confirmed_in_P41=False,
        human_observation=rel(out/'human-observation.json'),
        previous_P39_physical_motion_confirmation_retained=True,measured_LCD_FPS=False,
        user_reported_cold_power_cycle_in_P40=True,cold_autonomous_P41_profile_verified=False,
        factory_PRODUCT_ID_FF_root_cause_closed=False,long_term_stability_verified=False,
        lossless_proven=False,ADC_gaps='unknown',full_stream_saved=False,known_target_proven=False,real_AI_verified=False,
        TX_started=False,CDC_Critical_remaining=58,external_input_delay_missing=7,external_output_delay_missing=29,
        checkpoint_report=rel(out/'report.json'),parent_checkpoint='results/p39-checkpoint-20261021T143630550744Z/report.json',
        next_tasks=['controlled long-running monitor with bounded logs and safe stop',
            'rollback-capable persistent startup and cold-start testing','PRODUCT_ID_FF failure/success evidence pairing',
            'known-source quality and real AI integration'])
    write(state_path,state)
    text=f'''# HW-031：一次性板端自主启动与两分钟接收/显示

日期：2026-10-21晚（北京时间）；沿用P39最终原生C程序和P37安全M16.5/D2/O25合并硬件。上轮重启/断电观察见[HW-030](EXP-HW-030-boot-recovery-and-cold-observation.md)。

## 验收结论与限制

**这一次新启动中，板端启动脚本自行完成合并PL/overlay初始化、RX配置及有界频谱显示；主机没有在登录后发送装PL、应用overlay或启动monitor的命令。** 两分钟完成{summary['display_updates']}次分析/CPU写屏，正常停止；同boot独立确认RF参数、buffer/scan释放、taint0、guard恢复，时钟后验及归档IQ的NumPy复核通过。

这是一次性、120秒有界启动试验，不是“每次通电永久自动运行”或无限运行版本。临时S99 wrapper在新boot加载PL前就恢复原始S99board；下次普通重启仍按厂家RF-only启动。未更换默认固件、BOOT、base DTB或board-mode，没有启动TX。用户本次只答“只看到 RX STOPPED，没观察到更新”，所以**本次实体动态人工确认仍为false**；P39早先的实体运动确认只作为历史证据。不能混同机器写屏计数和物理LCD FPS。

## 一次性启动实现

- `board/boot/p41-monitor-once.sh.in`：必须是与armed boot不同的新boot，且原guard SHA和p35-hold标记匹配；程序/位流/配对DTBO哈希通过；无RF、显示及overlay绑定才单次装PL+单次应用overlay。按唯一PHY/ADC/DDS名字确认、先idle再设manual0dB/2450MHz，Fs30.72MS/s/BW18MHz不变；只解绑framebuffer vtcon，保留UART console。无热卸载、无热重试。
- `p41_boot_templates.py`：严格路径/UUID/SHA/时长输入；复用已审查hold模板，将原guard恢复并sync后才调用独立runtime。runtime前40秒启动期限，monitor另有135秒timeout和22秒终止后备；应用自身120秒停止/join/释放。后备期限不是已验证的故障自恢复机制。
- `p41_autonomous_once.py`：先验证本机已归档的P40 suite、源码/ARM构建、实际shell测试和配对产物，再上传到新独立RAM/`{trial['installed_directory']}`。验证当前目标BusyBox timeout在init脚本正常返回后保留后台子进程的行为；保存原guard备份后才原子arm、sync并发出一次普通reboot。全程单串口owner，无并发板端操作。
- 新启动自动日志依次为ORIGINAL_GUARD_VERIFIED、EMPTY_BINDINGS_VERIFIED、PL_ATTEMPT=1、OVERLAY_ATTEMPT=1、MONITOR_LAUNCH、BOUNDED_MONITOR_LAUNCHED。/proc/uptime在发起launch前为7.76秒，它不是第一张物理画面出现时刻，也不是端到端RF延迟。原始启动UART证明上述marker早于login。

## 原始证据

- 本轮试验：`{rel(trial_path)}`，boot={boot}；同目录有实际执行源、runtime.sh、boot.sh、monitor二进制、完整启动UART、autonomous-boot-log.txt及program.txt。
- 本轮post-accept：`{rel(args.post_review)}`，6阶段逐项退出码/报告SHA。
- 本boot时钟后验：`{rel(Path(review['clock_acceptance']))}`。独立live DT地址/driver gate后读LOCK和DRP，软件/寄存器M16.5/D2/O25一致；未仪器测外部PCLK。自动runtime在启动时只作软件33MHz率门槛，独立LOCK核验是本次应用结束后的主机后验，不冒充启动前仪器测量。
- 原始最后显示前缀和framebuffer均已回传电脑，分块SHA/gzip CRC/总SHA核验通过；`{rel(final_path)}`独立NumPy核对峰值、bin、RMS和频谱总功率通过。回读图`{rel(Path(review['screen_png']))}`已查看，上下均RX STOPPED，不是实物照片。
- 用户回答单独记录`{rel(out/'human-observation.json')}`，不改写机器试验原记录。

## 机器摘要

```json
{json.dumps(summary,ensure_ascii=False,indent=2)}
```

发布=消费+UI覆盖+末尾待消费。每refill65536帧，只复制前8192帧到最新信箱，UI未消费的旧前缀可被覆盖；本次仅保留最后实际显示的32768原始字节。UI覆盖不是ADC丢样计数；未保留全流，无独立ADC序号/overrun证据，ADC gaps unknown、lossless=false。输入未知，近DC峰不能说成检测到已知RF目标，功率不是校准dBm，没有AI分类。

## 测试与实际纠错

- `results/p41-preparation-20261021T152204Z/report.json`：8项实际POSIX shell在隔离临时目录执行，覆盖恢复顺序/后台子进程存活、旧boot/错误guard/runtime/bin SHA、已有overlay/RF、失败probe没有二次PL/overlay。源哈希前后固定、原始模板sh -n通过；不是硬件驱动仿真或目标启动验收。
- `results/p41-common-evidence-gates-20261021.xml`：15 passed，扩展严格的P41已结束/idle/同boot/guard恢复/新启动证据门槛，保留原P38/P39规则。时钟后验允许已验收的P41启动报告，所有寄存器/软件率校验不变。
- 第一次shell测试6 failed/2 passed，来自测试目录映射把/proc/sys二次替换，以及Windows不能直接创建含冒号的iio:device目录。失败XML和测试源码保留（results/p41-shell-tests-20261021.xml、p41-shell-attempt1-source.py）；修正仅影响测试副本的单遍绝对路径映射/目录名，实际部署shell不用测试根目录或假硬件。后来8项通过，未删负例或改为无条件成功。
- 目标板独立验证timeout后台存活原语通过，随后真实启动及两分钟应用完成；没有把WSL的timeout行为直接当成BusyBox目标证据。

## 当前状态与后续任务

原guard已恢复、默认mode仍rf、RX idle、串口关闭，无后台monitor/TX，未再次关机。`{trial['installed_directory']}`保留为休眠的试验副本，不等于永久启用自启动。当前权威状态p41_current，恢复步骤见[RESUME-P41](../handoff/RESUME-P41-20261021.md)。

接下来先实现有受控停止和有界日志的长时间运行，做更长稳定性/取消恢复，再将已验证路径做成可回退的持久启动并另做真断电试验。厂家0xFF根因、58项CDC、7输入/29输出外部延迟缺项、物理PCLK、ADC连续性、已知信号质量和真实AI仍开放。本次P41是软件重启，不能继承P40厂家RF冷启动成功而称“P41冷启动已通过”。
'''
    (ROOT/record).write_text(text,encoding='utf-8')
    (ROOT/resume).write_text(f'''# P41当前恢复清单（2026-10-21）

先读START-HERE、TX-SOURCE-STATUS.json的p41_current及[HW-031](../experiments/EXP-HW-031-autonomous-once-startup.md)。

最后实读boot={boot}，P37安全合并PL/显式overlay；P41一次性开机自动发起120秒monitor已正常停止，screen上下RX STOPPED，RX buffer/scan全0、taint0，原S99board恢复。默认RF固件/overlay/BOOT/board-mode未改，旧板未启动TX。串口已关闭，无后台采集、未发新关机命令。

1. 先只读重新认端口/真实boot、taint、guard、RF/显示绑定及进程；不要把上述boot直接复制成下次参数。COM8独占，DTR/RTS在open前false。
2. 若同一P41 boot及idle/参数/源SHA都匹配，可用P39 runner在现有绑定下继续有界软件试验：构建results/p39-build-20261021T142930Z/report.json，时钟验收`{rel(Path(review['clock_acceptance']))}`。不要重装PL/overlay，不热卸驱动或在DMA中改时钟。
3. 若已重启，P41 wrapper已自恢复为原S99board，默认回厂家RF-only；不会再次自动显示。先保留完整启动日志/0xFF状态和活DT GPIO/SPI信息；必要时用p40_reset_readback.py，只读诊断不翻GPIO。未到登录时先有界被动观察，不能将2秒shell未建立当作RF损坏。
4. 再试P41不得重放本次boot或旧suite。当前P41执行器要求本启动已完成且归档的恢复suite，所有输入SHA/idle门槛通过后才允许一次arm；下次应先按P40/P35恢复清单重新建立本boot证据。若存在pending wrapper，先核对实际guard与已存backup、boot.sh，不重复arm。原guard须先恢复才装PL。
5. 下一步优化为受控长时间运行/有界日志、安全停止和可回退持久启动，另做P41 profile真正断电验收。任何失败保留原件，不热移除ADC/PWM/显示overlay，也不在驱动绑定下重配PL。

本地增量检查点：`{rel(out/'report.json')}`；父P39/P38检查点保留，results不在Git。程序运行态和RAM临时文件不能靠断电保存；电脑代码、原始证据和二进制已经持久化。需要停工先正常关机再断电。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    intro='''# 从这里恢复项目工作

**P41为当前状态（2026-10-21晚）：** 先读[HW-031](docs/experiments/EXP-HW-031-autonomous-once-startup.md)、[P41恢复清单](docs/handoff/RESUME-P41-20261021.md)及TX-SOURCE-STATUS.json的p41_current。一次性板端开机初始化+120秒接收/频谱写屏通过，电脑登录后没有发送启动应用或装PL命令；新boot时钟后验、IQ/屏幕归档和NumPy复核通过。原guard已在装PL前恢复，当前RX正常停止、串口关闭。用户本次只看到RX STOPPED，P41动态人工确认不算通过。

**下次普通重启仍回厂家RF-only，不会永久自动显示。** P41是一次性有限时长试验，长期运行/安全停止/有界日志和可回退持久启动仍待做；0xFF根因、CDC/外部时序、无损连续性、已知源质量和真实AI仍开放。下方P40“试验进行中”及更早“当前”段均为历史，已被本段与p41_current取代，不重放历史boot命令。

'''
    start.write_text(intro+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')

    # Source/evidence increment on top of the already verified P39/P38 bundle.
    parent=ROOT/'results/p39-checkpoint-20261021T143630550744Z/report.json';parent_data=read(parent)
    parent_zip=ROOT/parent_data['archive']['path']
    if sha(parent_zip)!=parent_data['archive']['sha256']:raise ValueError('parent checkpoint changed')
    files=set()
    def add(path):
        # Parent ZIPs remain separate immutable checkpoints; avoid nesting
        # those archives in this increment while retaining their reports/SHA.
        if path.is_file() and path.name!='checkpoint.zip':files.add(path.resolve())
    for directory in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        for path in (ROOT/directory).rglob('*'):
            if '__pycache__' not in path.parts:add(path)
    for path in ROOT.iterdir():
        if path.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd') or path.name in ('.gitignore','.gitattributes'):add(path)
    for directory in (ROOT/'results').iterdir():
        if directory.is_dir() and directory.name.startswith(('p40-','p41-')):
            for path in directory.rglob('*'):add(path)
        elif directory.is_file() and directory.name.startswith(('p40-','p41-')):add(directory)
    for name in ('p35-once-merged-20261021T144840Z','p35-once-merged-20261021T150934Z',
        'p32-preflight-20261021T144219Z','p32-preflight-20261021T150638Z','p32-preflight-20261021T150823Z'):
        for path in (ROOT/'results'/name).rglob('*'):add(path)
    visited=set()
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for v in value.values():yield from strings(v)
        elif isinstance(value,list):
            for v in value:yield from strings(v)
    while True:
        pending=[path for path in files if path.name=='report.json' and path not in visited]
        if not pending:break
        for path in pending:
            visited.add(path)
            try:value=read(path)
            except (ValueError,UnicodeError):continue
            for text in strings(value):
                if '\n' in text or len(text)>400:continue
                normalized=text.replace('\\','/')
                if not (normalized.startswith('results/') or normalized.lower().startswith(ROOT.as_posix().lower()+'/results/')):
                    continue
                candidate=Path(text)
                if not candidate.is_absolute():candidate=ROOT/candidate
                candidate=candidate.resolve()
                if not candidate.is_relative_to(ROOT/'results') or not candidate.is_file():continue
                add(candidate)
                if candidate.name=='report.json':
                    for member in candidate.parent.rglob('*'):
                        if member.name!='checkpoint.zip':add(member)
    files.discard((out/'report.json').resolve())
    rows=[dict(path=rel(path),bytes=path.stat().st_size,sha256=sha(path)) for path in sorted(files)]
    write(out/'manifest.json',rows);zipped=out/'checkpoint.zip'
    with zipfile.ZipFile(zipped,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(zipped) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for row in rows:
            raw=z.read(row['path'])
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('ZIP file SHA failure')
    write(out/'report.json',dict(status='passed_P41_incremental_checkpoint_all_ZIP_CRC_and_SHA',board_operations=False,
        archive=dict(path=rel(zipped),bytes=zipped.stat().st_size,sha256=sha(zipped)),files=len(rows),
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent),archive_sha256=sha(parent_zip)),
        trial=rel(trial_path),post_review=rel(args.post_review),all_member_SHA_verified=True,
        runtime_not_persisted=True,persistent_autostart_enabled=False,board_shutdown_issued=False))
    print(out);print('passed_P41_incremental_checkpoint_all_ZIP_CRC_and_SHA')


if __name__=='__main__':main()
