"""Close the P79 evidence chain and verified incremental recovery ZIP; no IO."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys,zipfile,hashlib,re,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control
from rfsig.board_session import require_tx_off,require_rx_control

def read(p):return json.loads(Path(p).read_text('utf-8'))
def write(p,d):Path(p).write_text(json.dumps(d,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(p):return Path(p).resolve().relative_to(ROOT).as_posix()
def ref(p):return dict(report=rel(p),sha256=control.sha(p))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',type=Path,required=True);args=ap.parse_args()
    review=read(args.review)
    if review['status']!='passed_P79_screen_protocol_RF_AI_history_cleanup' or not all(x['passed'] for x in review['gates']):
        raise ValueError('Complete independent review required')
    archive_path=ROOT/review['archive'];archive=read(archive_path)
    if control.sha(archive_path)!=review['archive_sha256']:raise ValueError('Archive changed')
    require_tx_off(archive['after_TX']);require_rx_control(archive['after_RX'],running=False)
    profile,provenance=control.load_profile()
    if profile['schema']!='rfsig.receiver_profile.p76.v1':raise ValueError('Persistent receiver profile changed')
    xml=ET.parse(ROOT/'results/p79-final-tests-20261027.xml').getroot()
    suites=list(xml.iter('testsuite'))
    if any(int(s.get(k,'0')) for s in suites for k in ('failures','errors')):raise ValueError('Tests failed')
    tests=sum(int(s.get('tests','0')) for s in suites)
    manual_paths=[ROOT/'results/p78-screen-link-20261027T121704Z/report.json',
                  ROOT/'results/p78-screen-link-20261027T122101Z/report.json']
    buttons=set()
    for p in manual_paths:
        m=read(p)
        if not m['serial_closed'] or m['identity']['serial']!='D1273501630AD655':raise ValueError('Manual screen identity incomplete')
        raw=(p.parent/'UART/uart.rx.bin').read_bytes()
        buttons.update(x[0] for x in re.findall(rb'\x65\x00(.)\x00\xff\xff\xff',raw))
    if not set(range(1,10))<=buttons:raise ValueError('All nine actual manual keys not present')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');out=ROOT/'results'/('p79-final-'+stamp);out.mkdir()
    human=ROOT/'results/p79-human-feedback-20261027.json'
    write(human,dict(recorded_utc=datetime.now(timezone.utc).isoformat(),source='direct replies in this chat; original timestamps unspecified',
        user_reports=[
          '射频接法未变；屏仅接电脑','已点完，文字和时长正常变化','已重新点这三个键','三个状态均正确显示',
          '重新连接好了 继续','操作完成，收发和显示正常','已在 RUNNING 时点 STOP，已回 IDLE'],
        interpretation='Human reports retained separately. Raw evidence verifies nine keys and BPSK TX; later manual QPSK stop overlapped session end. No full human three-preset claim.'))
    record=dict(schema='rfsig.source_screen.integration.v1',status='passed_P79_computer_mediated_screen_protocol_RF_integration',
                created_utc=datetime.now(timezone.utc).isoformat(),review=ref(args.review),archive=ref(archive_path),
                screen_session=ref(ROOT/archive['screen_report']),human_feedback=ref(human),tests_passed=tests,
                groups=review['groups'],input_origin=review['input_origin'],manual_nine_keys_verified=True,
                manual_key_reports=[ref(p) for p in manual_paths],
                partial_manual_RF_session=ref(ROOT/'results/p79-screen-control-20261027T130156Z/report.json'),
                partial_manual_RX_archive=ref(ROOT/'results/p59-p79-session-archive-20261027T131158174564Z/report.json'),
                complete_human_three_preset_rehearsal=False,direct_P201_UART_verified=False,
                standalone_without_PC=False,teammate_final_HMI_TFT_received=False,
                RX_stopped=True,TX_stopped=True,serial_closed=True,boards_powered_not_shutdown=True,
                RX_boot=archive['after_RX']['boot_id'],TX_boot=archive['after_TX']['boot_id'],
                receiver_selection_sha256=control.sha(ROOT/'configs/receiver-profile.json'),
                receiver_profile_provenance=provenance,PL_changes=False,reboots_issued=0,
                persistent_board_files_changed=False,new_independent_AI_accuracy=False,
                USB_console_background_issue='reproduced without RF; mitigated by verified same-USB non-PTY network jobs; underlying cause not claimed fixed',
                parent_checkpoint=ref(ROOT/'results/p77-final-20261026T130128Z/report.json'),
                checkpoint=rel(out/'checkpoint.zip'),acceptance=rel(out/'acceptance.json'))
    write(out/'report.json',record)
    active=dict(status=record['status'],report=rel(out/'report.json'),report_sha256=control.sha(out/'report.json'),
                handoff='docs/handoff/RESUME-P79-20261027.md',checkpoint=record['checkpoint'],acceptance=record['acceptance'])
    write(ROOT/'results/p79-active.json',active)
    handoff='''# P79 当前恢复入口

本轮电脑中转的串口屏控制已通过协议自动回归和完整接收历史复核。人工九键与回显通过，人工 BPSK 发射通过；全人工三类彩排和发射中的人工 STOP 尚不作为已通过结论。

当前收发已停止、数字源已归零、串口及网络任务连接均释放，两板仍供电，未执行关机。实验数据和原始失败记录已归档到电脑。P76 接收持久版本和回退均未改变；旧板源包/控制仍在 RAM，重启后需重新准备。

先读 `results/p79-active.json`、本轮实验和 `docs/source-screen-control.md`。再次恢复先重新认板，旧板重启后先恢复冻结源包，再通过 `experiments/p79_bind_usb_network.py` 绑定同一 USB 串口/网络型号与 boot、公钥。不要使用旧 USB 交互控制台的后台任务原型，不把网络通道默认为其他板卡的替代连接。

新 RX 会话须新背景和参考单音。准备完成后用 `run-source-screen.cmd --rf-link-reviewed` 人工操作，只有原同轴与衰减连接保持时才用此参数；任何改接先复核新链路。启动界面不自动发射。新板自动接收仍最多 15 分钟，之后 RX STOPPED 正常。

本轮自动回归通过实屏 printh 回放既有按键协议，经过真实串口解析、guard 和 RF 链路，不能称作手指触摸或 click 事件测试。屏幕只通过 USB-TTL 接电脑；J19 物理串口、脱离电脑运行和旧板控制服务持久化仍待完成。后续优先取得队友最终 HMI/TFT 归档、补完整人工彩排，再推进独立直连。

完整恢复包是增量检查点，保留项目及 P77/P76 等父检查点。P76 启动证书不可改写；不要把本轮接收会话当作新冷启动验收。
'''
    (ROOT/'docs/handoff/RESUME-P79-20261027.md').write_text(handoff,encoding='utf-8')
    group_text='；'.join(x['signal']+' '+str(x['correct'])+'/'+str(x['stable_updates'])+' 稳定更新接受正确' for x in review['groups'])
    exp=ROOT/'docs/experiments/EXP-P79-source-screen-integration-20261027.md'
    with exp.open('a',encoding='utf-8') as f:
        f.write('\n## 本轮收尾结论\n\n自动协议回归、原生停止/到时清理、完整接收历史和同源 FFT/实显存已通过独立复核：'+group_text+'。本轮不是新的独立 AI 准确率。\n\n')
        f.write('人工阶段在 `results/p79-screen-control-20261027T130156Z/report.json` 保存为 partial：BPSK 实发到时完成；后来的 QPSK 操作碰到 420 秒会话截止，故不能把用户反馈转写为已抓到人工 STOP。该阶段完整 RX 已归档 `results/p59-p79-session-archive-20261027T131158174564Z/report.json`。\n\n')
        f.write('官方 click 指令已查证并实测，本 HMI 使用 click 不自动回传勾选的键值，记录 `results/p78-screen-link-20261027T131403Z/report.json`。随后无 RF 的 printh 帧回放通过 `results/p78-screen-link-20261027T131729Z/report.json`，自动收发回归明确标为 screen_generated_protocol_replay。没有修改 HMI，也没有把协议回放称为真实手指测试。\n\n')
        f.write('自动回归：`'+archive['screen_report']+'`；完整数据：`'+rel(archive_path)+'`；独立复核：`'+rel(args.review)+'`。相关 Python 测试 '+str(tests)+' 项通过。收尾时两板仍供电，收发停、DDS 零源、所有控制连接释放。最终检查点：`'+rel(out/'checkpoint.zip')+'`。\n')
    start=ROOT/'START-HERE.md';text=start.read_text('utf-8')
    a=text.index('2026-10-27 **P79');b=text.index('2026-10-26 **P77',a)
    note='2026-10-27 **P79最新**：串口屏九键/回显及电脑中转控制已适配；真实原生主动停止和到时清理、三类协议自动 RF 回归及完整接收历史复核通过。自动回归明确为实屏协议帧回放，未宣称完成全人工三类彩排。USB 控制台后台问题用已核同型号/boot/公钥的同 USB 非交互网络通道规避；不声称底层根因已修复。当前两板收发停、DDS 零源、控制连接释放，仍供电未关机，P76 持久版本不变。屏仍仅接电脑，J19/脱离电脑控制未验收，队友最终 HMI/TFT 待归档。先读[P79恢复](docs/handoff/RESUME-P79-20261027.md)、[实验记录](docs/experiments/EXP-P79-source-screen-integration-20261027.md)、[使用说明](docs/source-screen-control.md)及 results/p79-active.json。\n\n'
    start.write_text(text[:a]+note+text[b:],encoding='utf-8')
    state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(updated=record['created_utc'],status=record['status'],
        updated_note='P79 computer-mediated control and protocol RF regression verified; complete human rehearsal/independent board UART remain open.',
        status_note='P79 屏控软件和协议 RF 回归通过；收发已停、控制连接释放，仍供电。人工完整彩排和独立直连待完成。',
        authoritative_current_field='p79_current',p79_current=active)
    write(ROOT/'TX-SOURCE-STATUS.json',state)
    selected=set()
    for pattern in ('experiments/p78*.py','experiments/p79*.py','tests/test_source_screen*.py','tests/test_usb_network_p79.py'):
        selected.update(ROOT.glob(pattern))
    for name in ('START-HERE.md','TX-SOURCE-STATUS.json','results/p79-active.json','host/board_control.py','src/rfsig/board_session.py',
                 'src/rfsig/source_screen.py','src/rfsig/source_screen_regression.py','host/source_screen_link.py',
                 'host/source_screen_rf.py','host/p201_usb_network.py','board/source-job.sh','tests/native/check_source_job.py',
                 'configs/board-connections.json','configs/receiver-profile.json','requirements-screen-control.txt','run-source-screen.cmd',
                 'docs/source-screen-control.md','docs/experiments/EXP-P79-source-screen-integration-20261027.md',
                 'docs/handoff/RESUME-P79-20261027.md'):
        selected.add(ROOT/name)
    for p in (ROOT/'results').iterdir():
        if p==out:continue
        if p.name.startswith(('p78-','p79-')) or (p.name.startswith('p59-') and '20261027' in p.name):
            if p.is_dir():selected.update(x for x in p.rglob('*') if x.is_file())
            elif p.is_file():selected.add(p)
    selected.add(out/'report.json')
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=control.sha(p)) for p in sorted(selected)}
    write(out/'manifest.json',dict(schema='rfsig.incremental_checkpoint.v1',files=manifest,parent_checkpoint=record['parent_checkpoint']))
    with zipfile.ZipFile(out/'checkpoint.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(selected):z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(out/'checkpoint.zip') as z:
        if z.testzip() is not None or len(z.namelist())!=len(set(z.namelist())):raise ValueError('ZIP CRC/duplicate members')
        for name,m in manifest.items():
            data=z.read(name)
            if len(data)!=m['bytes'] or hashlib.sha256(data).hexdigest()!=m['sha256'] or control.sha(ROOT/name)!=m['sha256']:
                raise ValueError('ZIP/current bytes mismatch: '+name)
    write(out/'acceptance.json',dict(status='passed_P79_incremental_checkpoint_CRC_SHA_unique_members',
          zip_sha256=control.sha(out/'checkpoint.zip'),zip_bytes=(out/'checkpoint.zip').stat().st_size,
          files_verified=len(manifest),manifest_sha256=control.sha(out/'manifest.json'),report_sha256=control.sha(out/'report.json')))
    print(out,flush=True);print('passed_P79_saved_and_verified',flush=True)

if __name__=='__main__':main()
