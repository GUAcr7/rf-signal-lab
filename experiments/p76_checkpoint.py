"""Save installed demo, verified stop/halt, and pending physical power-cycle."""
import argparse,hashlib,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',type=Path,required=True)
    ap.add_argument('--halt',type=Path,required=True);ap.add_argument('--listener',type=Path,required=True)
    ap.add_argument('--listener-session',type=int,required=True);a=ap.parse_args()
    v=read(a.review);h=read(a.halt);listener=read(a.listener)
    if (v['status']!='passed_P76_installed_10min_RF_history_FFT_pixels_cleanup'
        or not all(g['passed'] for g in v['gates']) or h['status']!='passed_P76_saved_data_System_halted'
        or not h['halt_observed'] or not h['serial_closed'] or sha(a.review)!=h['review_sha256']
        or listener['halt_sha256']!=sha(a.halt) or listener['status']!='P76_listening_zero_UART_writes'):
        raise ValueError('reviewed stop/halt and passive listener required')
    demo_path=ROOT/v['demo'];demo=read(demo_path)
    if sha(demo_path)!=v['demo_sha256']:raise ValueError('demo changed')
    boot_path=ROOT/demo['boot'];boot=read(boot_path)
    selection=ROOT/'configs/receiver-profile.json';select=read(selection)
    if sha(boot_path)!=demo['boot_sha256'] or select['report_sha256']!=sha(boot_path):raise ValueError('selected certificate changed')
    parent_path=ROOT/'results/p75-final-20261026T102330Z/report.json';parent=read(parent_path)
    if sha(ROOT/parent['checkpoint'])!=parent['checkpoint_sha256']:raise ValueError('parent recovery ZIP changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p76-final-%Y%m%dT%H%M%SZ');out.mkdir()
    experiment=ROOT/'docs/experiments/EXP-P76-persistent-demo-20261026.md'
    table='\n'.join('|'+g['source']+'|'+str(g['accepted'])+'/'+str(g['updates'])+'|'+str(g['correct'])+'|' for g in v['groups'])
    text=experiment.read_text(encoding='utf-8')
    marker='\n## 完整验收与等待物理断电'
    if marker in text:text=text.split(marker,1)[0]
    text+=f'''

## 完整验收与等待物理断电

独立复核：`{rel(a.review)}`。同一次init启动会话运行{v['elapsed_software_s']:.6f}秒、{v['display_updates']}次更新，最大更新间隔{v['maximum_update_interval_s']:.6f}秒；没有host RX start。完整历史与同块AI/指标、三类稳定评分、最后I/Q的FFT/RMS、实显存停止字形、指标清空及资源释放均通过。

| 源 | 已接受/稳定更新 | 其中正确 |
|---|---:|---:|
{table}

单音稳定窗口全部为UNSUPPORTED_TONE。三类本次均40/40次接受且正确，不因此删除P75的2次不确定或宣称通用准确率。实际物理LCD本轮人眼确认尚待，不能将显存核对冒充看到了屏幕。

新板已正常关机，串口出现System halted：`{rel(a.halt)}`。关机前再次逐文件核对板端8份原数据SHA与电脑归档相同，执行sync；poweroff意图后未发送TTY恢复字节。旧板保持通电且DDS零源。

只读启动监听已开启：`{rel(a.listener)}`，工具执行会话{a.listener_session}。它不向UART写字节，最多监听20分钟；其report、console和UART文件在捕获结束前为动态文件，未封进本次不可变恢复包。真实断电需用户只断新板电源、等约10秒再接，不用改接线/拨码/旧板。冷启动结果另存，禁止修改已被选择SHA绑定的P76普通重启证书。

阶段恢复包：`{rel(out/'checkpoint.zip')}`，唯一成员名、CRC、每成员SHA验证后作为恢复入口。当前仅普通重启与十分钟软件/RF通过，真实断电尚未确认。
'''
    experiment.write_text(text,encoding='utf-8')
    handoff=ROOT/'docs/handoff/RESUME-P76-20261026.md'
    handoff.write_text(f'''# P76恢复：新版已固化，十分钟通过，等待新板真实断电上电

## 已完成

- 当前选择为P76比赛演示版（P75八相位/原权重/3帧一致），普通重启后init自主启动通过，P70/P57回退完整保留。
- 同一自主会话{v['elapsed_software_s']:.3f}秒/{v['display_updates']}次更新；BPSK、QPSK、16QAM各40/40接受正确，单音17条全部拒判；完整历史、FFT/RMS、指标清空、实显存和停止清理通过。本次不新增独立准确率声明，P75不确定事实保留。
- [实验记录](../experiments/EXP-P76-persistent-demo-20261026.md)。启动证书`{rel(boot_path)}`；十分钟原始`{rel(demo_path)}`；复核`{rel(a.review)}`；正常关机`{rel(a.halt)}`。

## 现在状态

新板已System halted，仍物理接电；旧板未关机、收发停止、DDS零源。关机前数据已在电脑完整保存并与板端再次逐文件核SHA；不用依靠RAM保留。

旧板boot `{demo['after_TX']['boot_id']}`；新板关机前boot `{h['expected_boot']}`。电脑`configs/receiver-profile.json` SHA `{sha(selection)}`，指向已封存P76启动证书SHA `{sha(boot_path)}`。**不要改该证书或把冷启动结果合写进去，否则选择校验失败。**

被动监听`{rel(a.listener)}`已打开，只读无UART写入，工具执行会话ID `{a.listener_session}`。当前串口由监听独占，不要同时开SecureCRT/其他控制脚本。监听report/console/uart文件是动态的，不属于本次不可变包，捕获结束后另存和封包。若下次监听已超时，先读其report确认关闭，再在新监听准备好后让用户物理断电上电；不盲目重新发送reboot/poweroff。

## 收到用户物理操作答复后

1. 用户只断新TLZ7xH电源，等10秒后再接，保持原接线、拨码与旧P201不变。必须保留这条直接用户答复的实际内容，普通reboot不能替代。
2. 先等只读监听结束，检查新的kernel、PERSISTENT_MONITOR_READY和自动登录/登录；核uart.tx.bin为空及halt/report SHA，读取串口日志中新的ORIGINAL_BACKUP_VERIFIED boot，不能沿用`{h['expected_boot']}`。
3. 释放监听后才通过固定status重新读板，验证P76安装所有文件SHA、init boot marker/启动守卫唯一、正确WORK/monitor SHA、只有一个RX、AI CALIBRATION_REQUIRED且ready=false、指标无效、更新递增。不要启动第二个接收，不自动发射。
4. 将用户关于屏幕是否亮、数字是否更新的答复单独记录。软件更新/显存只能证明软件，不冒充实际屏幕人眼确认。若用户只答已上电，则屏幕人眼确认仍待。
5. 冷启动证据另存P77或独立目录并封包，更新START-HERE与权威状态。普通启动十分钟已通过，没有新问题时不反复重跑整套旧测试。

## 正常演示流程

每次开机后先认板，旧板断过电先prepare-source上传当前boot源；新板新会话采背景后发送已知单音校准，再切三种调制源，结束时stop且确认DDS零源。接收启动本身不会自动RF发射。旧板控制屏由队友完成，联调和最终整机彩排仍待；频谱仪分路对照放其后。

回退素材：P76目录`{boot['installed_directory']}`中previous-boot保存P70包装器；P76启动证书同目录的previous-selection.json保存电脑原P70选择。需要回退时先正常停止和备份，核旧P70 SHA后原子恢复板端S99board及电脑选择；只恢复一边会触发身份校验失败。当前不需要回退。

恢复包：`{rel(out/'checkpoint.zip')}`，增量父包P75。results被Git忽略，要直接读文件系统。
''',encoding='utf-8')
    acceptance=dict(status='saved_P76_installed_10min_passed_halted_waiting_actual_power_cycle',
        boot=rel(boot_path),boot_sha256=sha(boot_path),demo=rel(demo_path),demo_sha256=sha(demo_path),
        review=rel(a.review),review_sha256=sha(a.review),halt=rel(a.halt),halt_sha256=sha(a.halt),
        listener=rel(a.listener),listener_exec_session_id=a.listener_session,listener_is_mutable_not_archived=True,
        handoff=rel(handoff),experiment=rel(experiment),persistent_selected=True,RX_halted=True,
        RX_running=False,TX_stopped=True,true_power_cycle_verified=False,physical_LCD_confirmed=False,
        elapsed_software_s=v['elapsed_software_s'],display_updates=v['display_updates'],
        parent=rel(parent_path),checkpoint=rel(out/'checkpoint.zip'),receiver_selection_sha256=sha(selection))
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=rel(handoff),checkpoint=acceptance['checkpoint'],RX_halted=True,RX_running=False,TX_stopped=True,
        true_power_cycle_verified=False,persistent_selected=True,passive_listener=rel(a.listener),listener_exec_session_id=a.listener_session)
    write(ROOT/'results/p76-active.json',pointer);write(ROOT/'results/p70-active.json',dict(pointer,current_via='results/p76-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';d=read(source)
    d.update(status=pointer['status'],authoritative_current_field='p76_current',p76_current=pointer,
        updated=datetime.now(timezone.utc).isoformat(),updated_note='P76 installed; ordinary autonomous reboot and eleven-minute controlled RF passed; new board safely halted, passive listener waiting actual power cycle; old board zero source.',
        status_note='P76新版已固化，普通启动与十分钟通过，新板已正常关机，等用户真实断电上电；旧板保持零源。')
    write(source,d)
    start=ROOT/'START-HERE.md';old=start.read_text(encoding='utf-8')
    old='\n'.join(s for s in old.splitlines() if not s.startswith(('2026-10-26 **P76进行中**','2026-10-26 **P76最新**')))+'\n'
    prefix=f'''2026-10-26 **P76最新**：新版AI已保存为独立开机版本，普通重启自主启动及同一会话{v['elapsed_software_s']:.1f}秒/{v['display_updates']}次更新通过，三类各40/40接受正确。完整数据/FFT/显存/停止清空通过。P70/P57回退保留；没有新的独立准确率声明。**新板已System halted，等用户只对新板真实断电上电**；只读监听见`{rel(a.listener)}`，会话{a.listener_session}，捕获结束前不要占其串口。先读[P76恢复]({rel(handoff)})、[实验记录]({rel(experiment)})及`results/p76-active.json`。下方P75未持久安装等为历史。

'''
    start.write_text(old.replace('# 从这里恢复项目工作\n','# 从这里恢复项目工作\n\n'+prefix,1),encoding='utf-8')
    paths={start,source,handoff,experiment,selection,ROOT/'src/rfsig/receiver_profile.py',ROOT/'tests/test_receiver_profile_p76.py',
        ROOT/'results/p76-active.json',ROOT/'results/p70-active.json',ROOT/'results/p76-halt-active.json',
        ROOT/'results/p59-source-active.json',ROOT/'results/p76-controller-tests-20261026.xml',ROOT/'results/p76-startup-tests-20261026.xml',
        out/'acceptance.json',parent_path,a.listener.parent/'executed-listener.py'}
    paths.update((ROOT/'experiments').glob('p76_*.py'))
    dirs={demo_path.parent,a.halt.parent,ROOT/'results/p59-status-20261026T122325568962Z',ROOT/'results/p59-stop-20261026T122525877248Z',
          ROOT/'results/p59-source-off-20261026T122726241161Z',ROOT/'results/p59-p70-halt-20261026T122839039384Z'}
    dirs.update((ROOT/s['report']).parent for s in demo['steps'])
    dirs.update(p for p in (ROOT/'results').glob('p76-*') if p.is_dir() and p!=out and p!=a.listener.parent)
    for folder in dirs:paths.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='checkpoint.zip')
    paths={p.resolve() for p in paths}
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths)}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=rel(parent_path),parent_sha256=sha(parent_path),files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(paths):z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())) or z.testzip() is not None:raise ValueError('ZIP unique names/CRC failed')
        for n,item in manifest.items():
            raw=z.read(n)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ZIP SHA failed')
    write(out/'report.json',dict(status='passed_P76_recovery_unique_names_CRC_all_member_SHA',checkpoint=rel(archive),
        checkpoint_sha256=sha(archive),checkpoint_bytes=archive.stat().st_size,verified_members=len(manifest),
        acceptance=rel(out/'acceptance.json'),acceptance_sha256=sha(out/'acceptance.json'),true_power_cycle_verified=False))
    print(out);print('verified members: '+str(len(manifest)))


if __name__=='__main__':main()
