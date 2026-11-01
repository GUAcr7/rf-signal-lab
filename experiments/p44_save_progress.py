"""Save evidence-scoped P44 outcome and a SHA/CRC-verified local checkpoint."""
import argparse,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from p43_finish_enable import reviewed

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('cycle','review','verification','enable','status'):p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();cycle,review=reviewed(args.cycle,args.review)
    verification=read(args.verification);enable=read(args.enable);status=read(args.status)
    if (verification['status']!='passed_new_warm_boot_over_600s_no_X_console_blank_disabled_backlight_enabled'
        or verification['expected_boot']!=cycle['expected_boot']
        or verification['inputs']['cycle']['sha256']!=sha(args.cycle)
        or verification['inputs']['review']['sha256']!=sha(args.review)
        or enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or enable['expected_boot']!=cycle['expected_boot'] or not enable['persistent_autostart_enabled']
        or enable['inputs']['current_warm_cycle']['sha256']!=sha(args.cycle)
        or enable['inputs']['current_warm_review']['sha256']!=sha(args.review)
        or status['status']!='read_only_persistent_profile_state_collected'
        or status['enable_report_sha256']!=sha(args.enable)
        or status['boot_id']!=cycle['expected_boot'] or not status['persistent_wrapper_selected']
        or status['taint']!='0' or status['RX_buffer']!='0' or status['RX_scans']!=['0']*4
        or status['pending_present'] or status['disabled_present'] or status['native_process_observed']):raise ValueError('final evidence differs')
    human_path=ROOT/'results/p44-human-long-test-20261022.json'
    human=read(human_path) if human_path.is_file() else {}
    physical=bool(human.get('physical_visibility_after_600s_confirmed') and human.get('expected_boot')==cycle['expected_boot'])
    policy_path=Path(verification['inputs']['policy']['path']);policy=read(policy_path)
    if sha(policy_path)!=verification['inputs']['policy']['sha256']:raise ValueError('policy proof changed')
    parent=ROOT/'results/p43-checkpoint-20261022T034146675785Z/report.json';parent_data=read(parent)
    parent_zip=ROOT/parent_data['archive']['path']
    if sha(parent_zip)!=parent_data['archive']['sha256']:raise ValueError('parent ZIP differs')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-checkpoint-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    record='docs/experiments/EXP-HW-034-display-sleep-policy.md';resume='docs/handoff/RESUME-P44-20261022.md'
    summary=cycle['native_summary'];now=datetime.now(timezone.utc).isoformat()
    current=dict(status='warm_boot_display_sleep_policy_verified_cold_retest_pending',updated_utc=now,
        expected_boot=cycle['expected_boot'],installed_directory=cycle['installed_directory'],
        display_policy_directory=policy['installed_directory'],display_policy_sha256=policy['installed_files_sha256'],
        reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in vars(args).items()},
        record=record,resume=resume,checkpoint=rel(out/'report.json'),persistent_autostart_enabled=True,
        RX_idle=True,serial_closed=True,board_shutdown_issued=False,
        physical_wake_confirmed=True,physical_visibility_after_600s_confirmed=physical,
        new_cold_boot_after_fix_verified=False,PRODUCT_ID_FF_root_cause_closed=False,
        failure_fallback_verified_on_real_board=False,ADC_gaps='unknown',lossless_proven=False,TX_started_this_round=False)
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    state.update(status=current['status'],authoritative_current_field='p44_current',updated=now,updated_note='P44: desktop DPMS black screen diagnosed; standalone display policy passed >600s warm boot; fresh cold test pending',
        record=record,p44_current=current,status_note='以p44_current及其恢复清单为准。P43的旧冷启动实体显示通过结论已撤回，修复后未再做真断电。')
    state['p43_current'].update(status='superseded_by_P44_warm_boot_sleep_fix_cold_retest_pending',
        current_boot_superseded=True,true_power_cycle_verified=False,physical_LCD_cold_start_accepted=False)
    write(state_path,state)
    write(ROOT/'results/p44-active.json',current)
    write(ROOT/'results/p43-active.json',dict(report=rel(args.enable),status=current['status'],status_report=rel(args.status),
        wrapper_may_be_installed=True,native_completion_unconfirmed=False,expected_boot=cycle['expected_boot'],RX_idle=True))
    (ROOT/record).write_text(f'''# HW-034：修复独立显示终端被桌面休眠关闭背光

日期：2026-10-22。当前boot `{cycle['expected_boot']}`。本轮未修改P37 FPGA/设备树或P42原生接收程序，旧P201未启动发射。

## 结论与证据

用户先反馈实体屏全黑、无明显背光。诊断时X显示查询为Monitor Off、DPMS Enabled，待机/挂起/关闭均600秒，控制台consoleblank=600；PWM2被请求但关闭、duty0。与此同时显存和接收程序有数据。因此撤回旧的整机实体显示冷启动通过结论，保留原机器证据。

正常X显示唤醒并关闭本会话休眠后，PWM2恢复enabled、period50000ns/duty50000ns，用户直接回复“亮起，能看到RF SIGNAL LAB或频谱”。这是本次黑屏受显示休眠控制且可恢复的直接证据；不推断所有黑屏都只有这个原因。

- 原失败反馈：`results/p44-human-display-failure-20261022.json`。
- 休眠状态：`results/p44-display-state-20261022T035717Z/report.json`；唤醒操作：`results/p44-wake-20261022T035907Z/report.json`。
- 人工唤醒确认：`results/p44-human-wake-confirmation-20261022.json`。
- 首次安装：`results/p44-policy-20261022T040536Z/report.json`保留failed原结果。其服务停止后立即检查时xinit尚未完成退出；后续独立读回确认退出，不能改写原失败为通过。
- 安装补验/下一次启动选择准备：`{rel(policy_path)}`；独立桌面退出读回`results/p44-display-state-20261022T040848Z/report.json`。
- 修复后一次全新软件重启：`{rel(args.cycle)}`。板端自行初始化并启动，主机登录后观察及停止；运行{summary['elapsed_software_s']:.3f}秒、更新{summary['display_updates']}次、RSS高水位{summary['maxrss_kib']}KiB。
- 最后实际显示的32KiB IQ、framebuffer、同boot时钟寄存器/驱动率及独立NumPy核对：`{rel(args.review)}`。
- 超过原600秒后，独立只读检查consoleblank0、没有Xorg/xinit、策略marker匹配当前boot、PWM2仍enabled：`{rel(args.verification)}`。这是软件/背光状态验收；不冒充光学测量。
- 超过600秒的实体可见性人工确认：**{physical}**。若False，保留为待验收，不能用显存截图替代。

## 持久实现

`/etc/init.d/xserver-nodm`改为SHA固定的条件入口，原厂家脚本精确备份在`{policy['installed_directory']}/xserver-original`。只有当前boot的P43标记、PERSISTENT_MONITOR_READY及进度文件全部存在时，由RF framebuffer终端占有显示，停止自身桌面服务，跳过X启动。通过标准VT转义将控制台blank/powerdown关闭，再用fb blank接口解除blank；不直接改PWM寄存器、不热卸任何驱动。不满足RF条件时仍委托原厂家X入口，stop也委托原入口。

策略及helper SHA固定在`{rel(policy_path)}`和最终校验报告；关机/重启不会丢失这些/etc文件。/run的进度和原始前缀仍会丢失，故已回传电脑。本轮测试结束后暂时恢复原S99board供通用归档工具严格检查，复核完成后重新选择同一P43持久wrapper：`{rel(args.enable)}`。最终只读状态`{rel(args.status)}`确认RX idle、buffer/scan0、taint0、无pending/disabled；未再关机。下次新boot会尝试自动接收/绘图。

## 验证范围及开放项

9项真实POSIX shell用例检查RF/其他模式分流、原入口委托、hash/唤醒失败；4项检查显式历史安装快照必须精确匹配，7项检查最新软件启动重新启用门禁。连同P43启动停止和P42运行归档门禁，本轮39项通过，`results/p44-final-gates-20261022.xml`。主机观察器增加有界20..900秒窗口，未放松原硬件新boot/空绑定/时钟/归档检查。测试XML及原始运行脚本随检查点保存。

修复后尚未再次人工真断电；不能声称冷启动实体显示已闭环。厂家0xFF偶发启动根因、实板故障回退、CDC/外部IO时序、物理PCLK测量、已知源质量波动、ADC无损连续性和真实AI仍开放。本轮十二分钟不等于24小时稳定性；外层24小时只是安全终止上限。
''',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P44恢复步骤（2026-10-22）

先读[HW-034](../experiments/EXP-HW-034-display-sleep-policy.md)和TX-SOURCE-STATUS.json的p44_current。当前机器证据指向boot `{cycle['expected_boot']}`；下一次上电必须重新识别，不重放绑定旧boot的命令。

1. 最后状态：RX已停止、buffer/scan0、串口关闭，新板仍通电，未发关机；显示保留最后快照。持久P43启动和P44显示防休眠策略都已启用。要断电先正常关机并确认System halted。
2. 新接电后先用`experiments/p43_status.py --enable-report {rel(args.enable)}`只读认板/boot/SHA/pending/disabled/进度；COM8只允许一个owner，打开前DTR/RTS false。若running，不能再装PL或另起接收进程。
3. P43安装目录`{cycle['installed_directory']}`；P44显示策略目录`{policy['installed_directory']}`。用SHA逐项核验，检查/run/p44-display-policy为RF_PANEL_NO_X_DPMS、consoleblank为0、没有Xorg/xinit、debug PWM2 enabled。不要只看brightness8或bl_power0判断背光。
4. 如果出现pending/disabled、0xFF、串口失联，先保存UART/dmesg/启动日志，不热卸ADC/RF/PWM/显示，不在已绑定驱动下重配PL；已有启动保护在下一个新boot选择厂家回退，实板故障演练仍待做。
5. 运行时停止只通过已核验`{cycle['installed_directory']}/control stop`，再独立确认进度stopped、RX idle、taint0。/run只保留最后实际显示前缀；下一次boot前按当前新boot回传原始IQ/显存并独立复核，不能仅保留截图。
6. 回退P44时只用已存原X入口精确SHA核对后在/etc/init.d原子替换；若需要回厂家RF模式，正常停止后仅更换下一次S99board选择，正常重启生效。不要对当前合并驱动执行原guard start，不重新启动X与RF直写显存争用。
7. 下一项：正常关机后人工断电约10秒再接电，验证新的boot自动RX且实体屏在600秒以后仍可见/更新；先保存当前证据。修复后真断电尚未验收，不能拿本次软件重启替代。随后再做已知源质量/真实AI等项目验收。

检查点：`{rel(out/'report.json')}`。results被gitignore排除，备份不能只依赖Git。父P43原始检查点保持不变；其中旧实体冷启动通过结论已由本轮反馈纠正。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    intro=f'''# 从这里恢复项目工作

**当前入口：P44显示休眠修复（2026-10-22）。** 先读[HW-034]({record})、[P44恢复步骤]({resume})及TX-SOURCE-STATUS.json的p44_current。已定位桌面DPMS在600秒后关闭背光；用户确认正常唤醒后屏幕亮起。条件启动策略已持久保存，修复后一次全新软件启动运行{summary['elapsed_software_s']:.1f}秒、更新{summary['display_updates']}次，超过600秒的背光/无X/consoleblank0读回及IQ/显存/时钟独立复核通过。超过600秒实体可见人工确认={physical}；**修复后真断电尚待验收**。

当前RX idle、串口关闭、板仍通电，未关机；P43持久wrapper和P44显示策略均已启用。下次新boot会尝试自动初始化接收/绘图。0xFF根因及其他项目开放项未关闭。旧P43“整机冷启动通过”已被实体黑屏反馈撤回，以下所有旧“当前”均为历史；不要重放旧boot或热卸驱动/重配PL。

---

'''
    start.write_text(intro+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    files=set()
    def add(f):
        if f.is_file() and f.name!='checkpoint.zip' and '__pycache__' not in f.parts:files.add(f.resolve())
    for d in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        for f in (ROOT/d).rglob('*'):add(f)
    for f in ROOT.iterdir():
        if f.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd') or f.name in ('.gitignore','.gitattributes'):add(f)
    for f in (ROOT/'results').iterdir():
        if '20261022' in f.name or f.name in ('p43-active.json','p44-active.json'):
            if f.is_dir():
                for child in f.rglob('*'):add(child)
            else:add(f)
    # Include any older referenced evidence transitively; never nest large parent ZIPs.
    def strings(v):
        if isinstance(v,str):yield v
        elif isinstance(v,dict):
            for x in v.values():yield from strings(x)
        elif isinstance(v,list):
            for x in v:yield from strings(x)
    visited=set()
    while True:
        pending=[f for f in files if f.name=='report.json' and f not in visited]
        if not pending:break
        for f in pending:
            visited.add(f)
            try:v=read(f)
            except (ValueError,UnicodeError):continue
            for s in strings(v):
                if '\n' in s or len(s)>400:continue
                normalized=s.replace('\\','/')
                if not(normalized.startswith('results/') or normalized.lower().startswith(ROOT.as_posix().lower()+'/results/')):continue
                child=Path(s);child=(child if child.is_absolute() else ROOT/child).resolve()
                if not child.is_relative_to(ROOT/'results') or not child.is_file():continue
                add(child)
                if child.name=='report.json':
                    for member in child.parent.rglob('*'):add(member)
    rows=[dict(path=rel(f),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(files)];write(out/'manifest.json',rows)
    zipped=out/'checkpoint.zip'
    with zipfile.ZipFile(zipped,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(zipped) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for row in rows:
            raw=z.read(row['path'])
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('member SHA differs')
    write(out/'report.json',dict(status='passed_P44_checkpoint_ZIP_CRC_and_all_member_SHA',files=len(rows),all_member_SHA_verified=True,
        archive=dict(path=rel(zipped),bytes=zipped.stat().st_size,sha256=sha(zipped)),
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent),archive_sha256=sha(parent_zip)),
        reports=current['reports'],board_operations=False,persistent_autostart_enabled=True,board_shutdown_issued=False,
        physical_visibility_after_600s_confirmed=physical,new_cold_boot_after_fix_verified=False))
    print(out);print('passed_P44_checkpoint_ZIP_CRC_and_all_member_SHA')
if __name__=='__main__':raise SystemExit(main())
