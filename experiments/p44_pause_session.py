"""Save an idle session handoff; no board shutdown, reboot or hardware writes."""
import hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT

def read(p):return json.loads(p.read_text('utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path);current=state['p44_current']
    status_path=ROOT/'results/p43-status-20261022T043056Z/report.json';status=read(status_path)
    checkpoint_path=ROOT/current['checkpoint'];checkpoint=read(checkpoint_path);archive=ROOT/checkpoint['archive']['path']
    if (checkpoint['status']!='passed_P44_checkpoint_ZIP_CRC_and_all_member_SHA'
        or sha(archive)!=checkpoint['archive']['sha256'] or archive.stat().st_size!=checkpoint['archive']['bytes']):raise ValueError('checkpoint changed')
    if (status['status']!='read_only_persistent_profile_state_collected' or status['boot_id']!=current['expected_boot']
        or status['taint']!='0' or status['RX_buffer']!='0' or status['RX_scans']!=['0']*4
        or status['native_process_observed'] or status['pending_present'] or status['disabled_present']
        or not status['serial_closed'] or not status['persistent_wrapper_selected']):raise ValueError('not confirmed idle')
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p44-session-save-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    before=out/'before';before.mkdir()
    for name in ('START-HERE.md','TX-SOURCE-STATUS.json'):(before/name).write_bytes((ROOT/name).read_bytes())
    record=dict(status='saved_idle_for_next_session_not_shutdown',saved_utc=now.isoformat(),
        user_requested_pause=True,board_shutdown_issued=False,board_halt_observed=False,board_operations=False,
        serial_closed=True,RX_idle=True,old_board_accessed=False,persistent_autostart_enabled=True,
        status_report=rel(status_path),status_report_sha256=sha(status_path),
        parent_checkpoint=rel(checkpoint_path),parent_checkpoint_sha256=sha(checkpoint_path),
        parent_archive_sha256=sha(archive),next_task='true_power_cycle_and_physical_display_after_600s')
    write(out/'report.json',record)
    current.update(session_paused=True,session_save=rel(out/'report.json'),RX_idle=True,serial_closed=True,board_shutdown_issued=False)
    current['reports']['status']=dict(path=rel(status_path),sha256=sha(status_path))
    state.update(authoritative_current_field='p44_current',updated=now.isoformat(),session_stop=record,
        updated_note='P44 work saved for next session; RX idle; no shutdown issued; next task true cold display verification')
    write(state_path,state);write(ROOT/'results/p44-active.json',current)
    notes=ROOT/'docs/handoff/STOP-P44-20261022.md'
    notes.write_text(f'''# P44停工保存与下次继续

用户要求先保存、下次继续。保存日期：2026-10-22（北京时间）。本轮只读状态`{rel(status_path)}`确认新板RX停止、buffer/scan均0、taint0、没有接收进程、没有pending/disabled；串口已关闭。**新板仍通电，未执行关机；本记录不能当作已可直接拔电的halt证明。** 旧P201本次未访问。

代码、实验记录、最后显示IQ/显存及复核结果已保存在电脑，主检查点`{rel(checkpoint_path)}`，1810文件，ZIP完整CRC/逐成员SHA此前已通过，本次重新核验ZIP SHA。此次交接增量保存`{rel(out/'report.json')}`及同目录保存包。results被gitignore排除，备份不能只依赖Git。

当前有效字段已统一为TX-SOURCE-STATUS.json的p44_current；修正遗留指向p41_current的入口，旧P41停机工具不能用于当前阶段。P43持久自动启动和P44防休眠策略均已保留。

下次说“继续，按START-HERE恢复”即可。若重新接电，先重新读取真实boot和文件哈希；已有接收进程时不重复启动、不装PL、不热卸驱动。首先正常关机后真正断电约10秒再接电，验证自动接收和实体屏在600秒后仍可见更新；修复后这项尚未做。具体步骤见[恢复清单](RESUME-P44-20261022.md)，完成范围见[HW-034](../experiments/EXP-HW-034-display-sleep-policy.md)。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    start.write_text('# 从这里恢复项目工作\n\n**最新停工保存（P44）：** 用户要求下次继续。先读[停工记录](docs/handoff/STOP-P44-20261022.md)和p44_current。接收停止、资源释放、串口关闭；**板卡仍通电，未执行关机。** 自动启动及防休眠设置已保存。下次首先做修复后的真正断电及十分钟以上实屏验证，不重放旧boot。\n\n'+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    members=[Path(__file__),ROOT/'experiments/p44_save_progress.py',state_path,start,notes,ROOT/current['resume'],
        ROOT/'results/p44-active.json',out/'report.json',status_path,*list(status_path.parent.rglob('*')),*list(before.rglob('*'))]
    members=sorted({p.resolve() for p in members if p.is_file()})
    manifest=[dict(path=rel(p),bytes=p.stat().st_size,sha256=sha(p)) for p in members];write(out/'manifest.json',manifest)
    packet=out/'save-packet.zip'
    with zipfile.ZipFile(packet,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for row in manifest:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','MANIFEST.json')
    with zipfile.ZipFile(packet) as z:
        if z.testzip() is not None:raise ValueError('packet CRC failure')
        for row in manifest:
            if hashlib.sha256(z.read(row['path'])).hexdigest()!=row['sha256']:raise ValueError('packet member SHA failure')
    write(out/'packet-report.json',dict(status='passed_save_packet_CRC_and_all_member_SHA',archive=rel(packet),sha256=sha(packet),
        files=len(manifest),parent_checkpoint=rel(checkpoint_path),board_shutdown_issued=False))
    print(out);print('passed_save_packet_CRC_and_all_member_SHA')
if __name__=='__main__':main()
