"""Save P43 acceptance, precise startup state, resume notes and verified checkpoint."""
import argparse
from datetime import datetime,timezone
import hashlib,json,zipfile
from pathlib import Path
from p32_session import ROOT
from p43_finish_enable import reviewed

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--enable-report',type=Path,required=True);p.add_argument('--status-report',type=Path,required=True)
    args=p.parse_args();enable=read(args.enable_report);status=read(args.status_report)
    if enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots':raise ValueError('accepted enable required')
    if (status['status']!='read_only_persistent_profile_state_collected' or status['boot_id']!=enable['expected_boot']
        or status['taint']!='0' or not status['persistent_wrapper_selected'] or status['pending_present']
        or status['disabled_present'] or status['native_process_observed'] or status['RX_buffer']!='0'
        or status['RX_scans']!=['0']*4 or not status['serial_closed']):raise ValueError('matching independent idle status required')
    paths={k:Path(v['path']) for k,v in enable['inputs'].items()}
    for k,path in paths.items():
        if sha(path)!=enable['inputs'][k]['sha256']:raise ValueError('enable evidence changed')
    one,review1=reviewed(paths['cycle_one'],paths['review_one']);two,review2=reviewed(paths['cycle_two'],paths['review_two'])
    cold_verified=enable.get('true_power_cycle_verified') is True
    cold=None
    if cold_verified:
        cold,cold_review=reviewed(paths['current_cycle'],paths['current_review'],require_clock=False)
        cold_clock=read(paths['current_clock'])
        if cold['expected_boot']!=enable['expected_boot'] or cold_clock['boot_id']!=enable['expected_boot']:raise ValueError('cold identity differs')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p43-checkpoint-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    record='docs/experiments/EXP-HW-033-persistent-startup.md';resume='docs/handoff/RESUME-P43-20261022.md'
    directory=enable['installed_directory'];now=datetime.now(timezone.utc).isoformat()
    current=dict(status='two_software_boots_archived_persistent_profile_enabled_cold_test_pending',updated_utc=now,
        enable_report=rel(args.enable_report),enable_report_sha256=sha(args.enable_report),status_report=rel(args.status_report),
        status_report_sha256=sha(args.status_report),expected_boot=enable['expected_boot'],installed_directory=directory,
        record=record,resume=resume,checkpoint=rel(out/'report.json'),persistent_autostart_enabled=True,
        wrapper_sha256=enable['wrapper_sha256'],original_guard_sha256=enable['original_guard_sha256'],
        RX_idle=True,serial_closed=True,board_shutdown_issued=False,true_power_cycle_verified=cold_verified,
        failure_fallback_verified_on_real_board=False,PRODUCT_ID_FF_root_cause_closed=False,
        native_duration_ms=0,safety_limit_seconds=86400,ADC_gaps='unknown',lossless_proven=False,
        physical_LCD_animation_confirmed_this_round=False,TX_started_this_round=False,
        cycles=[rel(paths['cycle_one']),rel(paths['cycle_two'])],reviews=[rel(paths['review_one']),rel(paths['review_two'])])
    if cold_verified:
        current.update(status='two_software_boots_and_one_user_power_cycle_verified_autostart_enabled',
            cold_cycle=rel(paths['current_cycle']),cold_review=rel(paths['current_review']),cold_clock=rel(paths['current_clock']),
            cold_native_summary=cold['native_summary'],poweroff_interval_measured_by_computer=False)
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    state.update(updated=now,updated_note=('HW-033: two software boots and one user power cycle verified; persistent profile enabled' if cold_verified else 'HW-033: persistent startup enabled after two software boots; true cold test pending'),
        status=current['status'],status_note='以p43_current为准。S99board现为已校验P43持久wrapper；普通新boot会尝试自动接收/绘图，不再直接走原厂RF-only。',record=record,p43_current=current)
    write(state_path,state)
    write(ROOT/'results/p43-active.json',dict(report=rel(args.enable_report),status=current['status'],
        status_report=rel(args.status_report),wrapper_may_be_installed=True,native_completion_unconfirmed=False,
        expected_boot=enable['expected_boot'],RX_idle=True))
    summaries='\n'.join(f"- 第{i}轮：boot `{c['expected_boot']}`，运行{s['elapsed_software_s']:.3f}秒，更新{s['display_updates']}次，收到信号正常停止，RSS高水位{s['maxrss_kib']}KiB；`{rel(cp)}`，复核`{rel(rp)}`。" for i,c,s,cp,rp in
        ((1,one,one['native_summary'],paths['cycle_one'],paths['review_one']),(2,two,two['native_summary'],paths['cycle_two'],paths['review_two'])))
    (ROOT/record).write_text(f'''# HW-033：持久开机自启动、受控停止与回退候选

日期：2026-10-22（北京时间）。P42十分钟程序为父版本，本轮没有更换原生C/FPGA设计，只开发开机选择、首次就绪判断、控制和验收工具。

## 已验收及边界

**同一套持久启动文件经过两次真实软件重启，均由板端在登录前自行初始化合并硬件并启动P42接收/频谱显示；主机登录后只观察、发送受控停止及做归档。** 两轮都核验buffer/scan0、taint0、RF参数一致，原始最后显示前缀与framebuffer回传完整，同boot时钟后验和独立NumPy复核通过。

{summaries}

这两轮是软件重启，不能叫冷启动验证。归档工具仍校验原guard，因此主机在每轮应用停止且独立idle确认后临时恢复原S99board；归档完成后再次原样装入同一wrapper。**不是两次启动之间完全没有主机改文件**，也没有把主机停止命令冒充脱离电脑整机验收。程序启动确实发生在板端，完整UART有登录前marker；本轮未再次取得实体屏幕动态人工确认。最终回读图已查看，标题/曲线及上下RX STOPPED BY REQUEST可读；回读不等于实物照片。

## 当前持久状态（最后实读）

- 启用报告：`{rel(args.enable_report)}`；独立只读状态：`{rel(args.status_report)}`。当前boot `{enable['expected_boot']}`。
- `/etc/rcS.d/S99board`现为P43 wrapper，SHA `{enable['wrapper_sha256']}`；原始guard在`{directory}/original`，SHA `{enable['original_guard_sha256']}`。没有改仓库原S99board参考文件。
- 安装目录`{directory}`含original、monitor、bringup、control、run、boot；哈希在启用报告固定。最终重新启用后没有再重启，当前RX空闲、串口关闭、板卡仍通电；屏幕保留最后快照。**下次新启动会尝试自动初始化及显示，已不再是下方历史P42的“普通重启只走RF-only”。**
- 原生duration=0直到请求停止，外层有86400秒（24小时）终止后备；达到后备期限会停止。不能说已经验证24小时运行，也不能叫任意时长不间断。P42十分钟验收仍作为原生程序的较长实板证据。
- 默认固件/原厂DTBO/BOOT/base DTB未替换，board-mode仍rf；不启动TX、不热卸载ADC/PWM/显示、不在现有驱动下重配PL。新启动只允许一次PL和一次显式overlay。

## 实现与失败路径

1. `p43-persistent-guard.sh.in`先校验original，诊断`--check-rf`只转发只读路径。start验证新boot、/run tmpfs和本boot未尝试marker；相同boot再start会拒绝。选择合并配置前留持久pending目录并sync。
2. `p43_boot_templates.py`严格替换保留P41原有fresh/empty、唯一RF名字、idle、bin/DTBO/hash、软件33MHz时钟和RF参数门槛；source变化无法静默套用。没有删原来的安全门槛。P43不要求已安装S99恢复原guard，而是核验独立original备份，installed wrapper由主机另行SHA固定。
3. monitor与launcher复制到已确认的/run tmpfs，使用固定且本boot必须不存在的`/run/p42-000043`。UI/进度/日志仍由P42控制；只在出现首次running进度后才清pending并sync，意味着确实发生过首次分析/写屏，不是只有进程PID。
4. 如果初始化没到首次进度，pending保留；**下一个新boot**见pending会持久disabled并执行原厂guard，不在失败的同boot里移除overlay或重装PL。disabled也先经本boot重复执行门槛，不能拿它绕过热重配保护。此自动回退已做隔离shell测试，**尚未在实板故意制造失败再验证回退**。哈希损坏等更早失败会直接停止，需要显式恢复，不能声称任何故障都能自愈。
5. `control stop`要求marker为当前boot、PID合法且/proc命令行首项timeout、精确monitor路径匹配，才向它发SIGTERM；随后有界等待退出。主机还必须检查native summary、RF/内核与idle，不凭exit文件单独宣布资源释放。停止命令不卸驱动、不改RF参数。

## 证据与纠错

- `results/p43-preparation-20261022T030536Z/report.json`：13项真实POSIX shell在隔离目录执行，源哈希与输入快照固定，4份生成脚本sh -n通过。包含首次UI后清pending、wrapper持续保留、拒绝PID1并实际SIGTERM停止、旧boot/错hash/已有RF或overlay/非RAM/重复start拒绝、pending/disabled选择factory、probe失败/无首帧不重试。
- 第一轮fixture 5失败/8通过：/run挂载检查的路径常量在测试副本没有映射到临时根目录，错误地拦下了正常场景。失败XML及原test源保留为`results/p43-shell-attempt1-20261022.xml`与`results/p43-shell-attempt1-source.py`；仅修测试路径映射，真实脚本仍要求/run tmpfs。后续preparation增加实际停止/PID拒绝检查并13项通过，不使用早期通过XML代替最终固定源码结果。
- 每轮result目录含完整原始UART、startup-log、program最后两项JSON、精确installed文件和executed.py。hardware-trial.json只是对应新boot初始化依据，时钟LOCK/寄存器仍由独立脚本实读；不能当物理PCLK已测。
- 两轮最后显示32KiB原始IQ均已电脑归档，非整段无损录制。UI覆盖不等于ADC丢样；输入未知、数字功率不是dBm、近DC峰不代表已知目标，没有接入真实AI。

## 下一步

先正常关机并保存，再由用户真正断开新板电源约10秒并重新上电；保持旧板和接线/拨码不变，观察P43首次UI/持续计数及冷启动RF日志，不能用第三次软件重启替代。若0xFF/失败，保留UART/dmesg/pending/disabled和boot，不热重试。后续还需实板回退验证、更长运行、CDC/外部时序、已知源与AI联调。冷启动0xFF根因未关闭。
''',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P43恢复步骤（2026-10-22）

读[HW-033](../experiments/EXP-HW-033-persistent-startup.md)和TX-SOURCE-STATUS.json的p43_current。持久启用报告`{rel(args.enable_report)}`。P42/P41下方原guard/RF-only说明为历史。

1. COM8只能一个owner，DTR/RTS打开前false；先运行`experiments/p43_status.py --enable-report <当前启用报告>`只读识别真实boot、wrapper及全部安装文件SHA、pending/disabled、/run日志、进程和buffer/scan。不直接用旧p32的guard_matches=false判损坏，当前wrapper是预期值。
2. 若新boot已有running进度且RX active，不再加载PL或另起接收；以当前wrapper/monitor_SHA和boot固定会话后观察并用已核验`{directory}/control stop`停止，再读summary、RF、taint、idle。原生monitor与数据在/run/p42-000043，断电丢失；必须在下次boot前回传最后显示前缀。
3. 若出现pending/disabled或RF未齐，保存当前启动UART、p43日志和dmesg；不能热卸驱动或在当前绑定下重装PL。pending在下一个新boot才进入factory fallback；这一回退的实板故障演练尚待验证。
4. 禁用/回退应只替换下一次启动选择：先核对安装original SHA `{enable['original_guard_sha256']}`及当前wrapper SHA，再复制original到/etc/rcS.d/隐藏临时文件、chmod755、核验并原子rename成S99board、sync。**不要在当前合并绑定下执行original start**，不要把副本命名S99board.off留在S*目录。确认停机后新boot才回厂。
5. 两轮P43用P42通用归档工具前都在应用正常停止后暂时恢复original，报告startup_paused_for_archiving=true；若当前仍为wrapper，不能绕过归档工具的guard校验。先按精确SHA暂停下一次启动选择，再归档/NumPy；完成后通过新的P43启用/复核流程恢复。不要重放绑定旧boot的p43_finish_enable命令。
6. 下一步真断电验证需要人工切断电源。当前最后实读RX idle、串口关闭，**尚未关机**；需要先sync+正常poweroff并确认System halted，再断电约10秒。再次接电wrapper会自动尝试初始化/绘图；24小时后备期限不等于已验收24小时运行。

本轮检查点`{rel(out/'report.json')}`，父P42检查点完整保留。results被gitignore排除，备份不能只依赖Git。真正断电/冷启动、实板自动回退、0xFF根因、全流连续性/已知目标、真实AI仍未完成。
''',encoding='utf-8')
    if cold_verified:
        main_record=ROOT/record
        initial=main_record.read_text('utf-8')
        initial=initial.replace('这两轮是软件重启，不能叫冷启动验证。','以上两轮是软件重启；后续一次人工断电验证见文末，不混算。')
        initial=initial.split('## 下一步',1)[0]+'''## 下一步

本轮已做一次用户真正断电再接电，详情见下节。继续积累冷启动成功/失败对照、实板故障回退、更长运行及已知源/AI联调；仍保留CDC、外部时序、ADC连续性等开放项，0xFF根因未关闭。
'''
        initial=initial.split('\n',1)[0]+'\n\n**最终结论：两次软件重启及一次用户真实断电后的板端自动启动均通过，持久wrapper已再次启用。当前RX停止/idle、串口关闭，未再次关机。一次成功不代表0xFF根因关闭；以下先记录软件重启阶段，文末记录真实断电证据。**\n'+initial.split('\n',1)[1]
        main_record.write_text(initial,encoding='utf-8')
        with (ROOT/record).open('a',encoding='utf-8') as f:
            f.write(f'''\n## 后续真实断电验证（本节覆盖上文“冷启动待做”）\n\n用户按关机后断电约10秒再接电的要求回复“新板已断电并重新上电”；间隔未由电脑仪器测量。关机记录`results/p43-power-cycle-prepare-20261022T032530Z/report.json`确认System halted；用户事件`results/p43-human-power-cycle-20261022.json`。被动UART `results/p43-passive-power-on-20261022T032808Z/report.json`收到新内核及P43就绪marker，发送UART字节0；原始console中自登录root shell已出现，旧捕获器仅识别行尾login，所以login_observed=false不代表未启动，原报告不改写。\n\n冷启动boot `{cold['expected_boot']}`，主机未重启/装PL/起应用。自动运行{cold['native_summary']['elapsed_software_s']:.3f}秒，更新{cold['native_summary']['display_updates']}次后受控停止。`{rel(paths['current_cycle'])}`保留实际计数和操作；时钟寄存器/软件率一致`{rel(paths['current_clock'])}`，原始前缀/显存完整归档及NumPy复核`{rel(paths['current_review'])}`。本次冷启动未出现0xFF、taint0，停止后资源释放；**一次成功不能证明0xFF根因已根治**，也不替代更多冷启动或实板故障回退演练。当前最终wrapper再次启用，RX idle、串口关闭、未再次关机。上文等待断电/旧boot均为历史；当前以本节与p43_current为准。实体动态人工确认另行记录，本记录不凭显存回读冒充实物观察。\n''')
        with (ROOT/resume).open('a',encoding='utf-8') as f:
            f.write('\n## 本轮冷启动已完成\n\n用户真实断电后自动启动已验收一次，当前boot '+cold['expected_boot']+'；重新启用报告`'+rel(args.enable_report)+'`，独立idle状态`'+rel(args.status_report)+'`。当前未再次关机，之前等待人工断电的状态为历史。接下来继续积累冷启动样本/实板回退及已知源/AI验证；不能把一次成功写成根因关闭。\n')
    start=ROOT/'START-HERE.md';text=start.read_text('utf-8')
    intro='''# 从这里恢复项目工作

**当前入口：P43已完成两次软件重启验收，持久自启动已启用（2026-10-22）。** 先读[HW-033](docs/experiments/EXP-HW-033-persistent-startup.md)、[P43恢复步骤](docs/handoff/RESUME-P43-20261022.md)和TX-SOURCE-STATUS.json的p43_current。当前RX已停止、板仍通电、串口关闭；S99board现在是已固定SHA的P43 wrapper，下次新boot会尝试自动初始化和接收/频谱显示。真断电及故障回退实板验证仍待做，0xFF根因未根治。

**不要按下方P42/P41历史说明恢复原guard或判定“普通重启仍仅RF-only”。** 先用P43只读status核对当前wrapper/boot/latch；禁止热卸驱动或在已绑定时重配PL。下方“P43正在推进”及更早状态均保留为历史，以本段与p43_current为准。

'''
    if cold_verified:
        intro=intro.replace('两次软件重启验收','两次软件重启及一次人工断电验收').replace('真断电及故障回退实板验证仍待做','本轮一次真断电已验证，故障回退实板验证仍待做')
        intro=intro.replace('下方“P43正在推进”及更早状态均保留为历史','下方等待人工断电、P43正在推进及更早状态均为历史')
    start.write_text(intro+text.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    # Current source plus today's evidence; immutable parent ZIP is not nested.
    files=set()
    def add(f):
        if f.is_file() and f.name!='checkpoint.zip' and '__pycache__' not in f.parts:files.add(f.resolve())
    for d in ('board','configs','docs','embedded','experiments','fpga','host','src','tests'):
        for f in (ROOT/d).rglob('*'):add(f)
    for f in ROOT.iterdir():
        if f.suffix in ('.md','.json','.toml','.ini','.txt','.in','.cmd') or f.name in ('.gitignore','.gitattributes'):add(f)
    for d in (ROOT/'results').iterdir():
        if '20261022' in d.name or d.name=='p43-active.json':
            if d.is_dir():
                for f in d.rglob('*'):add(f)
            else:add(d)
    visited=set()
    def strings(v):
        if isinstance(v,str):yield v
        elif isinstance(v,dict):
            for x in v.values():yield from strings(x)
        elif isinstance(v,list):
            for x in v:yield from strings(x)
    while True:
        pending=[f for f in files if f.name=='report.json' and f not in visited]
        if not pending:break
        for f in pending:
            visited.add(f)
            try:v=read(f)
            except (ValueError,UnicodeError):continue
            for s in strings(v):
                if '\n' in s or len(s)>400:continue
                n=s.replace('\\','/')
                if not(n.startswith('results/') or n.lower().startswith(ROOT.as_posix().lower()+'/results/')):continue
                child=Path(s)
                if not child.is_absolute():child=ROOT/child
                child=child.resolve()
                if not child.is_relative_to(ROOT/'results') or not child.is_file():continue
                add(child)
                if child.name=='report.json':
                    for member in child.parent.rglob('*'):add(member)
    parent=ROOT/'results/p42-checkpoint-20261022T025223969800Z/report.json';parent_data=read(parent);parent_zip=ROOT/parent_data['archive']['path']
    if sha(parent_zip)!=parent_data['archive']['sha256']:raise ValueError('parent P42 ZIP changed')
    rows=[dict(path=rel(f),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(files)];write(out/'manifest.json',rows)
    zipped=out/'checkpoint.zip'
    with zipfile.ZipFile(zipped,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(zipped) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failure')
        for row in rows:
            raw=z.read(row['path'])
            if len(raw)!=row['bytes'] or hashlib.sha256(raw).hexdigest()!=row['sha256']:raise ValueError('member SHA failure')
    write(out/'report.json',dict(status='passed_P43_checkpoint_ZIP_CRC_and_all_member_SHA',files=len(rows),
        archive=dict(path=rel(zipped),bytes=zipped.stat().st_size,sha256=sha(zipped)),all_member_SHA_verified=True,
        parent_checkpoint=dict(path=rel(parent),sha256=sha(parent),archive_sha256=sha(parent_zip)),
        enable_report=rel(args.enable_report),status_report=rel(args.status_report),board_operations=False,
        persistent_autostart_enabled=True,board_shutdown_issued=False,true_power_cycle_verified=cold_verified))
    print(out);print('passed_P43_checkpoint_ZIP_CRC_and_all_member_SHA')
if __name__=='__main__':raise SystemExit(main())
