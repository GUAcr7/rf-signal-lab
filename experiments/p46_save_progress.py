"""Seal known-source results and restore a concise, unambiguous resume entry.

This host-only operation checks archived IQ and the final board status evidence.
It never opens a serial port or claims a new physical LCD observation.
"""
import argparse
from datetime import datetime,timezone
import json
from pathlib import Path
from p32_session import ROOT
from p45_checkpoint import checkpoint,read,write,sha,rel
from p37_review_archives import archive_bytes
from p36_fb_snapshot_run import accepted_panel_parent
from p46_restore_tx import validate_source_package


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for name in ('trial','archives','analysis','panel','panel-review','enable','status','baseline-archive','prepared-sources'):
        p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();v={k:read(path) for k,path in vars(args).items()}
    t=v['trial'];a=v['archives'];m=v['analysis'];panel=v['panel'];review=v['panel_review'];enable=v['enable'];state=v['status']
    boot=t['expected_boot']
    prepared,payload,_=validate_source_package(args.prepared_sources)
    used=read(Path(t['source_report']));old_package=read(Path(used['source_report']))
    if (prepared['status']!='host_peak256_source_package_prepared_not_uploaded' or prepared['board_operations']
        or prepared['files_sha256']!=old_package['files_sha256']
        or prepared['archive_sha256']!=old_package['archive_sha256']):raise ValueError('host-only recovery package differs from actual transmitted sources')
    if (t['status']!='passed_bounded_known_source_captures_pending_host_archive' or not t['serial_closed']
        or not t['independent_final_RX_idle'] or not t['all_TX_cleanup_verified']
        or a['status']!='passed_all_known_source_raw_buffers_archived' or a['trial_sha256']!=sha(args.trial)
        or m['status']!='passed_all_known_source_snapshot_quality' or m['trial_sha256']!=sha(args.trial)
        or m['archives_sha256']!=sha(args.archives) or len(t['cases'])!=4):raise ValueError('full known-source acquisition chain differs')
    for item in t['cases']:
        if not item['TX_cleanup_verified'] or item['blocks']!=4 or item['raw_bytes']!=1048576:raise ValueError('incomplete TX/RX case')
        child=next(x for x in a['cases'] if x['name']==item['name']);path=Path(child['report'])
        if sha(path)!=child['report_sha256']:raise ValueError('archive report changed')
        meta,raw=archive_bytes(path)
        if meta['expected_boot']!=boot or len(raw)!=item['raw_bytes'] or meta['verified_raw_sha256']!=item['raw_sha256']:raise ValueError('raw acquisition changed')
        result=next(x for x in m['cases'] if x['name']==item['name'])
        if len(result['buffers'])!=4 or any(x['status']!='passed' for x in result['buffers']):raise ValueError('not every original window passed')
    for key,digest in m['inputs_sha256'].items():
        if sha(ROOT/key)!=digest:raise ValueError('analysis source changed: '+key)
    if sha(Path(m['plan']))!=m['plan_sha256']:raise ValueError('quality plan changed')
    archive_bytes(args.baseline_archive)
    if (not accepted_panel_parent(panel,boot) or panel['duration_ms']!=8000 or not panel['TX_cleanup_verified']
        or panel['source_report_sha256']!=t['source_report_sha256']
        or not panel['RX_finished_seconds_after_TX_submission']<25
        or review['status']!='passed_P42_archives_and_independent_NumPy' or review['trial_sha256']!=sha(args.panel)):
        raise ValueError('known-tone panel evidence differs')
    for child in review['stages']:
        if child['exit_code']!=0 or sha(Path(child['report']))!=child['report_sha256']:raise ValueError('panel review child changed')
        if child['label'].endswith('_archive'):archive_bytes(Path(child['report']))
    numerical=read(Path(review['final_review']))
    if not all(numerical['checks'].values()):raise ValueError('displayed prefix numerical check failed')
    tone=next(x for x in m['cases'] if x['name']=='tone')
    tone_hz=sum(x['carrier_hz'] for x in tone['buffers'])/4
    peak_hz=numerical['NumPy_reference']['peak_offset_bins']*30000
    if abs(peak_hz-tone_hz)>15000:raise ValueError('known tone not inside expected displayed FFT bin')
    if (enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots'
        or enable['expected_boot']!=boot or not enable['persistent_autostart_enabled'] or not enable['serial_closed']
        or state['status']!='read_only_persistent_profile_state_collected' or state['boot_id']!=boot
        or state['enable_report_sha256']!=sha(args.enable) or state['taint']!='0' or state['RX_buffer']!='0'
        or state['RX_scans']!=['0']*4 or state['native_process_observed'] or not state['persistent_wrapper_selected']
        or state['pending_present'] or state['disabled_present'] or not state['serial_closed']):raise ValueError('final rearm/idle chain differs')
    mods=[x for x in m['cases'] if x['name']!='tone']
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p46-checkpoint-%Y%m%dT%H%M%S%fZ')
    record='docs/experiments/EXP-HW-036-merged-known-RF-quality.md';resume='docs/handoff/RESUME-P46-20261022.md'
    current=dict(status='known_RF_quality_and_tone_LCD_numerically_verified',updated_utc=now.isoformat(),expected_boot=boot,
        TX_expected_boot=t['TX_expected_boot'],reports={k:dict(path=rel(path),sha256=sha(path)) for k,path in vars(args).items()},
        record=record,resume=resume,checkpoint=rel(out/'report.json'),RX_idle=True,serial_closed=True,COM8_owned_by_archive=False,
        all_TX_native_cleanup_verified=True,TX_sessions_this_phase=5,source_peak_component_counts=256,
        complete_quality_raw_bytes=4194304,complete_quality_DMA_buffers=16,
        reference_EVM_db={x['name']:dict(min=x['evm_min_db'],max=x['evm_max_db']) for x in mods},
        checked_symbols=sum(x['total_checked_symbols'] for x in mods),symbol_errors=sum(x['total_symbol_errors'] for x in mods),
        known_tone_display_peak_hz=peak_hz,known_tone_LCD_updates=panel['native_summary']['display_updates'],
        known_tone_physical_LCD_confirmation=False,persistent_autostart_enabled=True,persistent_profile_rearm_pending=False,
        startup_selection_temporarily_original=False,board_shutdown_issued=False,hardware_reboots_issued_by_host=0,
        lossless_proven=False,ADC_gaps='unknown',blind_AI_verified=False,absolute_power_calibrated=False,
        absolute_frequency_calibrated=False,PRODUCT_ID_FF_root_cause_closed=False,
        historical_large_block_quality_fluctuation_root_cause_closed=False,
        historical_fluctuation_reproduced_this_phase=False,failure_fallback_verified_on_real_board=False)
    current.update(recovery_host_package_exactly_reproduced=True,recovery_generalized_upload_board_retest=False)
    # Keep the earlier boot/display verification as history, never overwrite it.
    path=ROOT/'TX-SOURCE-STATUS.json';root=read(path)
    root.update(status=current['status'],authoritative_current_field='p46_current',updated=now.isoformat(),record=record,
        updated_note='P46: every known RF DMA window archived/analysed, known-tone P42 IQ/framebuffer reviewed, persistent startup rearmed; not blind AI or gapless proof',
        status_note='以p46_current和P46恢复清单为准；P45冷启动验收保留为父证据，历史波动根因及AI仍开放。',p46_current=current)
    root['session_stop']=dict(active=False,superseded_by='p46_current',board_shutdown_issued=False,halt_observed=False,
        note='Both boards remain powered; guarded TX ended and RX is idle. Original data are archived on the PC.')
    write(path,root);write(ROOT/'results/p46-active.json',current)
    doc=ROOT/record;text=doc.read_text('utf-8')
    text=text.split('\n## 完成结果与证据（覆盖前文临时状态）',1)[0]
    text=text.replace('当前阶段进行中，原始数据回传和离线质量结论尚待完成。','本轮阶段已完成：完整数据回传、逐窗口质量判定、已知单音写屏独立复核及自启动恢复通过。',1)
    rows='\n'.join(f"| {x['name']} | {x['evm_min_db']:.2f} 至 {x['evm_max_db']:.2f} | {x['total_checked_symbols']} | {x['total_symbol_errors']} |" for x in mods)
    doc.write_text(text+f'''
## 完成结果与证据（覆盖前文临时状态）

完整归档 `{rel(args.archives)}`：四种源共16个完整返回缓冲、4MiB原始I/Q均到电脑，压缩/解压SHA与板端记录一致；不是只挑最优窗口。未发射smoke原始262144字节也已回传，`{rel(args.baseline_archive)}`。

质量判定 `{rel(args.analysis)}`，图见其quality.png：全部16窗口通过。三种调制相关度最小值分别0.998389、0.998500、0.997731，ADC端点比例均0；每组四窗口EVM范围不到1dB。

| 调制 | 已知参考EVM（dB） | 后半段检查符号数 | 错误数 |
|---|---:|---:|---:|
{rows}

载波/源对齐使用整个窗口；上述3012个已知符号的0错误不是独立BER。各调制源位置模进度均为+1采样，不能排除整个周期丢失。四组总原始帧名义时长34.13ms，分属不同发射会话，不能拼成连续ADC时间或证明长稳。

单音相对名义+960kHz约多33.84kHz，为两台未校准RF参考的相对结果；不能归因单独板卡或宣称绝对频率达标。先前20至32dB块间质量跳变在本轮冻结条件下没有重现，**历史故障根因仍未关闭**，不能写成已根治。

补充已知单音→P42接收/分析/显存写屏：`{rel(args.panel)}`，8.003秒更新{panel['native_summary']['display_updates']}次，使用完全相同已验收ELF。第33频点对应+990kHz，独立NumPy与板端FFT、RMS、总功率一致；原始最后显示前缀32768字节及1536000字节显存均归档，`{rel(args.panel_review)}`。屏幕回读PNG是显存图，不是实体屏照片或本次动画人工确认；P45的实体动态确认仍仅属于P45。显示保留no AI，不把参考解调当盲识别。RX在TX提交后8.875秒确认结束，位于30秒限时发射之内，原生TX清理及8路DDS raw0确认。

短时单音试验的同boot时钟门禁增加6项通过，`results/p46-panel-gates-20261022.xml`。该门禁分别核验受控冷启动来源、trial/readback SHA、实际boot及驱动/寄存器率一致性；没有把冷启动伪装成主机软件重启。P42原native源码、ELF和公共审查算法未修改。

归档结束已重新选用持久P43 wrapper，`{rel(args.enable)}`；只读终态`{rel(args.status)}`确认boot一致、taint0、RX buffer/scan0、无活动接收、无pending/disabled、串口已关闭。当前板仍通电，未关机。保存包`{rel(out/'report.json')}`覆盖代码/记录/状态及引用的原始数据，逐项SHA和ZIP CRC检查。

下一步依赖：先做独立会话/不同随机种子的已知源重复采集并排除数据泄漏，再做真实信号盲分类及板端接入；更多冷启动/长稳、0xFF根因与真实故障回退另行验证。CDC/外部时序、物理PCLK/绝对RF功率、无损连续性仍保持开放。
''',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P46恢复清单（已完成本轮已知源验收）

先读[HW-036](../experiments/EXP-HW-036-merged-known-RF-quality.md)、TX-SOURCE-STATUS.json的p46_current。本轮4MiB原始数据和全部16窗口通过已知参考筛查；已知单音的板端FFT/最后显示原始前缀/显存独立复核通过。真实AI仍未连接。

1. 当前两板仍通电；RX已停止、资源释放、TX守卫已退出、DDS数字零源确认、两个串口均关闭。P43持久自启动和P44防休眠仍启用；不要按历史“暂时original guard”说明操作。物理RF静默未用仪器测量。
2. 下次先用`experiments/p43_status.py --enable-report {rel(args.enable)}`只读识别新板boot、wrapper SHA、pending/disabled、进程、buffer/scan。只读识别旧板及DDS，串口各一owner、打开前DTR/RTS false。不重复起流、卸驱动或重配PL。
3. 本次新板boot `{boot}`、旧板boot `{t['TX_expected_boot']}`只是已存身份。断电后必须重读，禁止直接重放绑定旧boot的P46脚本。旧板rootfs及/tmp为易失，先从电脑归档恢复守卫/源，核验boot/SHA/原生--check，再按原冻结射频配置做有界发射。
4. 旧P201支持uudecode和分开的gzip/tar，不支持base64或tar -z。P46第一次恢复失败原始证据留存，后续有效恢复 `{t['source_report']}`。修正后的`p46_prepare_sources.py --preflight 新预检报告`只在电脑准备文件；`p46_restore_tx.py --source-report 源文件报告 --preflight 新预检报告`先离线校验全部包成员/峰值，再核对本次旧板boot和解码工具。该通用恢复版本已通过主机门禁，尚未额外重做一次板端上传；本次成功板端依据仍是原有效恢复报告，不能互相替代。
5. 当前接线仍为旧TX1→新RX1A，数字峰值256、TX−10dB、RX manual0dB；未提高功率。改变线缆/衰减/增益必须重新核验输入范围，不自动照搬。全部原始数据已电脑保存，`/run`及旧板RAM断电丢失不影响已存证据。
6. 优先补独立会话和不同种子/条件的真实RF数据；按会话分训练/验证/测试，不能把同一循环波形相邻窗口随机分割。通过后再做盲分类/板端推理及显示，不用已知符号EVM冒充AI准确率。
7. 历史严重块间波动本轮未重现，根因未关闭；0xFF、故障回退实板验证、更多冷启动/长稳、CDC/外部时序、物理PCLK、连续性仍开放。若异常，保留原UART/dmesg/boot证据，不热卸载或绑定中装PL。

保存包 `{rel(out/'report.json')}`。results由gitignore排除，须直接读文件系统。需要断电时先正常关机并确认System halted；本轮尚未执行关机。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';history=ROOT/now.strftime('START-HERE-HISTORY-P46-%Y%m%dT%H%M%SZ.md')
    history.write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作

**当前入口：P46（2026-10-22）已知射频源与小屏数值链验收完成。** 先读[实验记录]({record})、[恢复清单]({resume})和`TX-SOURCE-STATUS.json`的`p46_current`。`results/p46-active.json`是当前机器入口，results不在Git，须直接读文件系统。

单音、BPSK、QPSK、16QAM共16个完整返回缓冲/4MiB原始IQ已归档并逐窗口通过。调制参考EVM约−36.7至−38.6dB，每组范围不到1dB；已知符号检查3012个、0错误。已知单音写屏8秒/16次更新，FFT/RMS/总功率与独立NumPy一致，原始前缀和显存回读已保存。它们是已知源诊断，**不是盲AI、独立BER或无损连续接收验收**。

**当前RX idle、TX限时守卫已正常退出、串口关闭、两板仍通电，未关机。P43持久自动启动与P44防休眠已重新启用。** 下次首先只读认板、boot、配置SHA、进程和buffer/scan；若已running不另开接收。禁止热卸驱动或绑定中装PL，不重放旧boot。安全断电前先正常关机确认System halted。

P45已通过修复后一次真正断电和十分钟以上实体动态确认；本轮P46没有新增实体屏人工确认。历史严重块间波动未在本轮重现，根因仍开放；0xFF、故障回退、更多冷启动/长稳、CDC/外部IO时序、物理PCLK和绝对RF校准也未关闭。下一步优先独立会话/不同种子的真实RF数据与无泄漏盲分类，再接板端显示。

本轮检查点：`{rel(out/'report.json')}`；原始质量图：`{rel(Path(m['plot']))}`。全部旧状态入口已保存在[历史索引]({rel(history)})，仅供追溯，不作为当前操作指令。
''',encoding='utf-8')
    result=checkpoint('p46-checkpoint',vars(args),destination=out)
    print(result);print(current['status'])


if __name__=='__main__':main()
