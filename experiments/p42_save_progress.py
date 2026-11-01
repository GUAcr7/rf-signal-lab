"""Save P42 work/resume records; no board access or hardware changes."""
import argparse
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
import zipfile
from p32_session import ROOT
from p36_fb_snapshot_run import accepted_panel_parent
from p42_run_live_panel import validate_progress
from p39_run_latest_panel import validate_summary

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--suite',type=Path,required=True)
    p.add_argument('--checkpoint',action='store_true')
    args=p.parse_args();suite_path=args.suite.resolve();suite=read(suite_path)
    accepted=suite['status']=='passed_short_until_signal_stop_restart_10min_and_archived_review'
    if args.checkpoint and not accepted:raise ValueError('only accepted completed suite may become checkpoint')
    if accepted:
        if len(suite['stages'])!=5:raise ValueError('incomplete P42 suite stage set')
        for stage in suite['stages']:
            child=Path(stage['report'])
            if stage['exit_code']!=0 or sha(child)!=stage['report_sha256'] or not read(child)['status'].startswith('passed_'):
                raise ValueError('suite child evidence changed')
        for key in ('short_report','cancel_report','long_report'):
            child=read(Path(suite[key]))
            if child['schema']!='rfsig.p42_board.v1' or not accepted_panel_parent(child,suite['expected_boot']):raise ValueError('completed P42 child required')
            validate_summary(child['native_summary'],child['duration_ms'],child['interval_ms'],child['cancel_signal_sent'])
            validate_progress(child['progress_samples'][-1],child['duration_ms'])
        review=read(Path(suite['final_review']))
        for stage in review['stages']:
            if stage['exit_code']!=0 or sha(Path(stage['report']))!=stage['report_sha256']:raise ValueError('final review child changed')
    boot=suite['expected_boot'];long_path=Path(suite['long_report']) if accepted else None
    long=read(long_path) if accepted else None
    record='docs/experiments/EXP-HW-032-long-running-RX-LCD.md'
    resume='docs/handoff/RESUME-P42-20261022.md'
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    current=dict(status=suite['status'],expected_boot=boot,suite_report=rel(suite_path),
        suite_report_sha256=sha(suite_path),record=record,resume=resume,
        native_build='results/p42-build-20261022T022745Z/report.json',
        fresh_merged_trial='results/p35-once-merged-20261022T022336Z/report.json',
        recovery_baseline='results/p40-recovery-suite-20261022T022826Z/report.json',
        persistent_autostart_enabled=False,PRODUCT_ID_FF_root_cause_closed=False,
        ADC_gaps='unknown',lossless_proven=False,physical_LCD_animation_confirmed_this_round=False,
        old_board_TX_started_this_round=False,updated_utc=datetime.now(timezone.utc).isoformat())
    if accepted:
        current.update(long_report=rel(long_path),long_report_sha256=sha(long_path),final_review=rel(Path(suite['final_review'])),
            screen_png=rel(Path(suite['screen_png'])),native_summary=long['native_summary'],
            RX_idle=True,serial_closed=True,board_shutdown_issued=False,
            progress_snapshots=len(long['progress_samples']),native_log_bytes=long['native_log_bytes'])
        current.update(runtime_readback=rel(Path(review['runtime_readback'])),runtime_allocated_KiB=review['runtime_allocated_KiB'])
    state.update(updated=current['updated_utc'],updated_note='HW-032: P42 long-running RX/LCD work; see p42_current',
        status=suite['status'],status_note='以p42_current及HW-032为准。长时长接收/显示验证不等于全流无损、已知源质量或真实AI验收。',
        record=record,p42_current=current)
    write(state_path,state)
    intro='''# 从这里恢复项目工作

**当前入口：P42（2026-10-22）**。先读[HW-032](docs/experiments/EXP-HW-032-long-running-RX-LCD.md)、[P42恢复步骤](docs/handoff/RESUME-P42-20261022.md)及TX-SOURCE-STATUS.json的`p42_current`。状态以其指向的实际suite报告为准；下方P41停机及其他“当前”字样均为历史。今天两板已重新上电，新板重新建立P37合并配置。

**普通重启仍回厂家RF-only，不是永久自动显示。** 不重放旧boot，不热卸ADC/PWM/显示驱动，不在驱动绑定时重配PL。`results/`不在Git，须直接读文件系统。当前运行是否结束以P42报告为准，不能照搬昨天的“已关机”。

'''
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    if '**当前入口：P42' not in old:start.write_text(intro+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    result='**仍在执行，尚未验收。**' if not accepted else f'''**三秒短测、duration=0直到信号停止、停止后重启并运行十分钟均通过。** 长测实际{long['native_summary']['elapsed_software_s']:.3f}秒、{long['native_summary']['display_updates']}次分析/写屏；原生程序最终日志{long['native_log_bytes']}字节，收到{len(long['progress_samples'])}次有效进度快照。结束后独立确认RX buffer/scan全0、taint0、RF参数和boot不变、串口关闭。三个会话的最后显示原始前缀均回传电脑，NumPy峰值/bin/RMS/频谱总功率核对通过；长测另有同boot时钟后验和framebuffer归档。

长测最大RSS {long['native_summary']['maxrss_kib']} KiB；这是本进程的高水位和有限时间观察，不能证明任意时长无泄漏。屏幕回读图：`{rel(Path(suite['screen_png']))}`（不是实物照片）。本轮没有再次向用户确认实体动画，不沿用P39的人工确认冒充本轮验收。'''
    text=f'''# HW-032：长时间接收、内存进度文件与安全停止

日期：2026-10-22（北京时间）。本轮仅修改应用及其验收/归档工具，硬件沿用P37安全M16.5/D2/O25。

## 本轮结论

{result}

权威suite：`{rel(suite_path)}`，状态`{suite['status']}`。新板boot `{boot}`；旧板本轮仅重新认板，没有发起TX。当前没有已知源输入保证，所有频谱功率均为数字计数域，不是dBm或已识别目标。

## 恢复与实现

- 上电只读识别：`results/p32-preflight-20261022T022119Z/report.json`，两板在线，新板厂家RF_READY，taint0、空闲。
- 新hold启动：`results/p35-once-merged-20261022T022336Z/report.json`。先恢复原S99board，验证fresh/空绑定门槛，再单次PL+单次显式overlay；没有热卸驱动。默认固件、BOOT及board-mode未替换。
- 基础suite：`results/p40-recovery-suite-20261022T022826Z/report.json`。新增`--baseline-only`，只验证当前boot时钟、RF、8轮取消重建、layout和静态写屏；用不同通过状态，不能当完整P40长测通过，也不能绕过P41执行器的完整suite门槛。
- 新C源`embedded/arm_live_panel_p42/arm_live_panel_p42.c`从P39独立派生，旧P39源未改。一个libiio上下文和65536帧缓冲反复refill；只复制前8192帧到最新信箱，UI按500ms请求间隔取最新前缀分析/写屏，UI覆盖计数与ADC丢样无关。
- 原生duration=0表示直到SIGTERM；正值支持至24小时，但仅本轮十分钟完成过实板验收。主机验收工具对duration=0强制要求有界取消时间，另有拥有者PID/命令行校验及timeout后备。
- 每次更新将小于4096字节的`progress.next`关闭后rename为`progress.json`，只保留最新一份；最终再写完成态。stdout只保留启动、最后指标/序号和结束行，取消每帧历史打印。最终保存最后真正显示前缀32768字节，未保存整段流或所有画面。
- 持续写入目录为`/run/p42-HHMMSS`，实读`/proc/mounts`确认/run为tmpfs后才允许运行，无写SD/tmp的退路。上传只经已有白名单`/tmp/p35-p42-*`暂存，校验后复制到/run；暂存不是持续日志。
- 任一进度写失败即停止，cancel→有期限join→释放buffer/context；不能join时拒绝声称清理完成。最终summary、progress、独立idle读回共同验收，不凭遗留running快照宣布通过。

## 测试与证据边界

- `results/p42-build-20261022T022745Z/report.json`：21项原生mock测试及ARMhf构建通过，GLIBC兼容检查通过；包括真实信号取消、原子快照并发读取、进度写失败、错误layout/版本/RF漂移和卡住线程。mock不替代实板。
- `results/p42-common-gates-20261022.xml`：8项主机门槛测试通过，覆盖P42计数/NaN/单调性、同boot及严格归档白名单；保留P38/P39/P41原规则。
- `results/p42-final-common-gates-20261022.xml`：补上主机duration0必须有界取消/非法时长在访问板卡前拒绝，并覆盖原summary、产物复用和boot门槛，共40项通过。
- 长测结束后另行只读检查运行目录：固定9个文件，含monitor/launcher/PID/退出码/log、最终progress/summary/原始前缀/其gzip，无历史序列或progress.next残留；总占用128KiB，log701B、progress433B。具体证据`results/p42-runtime-readback-20261022T024946Z/report.json`。这些数值只属于本次已完成的长测。运行阶段快照RSS高水位2452KiB，结束保存后最终2572KiB，不把收尾增加误写成全程恒定，也不声称任意时长无泄漏。
- `{rel(suite_path)}`按单串口owner顺序执行：短测原始字节归档与NumPy，duration0 SIGTERM及独立idle，取消会话归档与NumPy，重启十分钟，然后时钟后验、最后IQ与屏幕归档、独立NumPy。
- 每份子报告同目录保留executed.py、命令/退出码、原始UART读写和源/产物SHA。失败记录不删除。只保留各会话最后显示的32KiB原始数据，不是十分钟完整IQ。
- ADC gaps unknown、lossless=false；没有ADC序号/overrun独立证明，软件UI覆盖不能解读为硬件丢样；写屏次数不能称实体LCD FPS；时钟软件/寄存器一致不替代物理PCLK测量。

## 后续依赖

1. 在不削弱fresh/empty/guard/hash门槛的前提下，把P42已验证应用接入可回退的持久启动；显式启动状态、只读禁用/恢复路径、禁止热重载。先隔离shell负例，再有限时长启动实测，最后才扩大运行时长。
2. 对该最终启动版本另做真正断电验收及RF启动0xFF成功/失败对照，软件重启不能替代；目前0xFF根因没有关闭。
3. 后续已知源质量/指标、真实AI及其显示联调；58项关键CDC、7输入/29输出外部时序缺项、ADC无损连续性仍开放。不得因本次长测通过而抹掉这些边界。
'''
    (ROOT/record).write_text(text,encoding='utf-8')
    if accepted:
        (ROOT/record).write_text(text+'\n最终framebuffer图已人工查看：标题、绿色频谱曲线和上下RX STOPPED均可读，update1175/source block281142；它是显存回读，不是实体屏幕照片或动画确认。\n',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P42恢复步骤（2026-10-22）

先读[HW-032](../experiments/EXP-HW-032-long-running-RX-LCD.md)与TX-SOURCE-STATUS.json的p42_current，suite `{rel(suite_path)}`。本轮最近boot `{boot}`只能作历史身份，不能直接作为下次命令参数。

1. 先检查是否仍有进行中的P42 suite，运行中不再打开COM8。重新接线后用p32只读识别端口/真实boot/taint/进程/guard；DTR和RTS在打开前关闭，不盲发Ctrl-C。
2. 若仍是同boot且合并绑定/时钟/RF/idle全匹配，沿用本轮构建与验收时钟运行P42有界会话，不重复装PL。所有原始prefix应先归档电脑再切换boot。
3. 若已重启，普通启动仍厂家RF-only。先保存RF_READY或0xFF原始日志；仅当fresh hold新boot、原guard已恢复、无overlay/驱动绑定才按P35一次加载匹配P37安全bin/overlay，再执行当前boot基础suite和时钟验收。不复用旧boot，不热移除ADC/PWM/显示。
4. P42 duration0程序虽然支持直到信号，主机测试必须指定有界cancel-after；正常停止需要独立确认buffer/scan0、taint0、同boot、guard、RF不变。失联只保留原始尾迹，不叠加并发任务/盲重试。
5. 下一阶段为持久启动、最终版本真断电测试和已知源/AI；本轮不启用永久启动。需要断电时先另行正常关机并确认System halted，本文及旧停机记录不代表当前已经关机。

当前suite状态：`{suite['status']}`；临时/run数据断电丢失，验收归档在电脑results。电脑代码/实验记录已保存；如生成checkpoint另见p42_current.checkpoint。
''',encoding='utf-8')
    if not args.checkpoint:print('P42 progress and resume notes saved');return
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p42-checkpoint-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    parent=ROOT/'results/p41-checkpoint-20261021T154630949661Z/report.json';parent_data=read(parent)
    parent_zip=ROOT/parent_data['archive']['path']
    if sha(parent_zip)!=parent_data['archive']['sha256']:raise ValueError('parent P41 ZIP changed')
    # Store only this increment plus complete current source. Reports pull exact dependencies.
    current.update(checkpoint=rel(out/'report.json'));write(state_path,state)
    files=set()
    def add(p):
        if p.is_file() and p.name!='checkpoint.zip' and '__pycache__' not in p.parts:files.add(p.resolve())
    for directory in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        for f in (ROOT/directory).rglob('*'):add(f)
    for f in ROOT.iterdir():
        if f.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd') or f.name in ('.gitignore','.gitattributes'):add(f)
    for d in (ROOT/'results').iterdir():
        if '20261022' in d.name:
            if d.is_dir():
                for f in d.rglob('*'):add(f)
            else:add(d)
    def strings(value):
        if isinstance(value,str):yield value
        elif isinstance(value,dict):
            for v in value.values():yield from strings(v)
        elif isinstance(value,list):
            for v in value:yield from strings(v)
    visited=set()
    while True:
        pending=[f for f in files if f.name=='report.json' and f not in visited]
        if not pending:break
        for f in pending:
            visited.add(f)
            try:value=read(f)
            except (ValueError,UnicodeError):continue
            for s in strings(value):
                if '\n' in s or len(s)>400:continue
                norm=s.replace('\\','/')
                if not(norm.startswith('results/') or norm.lower().startswith(ROOT.as_posix().lower()+'/results/')):continue
                child=Path(s)
                if not child.is_absolute():child=ROOT/child
                child=child.resolve()
                if not child.is_relative_to(ROOT/'results') or not child.is_file():continue
                add(child)
                if child.name=='report.json':
                    for member in child.parent.rglob('*'):add(member)
    rows=[dict(path=rel(f),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(files)]
    write(out/'manifest.json',rows);zipped=out/'checkpoint.zip'
    with zipfile.ZipFile(zipped,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(zipped) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for row in rows:
            raw=z.read(row['path'])
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('ZIP member SHA mismatch')
    write(out/'report.json',dict(status='passed_P42_checkpoint_ZIP_CRC_and_all_member_SHA',files=len(rows),
        archive=dict(path=rel(zipped),bytes=zipped.stat().st_size,sha256=sha(zipped)),
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent),archive_sha256=sha(parent_zip)),
        suite_report=rel(suite_path),suite_sha256=sha(suite_path),all_member_SHA_verified=True,
        board_operations=False,board_shutdown_issued=False,persistent_autostart_enabled=False,runtime_not_persisted=True))
    print(out);print('passed_P42_checkpoint_ZIP_CRC_and_all_member_SHA')

if __name__=='__main__':main()
