"""Save the validated latency improvement and incremental recovery checkpoint."""
from pathlib import Path
from datetime import datetime,timezone
import argparse,json,sys,zipfile,hashlib,xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'host'),str(ROOT/'src'),str(ROOT/'experiments')]
import board_control as control
from rfsig.board_session import require_tx_off,require_rx_control

def read(p):return json.loads(Path(p).read_text('utf-8'))
def rel(p):return Path(p).resolve().relative_to(ROOT).as_posix()
def write(p,data):Path(p).write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def ref(p):return dict(report=rel(p),sha256=control.sha(p))

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',type=Path,required=True);args=ap.parse_args()
    review=read(args.review)
    if review['status']!='passed_P80_button_latency_and_full_RF_regression' or not all(g['passed'] for g in review['gates']):
        raise ValueError('Passed latency and RF review required')
    rf_path=ROOT/review['RF_review'];rf=read(rf_path)
    if control.sha(rf_path)!=review['RF_review_sha256']:raise ValueError('RF review changed')
    archive_path=ROOT/rf['archive'];archive=read(archive_path)
    if control.sha(archive_path)!=rf['archive_sha256']:raise ValueError('Archive changed')
    require_tx_off(archive['after_TX']);require_rx_control(archive['after_RX'],running=False)
    profile,_=control.load_profile()
    if profile['schema']!='rfsig.receiver_profile.p76.v1':raise ValueError('Receiver persistent profile changed')
    tests=ET.parse(ROOT/'results/p80-tests-final-20261027.xml').getroot()
    suites=list(tests.iter('testsuite'))
    if any(int(s.get(k,'0')) for s in suites for k in ('failures','errors')):raise ValueError('Tests failed')
    count=sum(int(s.get('tests','0')) for s in suites)
    parent=ROOT/'results/p79-final-20261027T133028Z/report.json'
    old_manifest=read(parent.with_name('manifest.json'))['files']
    wrapper=ROOT/'run-source-screen.cmd'
    if control.sha(wrapper)!=old_manifest['run-source-screen.cmd']['sha256']:
        raise ValueError('Manual entry changed since P79; review before replacing')
    original=wrapper.read_bytes()
    text=wrapper.read_text('utf-8');needle='--required-signals bpsk qpsk qam16'
    if text.count(needle)!=1 or '--fast-control' in text:raise ValueError('Unexpected manual wrapper')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p80-final-%Y%m%dT%H%M%SZ');out.mkdir()
    (out/'run-source-screen-p79.cmd').write_bytes(original)
    wrapper.write_text(text.replace(needle,needle+' --fast-control'),encoding='utf-8')
    record=dict(schema='rfsig.source_screen.latency_release.v1',status='passed_P80_fast_screen_control_saved',
                created_utc=datetime.now(timezone.utc).isoformat(),review=ref(args.review),RF_review=ref(rf_path),archive=ref(archive_path),
                timings=review['summary'],RF_groups=rf['groups'],tests_passed=count,entry='run-source-screen.cmd',
                rollback='omit --fast-control when invoking host/source_screen_rf.py; original path retained',
                parent_checkpoint=ref(parent),receiver_selection_sha256=control.sha(ROOT/'configs/receiver-profile.json'),
                RX_stopped=True,TX_stopped=True,serial_closed=True,boards_powered_not_shutdown=True,
                input_origin=review['input_origin'],human_latency_rehearsal=False,direct_P201_UART_verified=False,
                PL_changes=False,persistent_board_files_changed=False,new_independent_AI_accuracy=False,
                checkpoint=rel(out/'checkpoint.zip'),acceptance=rel(out/'acceptance.json'))
    write(out/'report.json',record)
    comparison=ROOT/'results/p80-snapshot-compare-20261027T135103Z/report.json'
    detail='\n'.join('- '+name+': '+format(row['old_median_s'],'.3f')+' s → '+format(row['new_median_s'],'.3f')+' s（'+str(row['samples'])+' 次）'
                     for name,row in review['summary'].items())
    exp='''# P80 发送屏按钮响应优化

日期 2026-10-27。先测 P79 原始日志：屏幕自身回显为毫秒级，APPLY/START 的等待来自重复整机诊断、每次串口唤醒固定等候，以及逐项远程命令。

## 修改及保留的检查

新 `PromptConsole` 遇到完整 root 提示即结束等待，仍核实际 Linux 身份。RX 的完整身份、boot 前后、RF、DMA/扫描、七份配置文件 SHA、启动脚本 SHA、进程完整 argv、校准/进度及原来的 160 行内核日志合成一次只读快照，使用 NUL 字段边界与 gzip/base64 传输。缺字段、重复字段、boot 改变、SHA/RF/内核错误与截断均拒绝。临时 shell helper 仅在 RAM，使用前核实际 SHA。

同一动作内部复用由本进程独占的连接，动作结束或异常必关闭；APPLY 和 START 之间不缓存授权。每次完整 inspect 仍重新读取全部检查值。进度以两个实际读取证明推进，等待与其他读取重叠，没有取消进度检查。原 guard、限时、停止/清理回执、波形 SHA、接收 AI 和 P76 固件均保持不变。

初次只读试验误用了 P201 的 uudecode 上传器；新板没有该命令，检查在发送内容前拒绝，RF=0。失败报告 `results/p80-snapshot-compare-20261027T134421Z/report.json` 保留；改用既有 TLZ7xH base64 上传器。后续只读旧/新完整字段比较通过。为减少短命子进程，字段由逐项 base64 改为 NUL 定界后整体压缩，仍保留显式完成字段和严格字段集合。

## 实测结果

本次与 P79 相同协议回放流程，各有 4 次 APPLY、4 次 START 和 1 次发射中 STOP。下列为收到协议帧至实屏目标状态读回的中位数，不包含人手按压时间，也不代表 ADC 时间。

'''+detail+'''

首次连接的 helper 部署和完整启动检查在进入 IDLE 前完成，以上不把该初始化说成按键耗时。时延标准在 RF 回归前写于 `results/p80-plan-20261027.json`，没有事后放宽。

三类实际 RF 稳定窗口均通过原有覆盖率≥70%、条件正确率≥90%要求；完整 AI/指标历史、同源 FFT/RMS、停止显存、DMA/DDS 归零及资源释放均通过。输入明确为实屏 printh 协议回放，不是新的全人工彩排或独立 AI 准确率。

'''
    exp+='对照：`'+rel(comparison)+'`；时延复核：`'+rel(args.review)+'`；RF 复核：`'+rel(rf_path)+'`；完整数据：`'+rel(archive_path)+'`。相关 Python 测试 '+str(count)+' 项通过。\n\n'
    exp+='人工入口已加 `--fast-control`，原路径保留，去掉该参数即可回退。收尾时两板收发停止、数字零源、控制连接释放，仍供电未关机。没有持久板卡启动修改。\n'
    (ROOT/'docs/experiments/EXP-P80-screen-latency-20261027.md').write_text(exp,encoding='utf-8')
    handoff='''# P80 按钮提速恢复入口

先读本轮 `docs/experiments/EXP-P80-screen-latency-20261027.md` 和 `results/p80-active.json`。快速模式已通过完整字段对照、真实 RF/AI/停止回归和时延门槛，人工手感与完整彩排还待确认。

当前收发均停、DDS 数字零源、全部控制连接已关闭，两板仍供电，未执行关机。数据及原始失败日志已保存。P76 接收持久版本/回退未改变；旧板重启后仍需恢复 RAM 源包，并重新绑定同一 USB 网络身份。

恢复准备沿用 P79：重新识别设备和 boot → TX 空闲/零源 → 必要时 prepare-source → 串口与 USB 网络同型号/同 boot/公钥绑定 → 新 RX、新背景和参考单音 → 人工入口 `run-source-screen.cmd --rf-link-reviewed`。此入口现在默认带 `--fast-control`；启动时先 CHECKING 完成一次完整检查，再显示 IDLE，按钮本身不自动发射。

原有身份、RF、SHA、内核及清理检查均保留，不能为了再提速删掉。若快速路径失败，不自动跳过校验；显式去掉 `--fast-control` 可恢复原控制路径。本次临时 RX 读取 helper 断电后丢失，下次在进入 IDLE 前自动上传并核 SHA，不需要改写屏幕或固件。

下一步先做一次人工手感及完整整机彩排，取得队友最终 HMI/TFT 归档；随后核验旧板独立 UART 的物理回环、屏幕直连及控制服务固化/上电恢复。屏仍接电脑，脱离电脑的独立控制尚未验收。新 RX 仍有 15 分钟期限，新会话须重新背景/单音校准。

本检查点为 P79 后的增量包，保留 P79 及父检查点。不要把本轮人工启动的 RX 当作新冷启动验收。
'''
    (ROOT/'docs/handoff/RESUME-P80-20261027.md').write_text(handoff,encoding='utf-8')
    guide=ROOT/'docs/source-screen-control.md'
    with guide.open('a',encoding='utf-8') as f:
        f.write('\n## P80 按钮提速更新\n\n人工入口现默认使用 --fast-control。收到按键帧后，本次协议回归的 APPLY/START/STOP 目标状态等待分别约 3.5/5.3/2.6 秒，原来约 9.8/18.5/6.4 秒。首次连接先完成完整检查和 RAM helper 部署，进入 IDLE 后再操作。检查没有取消；去掉该参数可显式回退原版。详细记录和恢复方法见 P80 实验及恢复清单。\n')
    active=dict(status=record['status'],report=rel(out/'report.json'),report_sha256=control.sha(out/'report.json'),
                handoff='docs/handoff/RESUME-P80-20261027.md',checkpoint=record['checkpoint'],acceptance=record['acceptance'])
    write(ROOT/'results/p80-active.json',active)
    start=ROOT/'START-HERE.md';text=start.read_text('utf-8')
    note='2026-10-27 **P80最新**：按钮等待已优化，协议实测 APPLY 约 9.8→3.5 秒、START 18.5→5.3 秒、STOP 6.4→2.6 秒。完整字段对照及三类真实 RF/AI/清理复核通过，人工入口默认带 --fast-control，原控制路径保留；未放松校验、未改接收固件。当前两板收发停、数字零源、连接释放，仍供电未关机。先读[P80恢复](docs/handoff/RESUME-P80-20261027.md)、[实验](docs/experiments/EXP-P80-screen-latency-20261027.md)和 results/p80-active.json。人工手感/整套彩排、旧板独立 UART/屏控固化仍待完成。下方 P79 为历史。\n\n'
    start.write_text(text.replace('# 从这里恢复项目工作\n\n','# 从这里恢复项目工作\n\n'+note,1),encoding='utf-8')
    state=read(ROOT/'TX-SOURCE-STATUS.json');state.update(updated=record['created_utc'],status=record['status'],
        updated_note='P80 latency reduced with complete validation retained; RF/history/cleanup pass, controllers stopped.',
        status_note='P80 按钮提速通过，收发已停、连接释放；独立直连和人工彩排待完成。',authoritative_current_field='p80_current',p80_current=active)
    write(ROOT/'TX-SOURCE-STATUS.json',state)
    selected={out/'report.json',out/'run-source-screen-p79.cmd'}
    for pattern in ('experiments/p80*.py','tests/test_fast_panel_p80.py'):
        selected.update(ROOT.glob(pattern))
    for name in ('host/source_screen_rf.py','host/fast_panel_control.py','board/rx-control-snapshot.sh',
                 'experiments/p79_cancel_guard_trial.py','run-source-screen.cmd','START-HERE.md','TX-SOURCE-STATUS.json',
                 'results/p80-active.json','docs/source-screen-control.md','docs/experiments/EXP-P80-screen-latency-20261027.md',
                 'docs/handoff/RESUME-P80-20261027.md'):
        selected.add(ROOT/name)
    for p in (ROOT/'results').iterdir():
        if p==out:continue
        if p.name.startswith(('p80-','p59-p80-')):
            selected.update(x for x in p.rglob('*') if x.is_file()) if p.is_dir() else selected.add(p)
    for folder in (args.review.parent,rf_path.parent,archive_path.parent):selected.update(p for p in folder.rglob('*') if p.is_file())
    prep=ROOT/'results/p79-prepare-session-20261027T135435Z/report.json'
    selected.update(p for p in prep.parent.rglob('*') if p.is_file())
    for step in read(prep)['steps']:selected.update(p for p in (ROOT/step['report']).parent.rglob('*') if p.is_file())
    pilot=ROOT/'results/p79-cancel-trial-20261027T135648Z/report.json'
    selected.update(p for p in pilot.parent.rglob('*') if p.is_file())
    selected={p.resolve() for p in selected}
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=control.sha(p)) for p in sorted(selected)}
    write(out/'manifest.json',dict(schema='rfsig.incremental_checkpoint.v1',files=manifest,parent_checkpoint=record['parent_checkpoint']))
    with zipfile.ZipFile(out/'checkpoint.zip','w',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(selected):z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(out/'checkpoint.zip') as z:
        if z.testzip() or len(z.namelist())!=len(set(z.namelist())):raise ValueError('ZIP CRC/duplicate failed')
        for name,m in manifest.items():
            payload=z.read(name)
            if len(payload)!=m['bytes'] or hashlib.sha256(payload).hexdigest()!=m['sha256'] or control.sha(ROOT/name)!=m['sha256']:
                raise ValueError('ZIP/current SHA failed: '+name)
    write(out/'acceptance.json',dict(status='passed_P80_incremental_checkpoint_CRC_SHA',zip_bytes=(out/'checkpoint.zip').stat().st_size,
                                   zip_sha256=control.sha(out/'checkpoint.zip'),files_verified=len(manifest)))
    print(out,flush=True);print('passed_P80_saved_and_verified',flush=True)

if __name__=='__main__':main()
