"""Verify saved work, normally halt both idle boards and save a stop packet."""
from datetime import datetime,timezone
import hashlib,json,re,zipfile
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
from p37_review_archives import archive_bytes
from p40_factory_boot import ACTIVE


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()
def read(path):return json.loads(path.read_text('utf-8'))
def write(path,obj):path.write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(path):return path.resolve().relative_to(ROOT).as_posix()


def main():
    state_path=ROOT/'TX-SOURCE-STATUS.json';state=read(state_path)
    if state['authoritative_current_field']!='p41_current':raise ValueError('newer phase exists; do not use stale stop flow')
    current=state['p41_current'];checkpoint_path=ROOT/current['checkpoint_report'];checkpoint=read(checkpoint_path)
    if checkpoint['status']!='passed_P41_incremental_checkpoint_all_ZIP_CRC_and_SHA' or checkpoint['all_member_SHA_verified'] is not True:
        raise ValueError('verified current checkpoint required')
    archive=ROOT/checkpoint['archive']['path']
    if archive.stat().st_size!=checkpoint['archive']['bytes'] or sha(archive)!=checkpoint['archive']['sha256']:
        raise ValueError('current checkpoint bytes changed')
    post=read(ROOT/current['post_review'])
    if post['status']!='passed_autonomous_boot_post_clocks_archives_and_independent_NumPy':raise ValueError('accepted post review required')
    for stage in post['stages']:
        path=Path(stage['report'])
        if sha(path)!=stage['report_sha256']:raise ValueError('saved evidence changed')
        if stage['label'] in ('IQ_archive','framebuffer_archive'):archive_bytes(path)
    cold=read(ROOT/state['p40_current']['cold_preflight'])
    expected={'COM8':current['last_identified_boot'],'COM9':cold['boards']['COM9']['boot_id']}
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p41-session-stop-'+stamp);out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],boards={},user_requested_stop=True,PC_shutdown=False,
        expected_boots=expected,checkpoint=str(checkpoint_path),checkpoint_zip_SHA_verified=True,
        RF_or_firmware_changes=False,overlay_hot_unload=False,serial_closed=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    before=out/'before';before.mkdir()
    for name in ('START-HERE.md','TX-SOURCE-STATUS.json'):(before/name).write_bytes((ROOT/name).read_bytes())
    def save():write(out/'report.json',r)
    board=None;save()
    for port,identity in [('COM8','Zynq-Tronlong'),('COM9','Linux pzp201')]:
        item=dict(poweroff_issued=False,halt_observed=False);r['boards'][port]=item
        try:
            board=BoardConsole(port,r,save);audit=out/port;audit.mkdir();board.port=AuditPort(board.port,audit);board.shell()
            if identity not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!=expected[port]:raise ValueError('board identity changed; no shutdown')
            if board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('tainted kernel; preserve state')
            if re.search(ACTIVE+r'|/etc/p41-\d+T\d+Z/monitor',board.command('ps -ef' if port=='COM8' else 'ps')):raise ValueError('experiment still active')
            board.command('ir=/sys/bus/iio/devices')
            names=board.command('for d in $ir/iio:device*;do echo $d;cat $d/name;done')
            pairs=re.findall(r'(/sys/bus/iio/devices/iio:device\d+)\r?\n([^\r\n]+)',names)
            for path,name in pairs:
                if name not in ('cf-ad9361-lpc','cf-ad9361-dds-core-lpc'):continue
                board.command('p='+path)
                board.command('if test -f $p/buffer/enable;then cat $p/buffer/enable;fi')
                # Both devices have buffer/enable in this verified platform;
                # reject an unexpected layout instead of inferring idle.
                if board.value(path+'/buffer/enable')!='0':raise ValueError('IIO buffer active')
            if port=='COM8':
                guard=sha(ROOT/'board/boot/S99board')
                if guard not in board.command('sha256sum /etc/rcS.d/S99board'):raise ValueError('original guard not restored')
                if board.value('/etc/board-mode')!='rf':raise ValueError('mode changed')
                adc=[path for path,name in pairs if name=='cf-ad9361-lpc']
                if len(adc)!=1:raise ValueError('RX name ambiguous')
                board.command('cd '+adc[0])
                if any(board.value('scan_elements/in_voltage'+str(i)+'_en')!='0' for i in range(4)):raise ValueError('RX scan not released')
            item['idle_verified']=True;board.command('command -v poweroff');board.command('sync',timeout=20)
            item['sync_complete']=True;item['shutdown_intent_saved']=True;save()
            board.port.write(b'poweroff\r');item['poweroff_issued']=True;save()
            item['shutdown_console']=text=board.read(40,r'(?:System halted|system halted|Power down)')
            (audit/'shutdown.txt').write_text(text,encoding='utf-8')
            item['halt_observed']=bool(re.search(r'System halted|system halted|Power down',text))
            if not item['halt_observed']:raise ValueError('normal halt not observed')
            print(port+' normal halt confirmed',flush=True)
        except Exception as exc:item['error']=repr(exc)
        finally:
            if board:board.close();board=None
            save()
    r['serial_closed']=True
    both=all(r['boards'].get(port,{}).get('halt_observed') is True for port in expected)
    r['status']='both_boards_normal_halt_confirmed_work_saved' if both else 'stop_incomplete_check_individual_board_records'
    r['ended_utc']=datetime.now(timezone.utc).isoformat();save()
    state['session_stop']=dict(updated_utc=r['ended_utc'],user_requested_stop=True,record=rel(out/'report.json'),
        checkpoint=current['checkpoint_report'],both_board_halts_observed=both,
        board_shutdown_issued=all(item['poweroff_issued'] for item in r['boards'].values()),
        PC_shutdown=False,next_session_requires_new_boot_identity=True,
        original_guard_restored_before_stop=r['boards']['COM8'].get('idle_verified',False))
    current.update(session_stopped=both,poweroff_record=rel(out/'report.json'),
        runtime_state='both boards normally halted; physical power may now be disconnected' if both else 'see per-board stop record')
    write(state_path,state)
    stop_path=ROOT/'docs/handoff/STOP-P41-20261021.md'
    stop_path.write_text(f'''# P41停工保存与再次上电

保存日期：2026-10-21（北京时间）。关机记录：`{rel(out/'report.json')}`，status={r['status']}。两板是否都已正常halt：{both}。未关闭电脑，未更换默认固件/BOOT或热卸载驱动。

代码、实验记录、ARM程序、最后显示IQ/屏幕原始字节和NumPy复核已保存在电脑。主检查点：`{current['checkpoint_report']}`（1398文件，ZIP全部CRC/SHA核验）；P39/P38父检查点继续保留。results被gitignore排除，不能只靠Git备份。

下次接好原接线/拨码并上电后，在聊天中说“已上电，按START-HERE继续”。先重新认板、读取实际boot与guard；不要复制停机前boot。默认启动仍是厂家RF-only，不会永久自动启动P41显示；之前的一次性wrapper已恢复原S99board，必须按当前[恢复清单](RESUME-P41-20261021.md)继续。板RAM和运行PL不会因电脑保存而持久化。

完成范围：[HW-031](../experiments/EXP-HW-031-autonomous-once-startup.md)。剩余：长时间受控运行、有界日志/安全停止、可回退持久自启动及冷启动复测、0xFF根因、已知源质量与真实AI。若任一板halt未确认，先读本次各板error/console，不把本文当作两板都可断电的结论。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    banner=f'**最新停工保存：** `{rel(out/"report.json")}`；两板正常halt确认={both}，未关闭电脑。先读[停工/下次接线说明](docs/handoff/STOP-P41-20261021.md)，下方P41运行状态为停机前历史。\n\n'
    start.write_text('# 从这里恢复项目工作\n\n'+banner+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    # A small verified packet captures this shutdown and the updated pointers;
    # the large P41 source/evidence archive stays immutable.
    members=[Path(__file__),state_path,start,stop_path,out/'report.json',*list((out/'COM8').rglob('*')),*list((out/'COM9').rglob('*'))]
    members=[path for path in members if path.is_file()]
    manifest=[dict(path=rel(path),bytes=path.stat().st_size,sha256=sha(path)) for path in members]
    write(out/'manifest.json',manifest);packet=out/'stop-packet.zip'
    with zipfile.ZipFile(packet,'x',compression=zipfile.ZIP_DEFLATED) as z:
        for row in manifest:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','manifest.json')
    with zipfile.ZipFile(packet) as z:
        if z.testzip() is not None:raise ValueError('stop ZIP CRC failed')
        for row in manifest:
            if hashlib.sha256(z.read(row['path'])).hexdigest()!=row['sha256']:raise ValueError('stop ZIP member SHA failed')
    write(out/'packet-report.json',dict(status='stop_packet_all_CRC_and_SHA_verified',path=rel(packet),sha256=sha(packet),files=len(manifest)))
    print(out);print(r['status'])
    return 0 if both else 1


if __name__=='__main__':raise SystemExit(main())
