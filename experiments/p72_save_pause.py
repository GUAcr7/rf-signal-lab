"""Save the user-requested pause with a verified incremental recovery ZIP."""
import argparse,hashlib,zipfile
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--review',required=True,type=Path);a=ap.parse_args()
    v=read(a.review);trial=ROOT/v['trial'];t=read(trial)
    if (v['status']!='completed_P72_diagnostic_full_history_and_frozen_replay' or
        sha(trial)!=v['trial_sha256'] or not all(t.get(k) for k in ('RX_stopped','TX_stopped','serial_closed'))):
        raise ValueError('clean stopped byte archive and independent replay required before pause')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p72-final-%Y%m%dT%H%M%SZ');out.mkdir()
    handoff='docs/handoff/RESUME-P72-20261026.md';experiment='docs/experiments/EXP-P72-qam-capture-20261026.md'
    summary='；'.join(s['phase']+': '+str(s['classified'])+'/'+str(s['observations'])+'接受' for s in v['segments'] if s['source']!='tone')
    text=f'''# P72：午间保存，下午从实际不确定块抓取继续

用户要求本轮先保存，下午继续。记录与代码均已保存到电脑，不依赖板卡RAM保留。

## 当前已完成

- P71新版真正断电自主启动、超过十分钟接收显示验证保持有效，没有改动启动配置。
- P72同一次背景/单音校准后，分别进行了早期与校准年龄至少160秒的晚期16QAM限时发射；完整历史评分：{summary}。这是暴露seed2315的诊断，不是新的独立准确率。
- 原始试验：`{rel(trial)}`；逐块独立Python及冻结C复核：`{rel(a.review)}`。
- 保存全部{len(t['shots'])}组I/Q、AI与指标快照，完整AI/指标历史和少量显存；压缩包、分块、整体SHA与CRC均已验证。
- 实际保存为UNCERTAIN的I/Q块：{v['actual_uncertain_IQ_blocks']}；触发与保存状态不同：{v['trigger_state_mismatch_count']}次。电脑触发后保存的是后续更新，不能把触发时的异常当成已保存的异常样本。16QAM问题未解决，未调整模型、门限或三帧一致性策略。

## 停止时状态

两板收发均停止；三个原生TX guard均有清理和DDS零源读回；RX正常到时结束，线程join、buffer/context释放、DMA/scan空闲，串口关闭。仍通电，本轮未执行Linux关机。

旧板boot `{t['after_TX']['boot_id']}`；新板boot `{t['after_RX']['boot_id']}`。COM10/COM8仅为本次编号，下次重新核验USB/Linux身份。板端P72数据位于`{t['stage']}/data`，电脑已完整备份。

## 下午的顺序

1. 先读本文件和`results/p72-active.json`，运行`run-board-control.cmd status`重新确认状态；不要同时打开SecureCRT或多个占串口程序。
2. 若旧板断过电，先`prepare-source`重新上传RAM源并核SHA；新板重上电会自动启动P70接收，必须先按当前状态处理、使用新背景/单音，不能沿用旧boot校准或旧RAM源缓存。
3. 下一项是制作**仅RAM运行的诊断候选**，在原生程序已经判定UNCERTAIN的同一更新内自动保存该块I/Q/AI/指标，设数量和内存上限；同时保留预定正常块。不改冻结分类算法，不改持久启动。
4. 先用离线夹具验证事件抓取确实同源同块、不会重写快照或超预算；再做一次有限时RF采集。核对实际保存的状态/序号，逐块独立Python与冻结C复现后再讨论原因。
5. 只有实际证据支持时才建立修复候选；保留P70回退，按原覆盖率≥70%、条件正确率≥90%逐条件复测，背景/单音/失校准/削顶仍须拒判。P52独立成绩仍52/54。

用户没有要求继续新实验，午间不再发射或启动新接收任务。触屏仍由队友负责。

检查点：`{rel(out/'checkpoint.zip')}`，这是接在P71检查点之后的增量包，保留父恢复包；`results/`被Git忽略。
'''
    (ROOT/handoff).write_text(text,encoding='utf-8')
    (ROOT/experiment).write_text(f'''# P72：同一校准的早晚16QAM诊断与午间保存

日期：2026-10-26。用户在有限时试验进行时要求保存、下午继续；本轮只完成该试验的正常结束、归档与复核，没有新增后续RF实验。

协议在发射前写入执行代码与report：单音15秒、早期16QAM45秒、同一次校准至少160秒后晚期16QAM45秒；接收300秒。固定快照8/20/35秒，每段最多另加3次不确定触发；原生总限16，本轮15次。保持峰值256/−10dB、原衰减、RX手动0dB、Fs30.72MS/s、LO2450MHz及冻结P69程序。

完整稳定区间沿用首个观察后2秒、结束前3秒：{summary}。低覆盖率不阻断诊断归档，也没有被修改成通过。

试验：`{rel(trial)}`。复核：`{rel(a.review)}`。每个归档成员核SHA；每个快照与历史相同序号/AI相符，校准ready快照逐块验证Python前端功率、预测、策略和冻结C logits；两张实显存AI字形同源复核。实际异常I/Q数量{v['actual_uncertain_IQ_blocks']}。六次不确定轮询触发与后续保存状态存在时延问题，保留各自状态，不虚构异常数据已经抓到。

本轮结果只确认了采集/归档及复现链条，不证明频漂、定时、模型或硬件是根因。没有模型/参数/持久配置改动。下午先做同更新原生事件抓取，见[恢复清单](../handoff/RESUME-P72-20261026.md)。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text(encoding='utf-8')
    prefix=f'''2026-10-26 **P72午间已保存，下午继续**：同一校准的早晚16QAM诊断已正常停止、完整归档及Python/冻结C复核；{summary}。15组快照里实际UNCERTAIN为{v['actual_uncertain_IQ_blocks']}组，电脑触发有时延，下一项做同更新的板端事件抓取，不能宣称根因或修复完成。两板收发停、串口关、仍通电未关机，P70启动与模型不变。先读[P72恢复]({handoff})、[实验记录]({experiment})、`results/p72-active.json`。下方P71及更早描述保留历史。

'''
    start.write_text(old.replace('# 从这里恢复项目工作\n','# 从这里恢复项目工作\n\n'+prefix,1),encoding='utf-8')
    acceptance=dict(status='saved_P72_diagnostic_pause_AI_issue_open',review=rel(a.review),review_sha256=sha(a.review),
        trial=rel(trial),trial_sha256=sha(trial),handoff=handoff,experiment=experiment,TX_stopped=True,RX_stopped=True,
        RX_halted=False,powered_off=False,serial_closed=True,persistent_configuration_changed=False,
        actual_uncertain_IQ_blocks=v['actual_uncertain_IQ_blocks'],next_task='bounded native same-update uncertainty snapshots',
        checkpoint=rel(out/'checkpoint.zip'),parent='results/p71-final-20261026T041452Z/report.json')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
                 handoff=handoff,checkpoint=acceptance['checkpoint'],TX_stopped=True,RX_stopped=True,RX_halted=False,serial_closed=True)
    write(ROOT/'results/p72-active.json',pointer)
    write(ROOT/'results/p70-active.json',dict(pointer,current_via='results/p72-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';d=read(source)
    d.update(status=acceptance['status'],updated=datetime.now(timezone.utc).isoformat(),
             updated_note='P72 user-requested pause; complete RF diagnosis archived; uncertainty root cause open.',
             status_note='P71冷启动与十分钟显示已通过；P72诊断已保存，16QAM不确定问题仍待同块抓取定位。',
             authoritative_current_field='p72_current',p72_current=pointer);write(source,d)
    paths=[start,source,ROOT/handoff,ROOT/experiment,ROOT/'results/p72-active.json',ROOT/'results/p70-active.json',
           ROOT/'configs/receiver-profile.json',ROOT/'results/p59-source-active.json',out/'acceptance.json']
    paths.extend((ROOT/'experiments').glob('p72_*.py'))
    for directory in [trial.parent,*[p for p in (ROOT/'results').glob('p72-*') if p.is_dir() and p!=out]]:
        paths.extend(p for p in directory.rglob('*') if p.is_file() and '__pycache__' not in p.parts)
    paths=sorted(set(paths));manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in paths}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=acceptance['parent'],files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in paths:z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for n,item in manifest.items():
            raw=z.read(n)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:raise ValueError('ZIP member SHA differs')
    write(out/'report.json',dict(status='passed_P72_pause_increment_CRC_all_member_SHA',checkpoint=rel(archive),
                               checkpoint_bytes=archive.stat().st_size,checkpoint_sha256=sha(archive),verified_members=len(paths)))
    print(out)


if __name__=='__main__':main()
