"""Seal prospective RAM RF milestone, raw evidence and exact recovery order."""
import argparse,hashlib,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()
    v=read(a.review);trial_path=ROOT/v['trial'];t=read(trial_path)
    if (v['status']!='passed_P75_prospective_RF_history_phase_replay_metrics_and_cleanup'
        or sha(trial_path)!=v['trial_sha256'] or not all(g['passed'] for g in v['gates'])
        or not all(t.get(k) for k in ('RX_stopped','TX_stopped','serial_closed'))):
        raise ValueError('complete reviewed prospective RF and clean stop required')
    build_path=ROOT/t['build'];b=read(build_path)
    if sha(build_path)!=t['build_sha256']:raise ValueError('build changed')
    for name,digest in b['inputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('build input changed '+name)
    profile=ROOT/'configs/receiver-profile.json'
    if sha(profile)!=v['receiver_configuration_sha256']:raise ValueError('production selection changed')
    parent_path=ROOT/'results/p74-final-20261026T095803Z/report.json';parent=read(parent_path)
    if sha(ROOT/parent['checkpoint'])!=parent['checkpoint_sha256']:raise ValueError('P74 recovery archive changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p75-final-%Y%m%dT%H%M%SZ');out.mkdir()
    rows=[x for x in v['segments'] if x['source']!='tone']
    table='\n'.join('|'+x['phase']+' / '+x['source']+'|'+str(x['classified'])+'/'+str(x['observations'])+'|'+format(x['coverage']*100,'.2f')+'%|'+str(x['correct'])+'/'+str(x['classified'])+'|' for x in rows)
    summary='；'.join(x['phase']+' '+str(x['correct'])+'/'+str(x['observations'])+'接受且正确' for x in rows)
    experiment=ROOT/'docs/experiments/EXP-P75-live-phase-pool-20261026.md'
    extra=f'''

## 完整归档、独立复核及结论

原始试验已正常到时、全部5段guard清理及DDS零源读回通过，RX线程join、buffer/context释放、scan/DMA空闲，RF配置与boot未改，串口关闭。归档的分块/整包SHA、gzip CRC和成员SHA已在传输及独立复核中检查。板端实际同更新事件{len(t['events'])}组、预定快照{len(t['shots'])}组，完整AI/指标历史均保留。

独立复核：`{rel(a.review)}`；build：`{rel(build_path)}`。完整稳定窗口评分如下，未以电脑轮询抽样代替完整历史：

| 阶段/源 | 已接受/总更新 | 接受覆盖率 | 已接受且正确 |
|---|---:|---:|---:|
{table}

单音窗口全部拒判，末段稳定背景{v['background_stable_observations']}条均为NO_USABLE_SIGNAL且不输出类别。原离线失校准/削顶/混合三帧等拒判检查单列于离线报告，没有将它们冒充实板刻意注入实验。全部条件达到原覆盖率≥70%、已接受条件正确率≥90%的预定标准。

同更新I/Q经Python完整前端/八相位推理及独立候选C逐帧复现；各快照指标与AI块号相符，限定ROI中心/带宽与独立Welch计算误差≤5Hz，失效和停止时数值清空；两张实际显存AI页脚按字形/数值核对。更新总数{v['display_updates']}，最大实际更新间隔{v['maximum_update_interval_s']:.6f}s；完整判定前端/CNN耗时统计`{v['end_to_end_AI_compute_ms']}`。软件更新间隔不等于连续ADC时间，ADC gaps仍unknown，不能据此宣称无丢样。

**P75候选通过本组新seed受控RF端到端验收；早期16QAM仍有不确定，未宣称完全消除或根治。** 这不是跨设备/未知信号的通用识别率，原P52的52/54仍仅属于原算法。P75没有持久安装、未替换P70启动，尚需另外未暴露的独立组验证，再决定持久部署与必要启动验收。

当前两板仍供电，未Linux halt；旧boot `{t['after_TX']['boot_id']}`，新boot `{t['after_RX']['boot_id']}`，RAM候选及源断电会丢，但电脑的原始数据/代码/恢复包已保存。阶段恢复包：`{rel(out/'checkpoint.zip')}`，父包为P74。
'''
    original=experiment.read_text(encoding='utf-8')
    if '\n## 完整归档、独立复核及结论' in original:
        original=original.split('\n## 完整归档、独立复核及结论',1)[0]
    experiment.write_text(original+extra,encoding='utf-8')
    handoff=ROOT/'docs/handoff/RESUME-P75-20261026.md'
    handoff.write_text(f'''# P75恢复：临时接收候选通过新seed RF回归，持久安装待决定

最新结果：{summary}。原始完整历史、同更新I/Q、Python/候选C、ROI数值、显存页脚和停止/清理全部复核通过。早期16QAM有少量不确定，不能声称完全消除。

## 文件入口

- 原始试验：`{rel(trial_path)}`；独立复核：`{rel(a.review)}`。
- 冻结协议/新源：`{t['plan']}`（seed2026102601）；构建：`{rel(build_path)}`；离线：`results/p75-offline-20261026T100607Z/report.json`。
- [实验记录](../experiments/EXP-P75-live-phase-pool-20261026.md)；[P74候选定义及验证](../experiments/EXP-P74-phase-pool-20261026.md)。
- 阶段恢复包：`{rel(out/'checkpoint.zip')}`，接在P74检查点后，保留父包。results被Git忽略，要直接读文件系统。

## 当前状态

- 两板收发停、DMA/scan空闲、旧板DDS raw/scale零源，串口释放；仍通电，未关机。
- 旧P201 boot `{t['after_TX']['boot_id']}`；新TLZ7xH boot `{t['after_RX']['boot_id']}`；COM10/COM8仅本次编号。
- 新板P75候选位于RAM `{t['stage']}`，360秒试验已正常结束，没有后台P75 RX或TX。屏幕可能保留停止画面。
- `configs/receiver-profile.json`仍指P70/P69，SHA `{sha(profile)}`；P57回退保留。下次上电自动启动原P70，不会自动启动本P75相位候选。
- 新源上传/缓存绑定当前旧板boot，`results/p59-source-active.json`指向P75新seed源包；默认prepare-source仍会恢复原seed2315。后续做新seed试验使用显式冻结计划及对应RAM上传工具，不混用。
- TJC旧板控制屏由队友负责；不修改其工程或重新分配任务。

## 后续按依赖执行

1. 先status重新识别两板和boot、源关闭/接收状态。若重新上电自动运行原P70，正常停止后再建唯一新RX；断电后重新上传RAM源和候选，重新采背景/单音，不复用校准token。
2. 固定当前P75算法和SHA，另设未暴露的源seed与独立采集会话，覆盖三类、每类多个完整块；按原独立总体≥90%、每类≥80%与C/Python/ARM逐帧一致验收，不将同一循环波形的数百次显示更新当作相互独立样本。P75的seed2026102601已暴露，不再用于挑参数后的新独立成绩。
3. 保留当前候选可行但早期16QAM仍有不确定的事实。若为进一步调优而使用P73/P75数据，这些数据划为开发/验证；改动后另留新测试组，保持3/3和质量门槛，不变成2/3投票或展示旧类别。
4. 独立组通过后可制作与P70并列的持久候选，保留P70/P57回退。验证普通启动的单一RX、校准/指标清空、实际显示更新，再做一次相关十分钟会话；涉及开机流程时才做必要的真实断电验收。没有改动的旧PL/屏驱动无需反复重做。
5. 主线演示仍需与队友的旧板控制屏整合，以及TX1功分/RSA3030对照；不是本P75已完成内容。

P75结论仅为新seed受控条件端到端回归通过；新候选通用未知拒识、绝对dBm、绝对RF频率校准、无丢样与新独立准确率均不从本轮推出。当前不需要用户重新接线或操作软件界面。
''',encoding='utf-8')
    acceptance=dict(status='passed_P75_new_seed_live_phase_candidate_RF_RAM_checkpoint',review=rel(a.review),review_sha256=sha(a.review),
        trial=rel(trial_path),trial_sha256=sha(trial_path),build=rel(build_path),build_sha256=sha(build_path),
        handoff=rel(handoff),experiment=rel(experiment),segments=v['segments'],
        candidate_live_RAM_verified=True,candidate_persistent_installed=False,uncertainty_completely_eliminated=False,
        independent_accuracy_newly_claimed=False,TX_stopped=True,RX_stopped=True,serial_closed=True,
        RX_halted=False,powered_off=False,parent=rel(parent_path),checkpoint=rel(out/'checkpoint.zip'),
        receiver_configuration_sha256=sha(profile),next_task='frozen separate independent sessions, then persistent profile decision')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=rel(handoff),checkpoint=acceptance['checkpoint'],TX_stopped=True,RX_stopped=True,serial_closed=True,
        RX_halted=False,candidate_persistent_installed=False)
    write(ROOT/'results/p75-active.json',pointer)
    write(ROOT/'results/p70-active.json',dict(pointer,current_via='results/p75-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';d=read(source)
    d.update(status=acceptance['status'],updated=datetime.now(timezone.utc).isoformat(),
             authoritative_current_field='p75_current',p75_current=pointer,
             updated_note='New seed prospective live RAM RF regression passed; early 16QAM uncertainty remains; P70 production unchanged; TX/RX stopped.',
             status_note='P75新seed真实RF回归通过，尚未持久替换P70；早期16QAM少量不确定仍保留，收发停、串口关、仍通电。')
    write(source,d)
    start=ROOT/'START-HERE.md';old=start.read_text(encoding='utf-8')
    old='\n'.join(line for line in old.splitlines() if not line.startswith(('2026-10-26 **P75进行中**','2026-10-26 **P75最新**')))+'\n'
    prefix=f'''2026-10-26 **P75最新**：固定八相位候选已接入仅RAM接收显示，并通过新seed2026102601的360秒真实RF/同次校准早晚回归：{summary}；单音和背景拒判、I/Q/AI/ROI/显存及停止清理通过。早期16QAM仍有不确定，未宣称根治或新的通用独立识别率。**未改P70持久启动**，下次上电仍运行原P70。收发停、串口关、仍通电未关机。先读[P75恢复]({rel(handoff)})、[P75实验]({rel(experiment)})及`results/p75-active.json`。下一项独立未暴露组验证及持久候选决策；下方P74“尚未实时接入”为历史。

'''
    start.write_text(old.replace('# 从这里恢复项目工作\n','# 从这里恢复项目工作\n\n'+prefix,1),encoding='utf-8')
    paths={start,source,handoff,experiment,ROOT/'docs/experiments/EXP-P73-same-update-events-20261026.md',profile,ROOT/'results/p75-active.json',ROOT/'results/p70-active.json',
           ROOT/'results/p59-source-active.json',ROOT/'results/p68-link-20261026.json',out/'acceptance.json',parent_path}
    paths.update((ROOT/'experiments').glob('p75_*.py'))
    dirs={trial_path.parent,(ROOT/t['source_upload']).parent,ROOT/'results/p59-status-20261026T095958189123Z'}
    dirs.update(p for p in (ROOT/'results').glob('p75-*') if p.is_dir() and p!=out)
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
        for name,item in manifest.items():
            raw=z.read(name)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ZIP member SHA failed')
    write(out/'report.json',dict(status='passed_P75_recovery_unique_names_CRC_all_member_SHA',checkpoint=rel(archive),
        checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),verified_members=len(manifest),
        acceptance=rel(out/'acceptance.json'),acceptance_sha256=sha(out/'acceptance.json')))
    print(out);print('verified members: '+str(len(manifest)))


if __name__=='__main__':main()
