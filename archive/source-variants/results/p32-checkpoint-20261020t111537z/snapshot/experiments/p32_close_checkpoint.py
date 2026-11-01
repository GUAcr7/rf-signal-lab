"""Save current P32 handoff and a selected, hash-verified evidence snapshot. No UART."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import zipfile
from p32_session import ROOT


def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    end_path='results/p32-preflight-20261020T111006Z/report.json'
    verified_path='results/p32-delivery-check-20261020T111312Z/report.json'
    end=json.loads((ROOT/end_path).read_text('utf-8'))
    verified=json.loads((ROOT/verified_path).read_text('utf-8'))
    if end['status']!='both_boards_identified' or verified['status']!='scoped_delivery_checks_passed':
        raise RuntimeError('current end state and scoped delivery verification required')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p32-checkpoint-'+stamp);out.mkdir(exist_ok=False)
    report=dict(status='saving',created_utc=datetime.now(timezone.utc).isoformat(),
        board_operations=False,scope='Selected P32 source/evidence snapshot, not a complete portable Vivado/vendor/runtime backup',
        end_state=end_path,verification=verified_path,files=[])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    # Preserve prior entry/status before making the new session authoritative.
    for name in ['START-HERE.md','TX-SOURCE-STATUS.json']:
        shutil.copy2(ROOT/name,out/(name+'.before'))
    state=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8'))
    state['authoritative_current_field']='p32_current'
    state['historical_field_note']='p32_current describes the 2026-10-20 active session. session_stop and p31_current are historical 2026-10-19 records; do not interpret them as current power state.'
    state['p32_current']=dict(date_local='2026-10-20',timezone='Asia/Shanghai',
        current_state='both_boards_powered_on_idle_original_RF_restored',
        boards=end['boards'],TX_application_started=False,old_TX_RAM_tools_restored_by_this_turn=False,
        factory_guard_restored=True,hot_overlay_removal=False,
        DMA4K=dict(both_drivers_probe_verified=True,RX_finite_transfer_verified=True,TX_transfer_verified=False,
            original_factory_PL_and_clocks_only=True,merged_clock_hardware_verified=False),
        PWM2=dict(candidate_project='E:/p32-pwm2-105934/project/combined.xpr',BD_validation=True,
            new_synthesis_route=False,physical_hardware_verified=False),
        merged_candidate_source='fpga/integration/rf-display-p32-pwm2.dts',
        merged_bitstream_generated=False,merged_firmware_loaded=False,
        unresolved_CDC_critical=58,full_continuous_IQ_verified=False,real_AI_accepted=False,
        handoff='docs/handoff/RESUME-20261020.md',experiment='docs/experiments/EXP-HW-024-dma4k-pwm-and-cdc.md',
        evidence=dict(runtime='results/p32-dma4k-resume-20261020T105719Z/report.json',
            first_preapply_failure='results/p32-dma4k-runtime-20261020T105431Z/report.json',
            PWM2_project='results/p32-pwm2-project-20261020T105934Z/report.json',
            paired_overlay='results/p32-paired-overlay-20261020T110125Z/report.json',
            FIFO_MM='results/p32-fifo-mm-20261020T110537Z/report.json',
            CDC='results/p32-final-cdc-20261020T105847Z/report.json',
            final_end_state=end_path,delivery_check=verified_path),
        checkpoint=str((out/'report.json').relative_to(ROOT)).replace('\\','/'))
    (ROOT/'TX-SOURCE-STATUS.json').write_text(json.dumps(state,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    checkpoint_rel=(out/'report.json').relative_to(ROOT).as_posix()
    entry=f'''# 从这里恢复项目工作

**2026-10-20 P32已记录。两块板当前保持通电、空闲，新板已正常重启回原厂RF模式；不是上次停机状态。** 先读[本轮实验](docs/experiments/EXP-HW-024-dma4k-pwm-and-cdc.md)与[最新恢复清单](docs/handoff/RESUME-20261020.md)。

- 新启动4KiB DMA试验通过：两个DMA探测/绑定，RX16缓冲及65536字节稀疏回收通过；TX没有发射/传输验收。保留原厂PL/时钟，因此不等于合并100MHz DMA或合并整机通过。
- 原背光TTC0通道0与系统已注册计时源冲突；新副本同时改PL连线与设备树到通道2，并纠正VDMA五路时钟名称。新工程仅BD校验与设备树电脑应用通过，**未综合/布线/生成位流/上板**。
- 新副本：`E:\\p32-pwm2-105934\\project\\combined.xpr`，配套`fpga/integration/rf-display-p32-pwm2.dts`。原P30布线基线仍在`E:\\p30c-1019-174235`，其WNS/WHS不能直接套用于新副本。
- 实际RX FIFO/MM、TX MM/FIFO有限数字仿真通过：合计128描述符、4432拍、排空后重新启用。中途abort、独立复位和物理CDC待做。最终58条严重告警已按五组整理，**没有豁免或清零**。
- **继续禁止热卸载RF overlay或PWM驱动。** 旧内核生命周期缺陷未修复，冷启动间歇0xFF未根治。新启动单次应用、普通重启恢复的试验路径已跑通。
- 最后观测新板boot=`5cb0b3a6-c099-4df2-a526-86c41da9921a`，RX manual/0dB/2450MHz，buffer/scan关闭、tainted=0；旧板未观察到TX应用。本轮未恢复旧板RAM发射包，下一次发射前必须恢复或核验。
- [240项证据/结构核对]({verified_path})通过，它们不是240项硬件功能测试。完整连续IQ、真实AI、RF/屏幕/触摸并行与整机指标尚未验收。
- 下一步：实际端点abort/独立复位与CDC审查 → 外部IO时序 → PWM2新候选综合布线 → 新启动合并上板 → 已知RF信号/完整IQ/真实AI。
- [本轮证据快照]({checkpoint_rel})仅包含选定源码/证据。`results/`被gitignore排除；完整迁移还需E盘工程、供应原件和工具依赖。

当前机器状态以`TX-SOURCE-STATUS.json`的`p32_current`为准。`session_stop`和`p31_current`保留2026-10-19历史作用域。再次断电后必须重新认板/读boot_id，不运行绑定旧boot和RAM路径的一次性试验脚本。板卡停机需先正常关机再断电。
'''
    (ROOT/'START-HERE.md').write_text(entry,encoding='utf-8',newline='\n')
    doc=ROOT/'docs/experiments/EXP-HW-024-dma4k-pwm-and-cdc.md'
    text=doc.read_text('utf-8').split('\n## 交付前复核与保存\n')[0].replace('p32-preflight-20261020T110125Z','p32-preflight-20261020T111006Z')
    text+='''
## 交付前复核与保存

[240项证据/结构复核](../../results/p32-delivery-check-20261020T111312Z/report.json)通过，包含当前板卡身份与空闲状态、4KiB接收记录/字节SHA、原P30三个关键文件未变、配套新BD与设备树、ADI源码未变，以及仿真参数对实际XCI的核对。这是证据与结构核对数量，不是新增240项硬件功能测试。

重存BD时Vivado展开了307项原先隐含的PS7参数；逐项与原XCI比对一致，其他信号/接口/地址网络保持一致，仅背光网络改为WAVE2。BD校验仍保留未使用M04地址路径、SPI SSIN提示及部分传播元数据告警；未将BD通过说成所有告警解决。

交付审查又将一次性hold模板的恢复临时文件改成隐藏文件，避免中断遗留的`S*`文件在下次启动时被自动执行。[四项主机复测](../../results/p32-hold-checks-20261020T110933Z/pytest.stdout)通过，新增rename失败场景。板端原保护脚本早已恢复，本次没有重新安装这个更新模板；硬件成功试验使用的实际旧模板在运行证据中保留，不混淆版本。

最新入口为START-HERE与RESUME-20261020，机器状态为p32_current。两板保持通电空闲，没有新增发射或合并固件加载。
'''
    doc.write_text(text,encoding='utf-8',newline='\n')
    # Gather selected source plus this turn's complete small result directories.
    selected=[ROOT/'START-HERE.md',ROOT/'TX-SOURCE-STATUS.json',doc,
        ROOT/'docs/handoff/RESUME-20261020.md',ROOT/'board/boot/S99board',
        ROOT/'board/boot/p32-once-hold.sh.in',ROOT/'tests/test_p32_hold.py',
        ROOT/'fpga/tb/tb_p32_fifo_mm.sv',ROOT/'fpga/integration/rf-display-p32-pwm2.dts']
    selected+=list((ROOT/'experiments').glob('p32*.py'))
    for folder in (ROOT/'results').iterdir():
        if not folder.is_dir() or folder==out:continue
        if (folder.name.startswith('p32-') and not folder.name.startswith('p32-checkpoint-')) or any(
                folder.name.startswith(p) for p in ['p26-rx-profile-restore-20261020T','p27-smoke-20261020T','p31-sparse-archive-20261020T']):
            selected+=list(p for p in folder.rglob('*') if p.is_file())
    snapshot=out/'snapshot'
    for path in sorted(set(selected)):
        relative=path.relative_to(ROOT)
        target=snapshot/relative;target.parent.mkdir(parents=True,exist_ok=True)
        # CopyFile2 can reject these long Windows snapshot paths. Python's
        # file IO supports them; bytes/hash, not timestamps, define this archive.
        target.write_bytes(path.read_bytes())
        report['files'].append(dict(file=relative.as_posix(),sha256=sha(target),bytes=target.stat().st_size))
    external=Path('E:/p32-pwm2-105934')
    for relative in ['project/combined.xpr','project/combined.srcs/sources_1/bd/system/system.bd',
            'patch-pwm2.tcl','p32-pwm2-validated.tcl']:
        path=external/relative;name=Path('external/P32-project')/relative
        target=snapshot/name;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(path.read_bytes())
        report['files'].append(dict(file=name.as_posix(),original=str(path),sha256=sha(target),bytes=target.stat().st_size))
    # Validate live local Markdown targets; snapshot is intentionally not portable.
    links=[]
    for path in [ROOT/'START-HERE.md',doc,ROOT/'docs/handoff/RESUME-20261020.md']:
        for target in re.findall(r'\[[^\]]+\]\(([^)]+)\)',path.read_text('utf-8')):
            if '://' in target:continue
            target_path=(path.parent/target.split('#')[0]).resolve()
            links.append(dict(source=str(path.relative_to(ROOT)),target=target,exists=target_path.exists()))
    if not all(v['exists'] for v in links):raise RuntimeError('broken handoff link')
    report['local_links']=links
    manifest=out/'manifest.json';manifest.write_text(json.dumps(report['files'],indent=2)+'\n',encoding='utf-8')
    zipped=out/'p32-evidence.zip'
    with zipfile.ZipFile(zipped,'w',zipfile.ZIP_DEFLATED) as archive:
        for row in report['files']:archive.write(snapshot/row['file'],row['file'])
    with zipfile.ZipFile(zipped) as archive:
        if archive.testzip() is not None:raise RuntimeError('zip CRC failure')
        for row in report['files']:
            if hashlib.sha256(archive.read(row['file'])).hexdigest()!=row['sha256']:raise RuntimeError('zip entry hash mismatch')
    report.update(status='P32_selected_source_evidence_snapshot_and_handoff_verified',
        snapshot_files=len(report['files']),zip_sha256=sha(zipped),zip_bytes=zipped.stat().st_size,
        zip_crc_and_all_entry_hashes_verified=True,full_environment_backup=False)
    save()
    pointer=dict(report=str(out/'report.json'),zip=str(zipped),zip_sha256=report['zip_sha256'])
    (ROOT/'results/p32-checkpoint-active.json').write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status']);print('files',len(report['files']),'links',len(links))


if __name__=='__main__':main()
