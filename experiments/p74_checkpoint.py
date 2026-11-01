"""Seal P73 diagnostic evidence and P74 candidate; no board operations."""
import argparse, hashlib, zipfile
from datetime import datetime, timezone
from pathlib import Path
from p45_checkpoint import ROOT, read, write, sha, rel


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--arm',type=Path,required=True)
    a=ap.parse_args();arm=read(a.arm)
    if (arm['status']!='passed_P74_actual_ARM_parity_latency_RAM_only_no_RF'
        or not all(arm.get(k) for k in ('serial_closed','TX_stopped','RX_stopped'))):
        raise ValueError('clean stopped ARM result required')
    native_path=ROOT/arm['native'];native=read(native_path)
    if sha(native_path)!=arm['native_sha256']:raise ValueError('native report changed')
    offline_path=ROOT/native['offline'];offline=read(offline_path)
    if sha(offline_path)!=native['offline_sha256']:raise ValueError('offline report changed')
    for key,digest in native['inputs_sha256'].items():
        if sha(ROOT/key)!=digest:raise ValueError('P74 native inputs changed '+key)
    review_path=ROOT/offline['review'];review=read(review_path)
    if sha(review_path)!=offline['review_sha256']:raise ValueError('review changed')
    trial_path=ROOT/review['trial'];trial=read(trial_path)
    if sha(trial_path)!=review['trial_sha256']:raise ValueError('trial changed')
    if (review['actual_uncertain_IQ_blocks']!=6 or review['trigger_state_mismatch_count']!=0
        or not all(g['passed'] for g in review['gates'])
        or not all(trial.get(k) for k in ('RX_stopped','TX_stopped','serial_closed'))):
        raise ValueError('same-update reviewed, stopped evidence required')
    frozen_path=ROOT/'results/p52-export-20261024T043113Z/report.json';frozen=read(frozen_path)
    for item in frozen['frozen_inputs'].values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('original frozen input changed')
    dataset=ROOT/'results/p54-plan-20261024T042837Z/dataset/frames.npz'
    if sha(dataset)!='b5d9e6474e165936482563e28586f2813d46e4e52338d94af9ba56dca7108aeb':
        raise ValueError('validation data changed')
    profile=ROOT/'configs/receiver-profile.json'
    if sha(profile)!=review['receiver_configuration_sha256']:raise ValueError('production profile changed')
    parent_path=ROOT/'results/p72-final-20261026T043517Z/report.json';parent=read(parent_path)
    if sha(ROOT/parent['checkpoint'])!=parent['checkpoint_sha256']:raise ValueError('parent recovery ZIP changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p74-final-%Y%m%dT%H%M%SZ');out.mkdir()
    handoff=ROOT/'docs/handoff/RESUME-P74-20261026.md'
    experiment=ROOT/'docs/experiments/EXP-P74-phase-pool-20261026.md'
    handoff.write_text(f'''# P74恢复入口：实际异常已复现，候选通过离线/ARM，真实RF候选验收待做

2026-10-26下午已完成P73取证和P74候选检查。本文件及START-HERE.md为最新入口，下方旧P73“归档中”或P72“下一项同块抓取”均为历史。本次不是用户要求关机或暂停，现将阶段成果固化以便继续。

## 可以确认的结果

1. P73原生同更新抓到6块实际UNCERTAIN和6块正常I/Q；块号/AI/指标同源，Python/冻结C重放与实际ARM一致。完整300秒RX及3段有限时TX已结束并归档。原验证窗口早64/68、晚61/68接受且全部正确；其余仍不确定。
2. FP32保留同样6块不一致；幅度缩放不影响结果，纯相位旋转影响所有6块异常。已找到输入敏感性的证据，不能据此称硬件或全部频偏/定时问题已排除。
3. P74固定八相位logits均值、再三帧完全一致的候选：原验证54/54（原53/54），六异常块6/6恢复正确一致，六正常块保持正确。候选没有训练或真实标签输入，也未改变原策略门槛。
4. C/Python99帧逐帧一致；实际ARM每种算法15帧一致，三帧候选计算平均26.1683ms、最大26.2056ms。只计分类计算，不计采集/FIR/绘图。
5. 上述验证与事件为已暴露数据，**不是新的独立识别率**。原P52独立INT8成绩仍52/54，仅属于原算法。P74尚无新的独立RF验收，不宣称根治或稳定性已通过。

## 当前硬件/软件状态

- 旧板boot `{arm['after_TX']['boot_id']}`；新板boot `{arm['after_RX']['boot_id']}`。
- 收发均停止、RX DMA/scan空闲、TX DDS raw/scale均零，串口已关闭。板卡仍供电，未Linux halt，未执行断电。
- 新板仍选P70/P69持久配置，`configs/receiver-profile.json` SHA `{sha(profile)}`；原P57回退保留。**P74只是RAM回放程序，没有接入LCD、没有替换自动启动。**
- P73板端数据`{trial['stage']}/data`；P74回放`{arm['stage']}`。均为RAM，断电丢失不影响电脑已归档证据，但恢复时必须重上传。
- 本次COM10为P201 Linux USB控制台、COM8为TLZ7xH CH340；下次不假定编号或boot相同。旧板source-active缓存只对本boot有效。
- TJC旧板触屏仍交给队友，不重新占用这部分任务。

## 下一步按依赖执行

1. 运行固定入口status重新识别两板，重新确认源关闭/当前boot；若新板因重上电自动RX，按固定入口正常停止，不能创建第二个RX；旧板断过电必须prepare-source重新上传并核SHA，不沿用旧校准。
2. 从已验收P69/P73建立**仅RAM的P74接收候选**：只把分类帧的原infer调用换为已验证八相位汇总；权重、FIR、RF配置、指标、三帧一致性与所有拒判/停止逻辑保持。先编译/检查冻结策略等价、单一接收上下文、同源证据、停止与错误清理；不要热换PL或卸载ADC驱动。
3. 在新RF前写出冻结协议和候选SHA：用从未用于选此候选的新源seed，覆盖BPSK/QPSK/16QAM，以及同一次新背景/单音校准后的早/晚16QAM。沿用原功率、增益、衰减和接线；不得从预测标签反调IF/挑相位。时长和稳定评分窗口在发射前固定。
4. 每条件完整稳定历史统计覆盖率≥70%、条件正确率≥90%；单列背景/单音/失校准/削顶拒判与停止清空，保留失败、同更新异常I/Q及至少预定正常I/Q。测实际更新间隔/资源/显存，不能用26ms代替端到端证明。
5. 独立Python与同候选C复核。新协议如果失败，保留失败证据，修订候选后使用另外未暴露的测试；不悄悄重用失败组作独立成绩。
6. 全部门槛通过后再决定持久替换，保留P70回退并做一次相关启动/显示验收。无需反复重做无改动的整套旧实验。

## 关键证据

- P73原始试验：`{rel(trial_path)}`；独立重放：`{rel(review_path)}`；固定探查：`results/p73-probes-20261026T093809Z/report.json`。
- P74离线：`{rel(offline_path)}`；C99帧：`{rel(native_path)}`；实际ARM：`{rel(a.arm)}`。
- 实验记录：[P73](../experiments/EXP-P73-same-update-events-20261026.md)、[P74](../experiments/EXP-P74-phase-pool-20261026.md)。P74首次提示符解析失败也已归档，后续成功未改写该失败。
- 增量恢复包：`{rel(out/'checkpoint.zip')}`；接在P72检查点之后，保留父包，results被Git忽略。
''',encoding='utf-8')
    acceptance=dict(status='saved_P74_offline_native_ARM_candidate_passed_fresh_RF_pending',
        trial=rel(trial_path),trial_sha256=sha(trial_path),review=rel(review_path),review_sha256=sha(review_path),
        offline=rel(offline_path),offline_sha256=sha(offline_path),native=rel(native_path),native_sha256=sha(native_path),
        ARM=rel(a.arm),ARM_sha256=sha(a.arm),handoff=rel(handoff),experiment=rel(experiment),
        actual_uncertain_IQ_blocks=6,diagnostic_uncertain_blocks_improved=6,
        candidate_new_independent_accuracy=None,classification_fix_deployed=False,
        production_configuration_changed=False,TX_stopped=True,RX_stopped=True,RX_halted=False,
        powered_off=False,serial_closed=True,checkpoint=rel(out/'checkpoint.zip'),parent=rel(parent_path),
        next_task='RAM candidate integration; prospectively frozen fresh three-class and early/late RF regression')
    write(out/'acceptance.json',acceptance)
    pointer=dict(status=acceptance['status'],report=rel(out/'acceptance.json'),report_sha256=sha(out/'acceptance.json'),
        handoff=rel(handoff),checkpoint=acceptance['checkpoint'],TX_stopped=True,RX_stopped=True,
        RX_halted=False,serial_closed=True,classification_fix_deployed=False)
    write(ROOT/'results/p74-active.json',pointer)
    write(ROOT/'results/p73-active.json',dict(pointer,current_via='results/p74-active.json',
                                           P73_same_update_capture_and_replay_complete=True))
    write(ROOT/'results/p70-active.json',dict(pointer,current_via='results/p74-active.json'))
    source=ROOT/'TX-SOURCE-STATUS.json';d=read(source)
    d.update(status=acceptance['status'],updated=datetime.now(timezone.utc).isoformat(),
             updated_note='P73 actual uncertainty captured/replayed; P74 fixed-phase candidate validated offline/ARM; fresh RF pending; production unchanged.',
             status_note='P74候选离线/ARM通过，未替换P70启动；真实RF候选验收待做，收发停、串口关、仍通电。',
             authoritative_current_field='p74_current',p74_current=pointer)
    write(source,d)
    start=ROOT/'START-HERE.md';old=start.read_text(encoding='utf-8')
    # Replace only the superseded current WIP paragraph; preserve dated history.
    lines=old.splitlines();lines=[line for line in lines if not line.startswith(
        ('2026-10-26 **P73同块诊断进行中**','2026-10-26 **P74最新**'))]
    old='\n'.join(lines)+'\n'
    prefix=f'''2026-10-26 **P74最新**：P73已归档6块实际不确定及6块正常I/Q并同块复现；相位敏感性有实证，未宣称根治。固定八相位汇总候选在原验证54/54、六异常块6/6改善；C/Python99帧和实际ARM15帧/模式通过，三帧计算平均26.17ms。属于离线/保存数据候选验证，**未接入实时LCD、未改P70持久启动、不是新的独立准确率**。收发停、串口关、仍通电未关机。先读[P74恢复]({rel(handoff)})、[P74实验]({rel(experiment)})及`results/p74-active.json`；下一项RAM接收候选和预先冻结的新三类RF/早晚16QAM回归。下方P72及更早“未抓到异常”等为历史。

'''
    start.write_text(old.replace('# 从这里恢复项目工作\n','# 从这里恢复项目工作\n\n'+prefix,1),encoding='utf-8')
    paths={start,source,handoff,experiment,ROOT/'docs/experiments/EXP-P73-same-update-events-20261026.md',
           ROOT/'results/p73-active.json',ROOT/'results/p74-active.json',ROOT/'results/p70-active.json',
           profile,ROOT/'results/p59-source-active.json',out/'acceptance.json',frozen_path,dataset,parent_path}
    paths.update(ROOT/item['path'] for item in frozen['frozen_inputs'].values())
    for pattern in ('p73_*.py','p74_*.py'):paths.update((ROOT/'experiments').glob(pattern))
    for folder in ('arm_live_panel_p73','arm_live_panel_p74'):
        paths.update(p for p in (ROOT/'embedded'/folder).rglob('*') if p.is_file())
    # New evidence only; immutable prior evidence is retained through the parent chain.
    evidence_dirs={trial_path.parent,a.arm.parent}
    for pattern in ('p73-*','p74-*','p59-p74-*'):
        evidence_dirs.update(p for p in (ROOT/'results').glob(pattern) if p.is_dir() and p!=out)
    for name in ('p59-status-20261026T091559008655Z','p59-stop-20261026T091706020695Z',
                 'p59-prepare-source-20261026T091750691345Z','p59-source-off-20261026T092039235247Z',
                 'p59-prepare-source-20261026T092243804142Z'):
        evidence_dirs.add(ROOT/'results'/name)
    for folder in evidence_dirs:
        paths.update(p for p in folder.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='checkpoint.zip')
    # CLI arguments may be relative; normalize before de-duplication and packing.
    paths={p.resolve() for p in paths}
    manifest={rel(p):dict(bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(paths)}
    write(out/'manifest.json',dict(schema='rfsig.recovery_increment.v1',parent=rel(parent_path),
                                  parent_report_sha256=sha(parent_path),files=manifest))
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(paths):z.write(p,rel(p))
        z.write(out/'manifest.json',rel(out/'manifest.json'))
    with zipfile.ZipFile(archive) as z:
        if len(z.namelist())!=len(set(z.namelist())):raise ValueError('duplicate ZIP member names')
        if z.testzip() is not None:raise ValueError('ZIP CRC failed')
        for name,item in manifest.items():
            raw=z.read(name)
            if len(raw)!=item['bytes'] or hashlib.sha256(raw).hexdigest()!=item['sha256']:
                raise ValueError('ZIP SHA differs '+name)
    write(out/'report.json',dict(status='passed_P74_increment_CRC_and_all_member_SHA',
          checkpoint=rel(archive),checkpoint_sha256=sha(archive),checkpoint_bytes=archive.stat().st_size,
          verified_members=len(manifest),acceptance=rel(out/'acceptance.json'),
          acceptance_sha256=sha(out/'acceptance.json'),classification_fix_deployed=False))
    print(out);print('verified members: '+str(len(manifest)))


if __name__=='__main__':main()
