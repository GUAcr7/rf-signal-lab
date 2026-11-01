"""Seal bounded stability and honest already-seen RF diagnostics; never touch a board."""
import argparse
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel,checkpoint
from p36_fb_snapshot_run import accepted_panel_parent
from p37_review_archives import archive_bytes
from p43_finish_enable import checked_units
from p50_save_progress import passed_host_tests
from p51_prepare_rf_bank import validate_splits
from p46_restore_tx import validate_source_package


def stable_trial(trial):
    s=trial['native_summary'];samples=trial['progress_samples']
    if (not accepted_panel_parent(trial,trial['expected_boot']) or trial.get('display_revision')!='p48'
        or trial['duration_ms']!=1800000 or s['duration_ms_requested']!=1800000
        or s['elapsed_software_s']<1800 or s['status']!='pass' or s['reason']!='duration_complete'
        or samples[-1]['state']!='finished' or trial['cancel_signal_sent']
        or s['RF_attributes_written'] or s['TX_API_loaded'] or not trial['serial_closed']):
        raise ValueError('complete automatic thirty-minute P48 trial required')
    for a,b in zip(samples,samples[1:]):
        if (a['state']==b['state']=='running' and b['elapsed_software_s']-a['elapsed_software_s']>=1
            and b['display_updates']<=a['display_updates']):raise ValueError('observed UI progress stall')
    running=[v for v in samples if v['state']=='running']
    return dict(elapsed_software_s=s['elapsed_software_s'],display_updates=s['display_updates'],
        software_updates_per_s=s['display_updates']/s['elapsed_software_s'],
        first_polled_maxrss_kib=samples[0]['maxrss_kib'],last_maxrss_kib=s['maxrss_kib'],
        observed_maxrss_growth_kib=s['maxrss_kib']-samples[0]['maxrss_kib'],
        running_polled_maxrss_max_kib=max(v['maxrss_kib'] for v in running),
        running_polled_maxrss_growth_kib=running[-1]['maxrss_kib']-running[0]['maxrss_kib'],
        memory_leak_root_cause_excluded=False,progress_samples=len(samples),
        physical_refresh_rate_measured=False,ADC_gaps='unknown',lossless_proven=False)


def checked_diagnostic(path):
    value=read(path);plan=ROOT/value['plan']
    if (value['status']!='passed_frozen_RF_adapter_and_C_Python_parity_diagnostic_only'
        or value['independent_real_RF_accuracy']!='not_measured' or value['model_weights_modified']
        or sha(plan)!=value['plan_sha256'] or sha(path.parent/'diagnostic.npz')!=value['dataset_sha256']):
        raise ValueError('frozen diagnostic only required')
    for item in read(plan)['inputs'].values():
        if sha(ROOT/item['path'])!=item['sha256']:raise ValueError('diagnostic input changed')
    for name,digest in value['outputs_sha256'].items():
        if sha(ROOT/name)!=digest:raise ValueError('C input/output changed')
    return value


def main():
    p=argparse.ArgumentParser(description=__doc__)
    for key in ('trial','review','units','clock','enable','status','nominal-ai','calibrated-ai','tone-calibration','source-bank','tests','screen-observation'):
        p.add_argument('--'+key,type=Path,required=True)
    args=p.parse_args();trial=read(args.trial);review=read(args.review);units=checked_units(args.trial,args.review,args.units)
    stats=stable_trial(trial);clock=read(args.clock);enable=read(args.enable);state=read(args.status)
    if review['status']!='passed_P42_archives_and_independent_NumPy' or review['trial_sha256']!=sha(args.trial):raise ValueError('independent review required')
    for stage in review['stages']:
        source=Path(stage['report'])
        if stage['exit_code'] or sha(source)!=stage['report_sha256']:raise ValueError('review changed')
        if stage['label'].endswith('_archive'):archive_bytes(source)
    if (clock['status']!='passed_user_power_cycle_gated_clock_driver_register_consistency' or clock['boot_id']!=trial['expected_boot']
        or enable['status']!='passed_persistent_profile_rearmed_after_two_archived_warm_boots' or enable.get('display_revision')!='p48'
        or not enable['persistent_autostart_enabled'] or enable['expected_boot']!=trial['expected_boot']
        or state['status']!='read_only_persistent_profile_state_collected' or state['enable_report_sha256']!=sha(args.enable)
        or state['boot_id']!=trial['expected_boot'] or state['taint']!='0' or state['RX_buffer']!='0' or state['RX_scans']!=['0']*4
        or state['native_process_observed'] or not state['persistent_wrapper_selected'] or state['pending_present'] or state['disabled_present']):
        raise ValueError('same-boot clock and final rearmed idle required')
    if sha(Path(clock['readback']))!=clock['readback_sha256']:raise ValueError('clock readback changed')
    nominal=checked_diagnostic(args.nominal_ai);calibrated=checked_diagnostic(args.calibrated_ai);calibration=read(args.tone_calibration)
    if calibration['status']!='passed_tone_only_common_IF_calibration' or calibration['modulation_labels_used'] or calibration['classifier_scores_used']:
        raise ValueError('independent tone-only common calibration required')
    bank=read(args.source_bank);validate_splits(bank['groups'])
    if bank['status']!='passed_12_seed_36_modulation_source_packages_PC_only_not_RF_data' or bank['real_RF_samples']!=0:raise ValueError('PC-only source bank required')
    source_hashes={name:set() for name in ('bpsk','qpsk','qam16')}
    for row in bank['groups']:
        if sha(ROOT/row['package'])!=row['package_sha256']:raise ValueError('source package changed')
        package,_,_=validate_source_package(ROOT/row['package'])
        if package['seed']!=row['seed'] or package['split']!=row['role'] or package['real_RF_acquired']:raise ValueError('source role changed')
        for name,hashes in source_hashes.items():
            if package['references'][name]['seed']!=row['seed']:raise ValueError('waveform seed differs')
            hashes.add(package['files_sha256'][name])
    if any(len(hashes)!=12 for hashes in source_hashes.values()):raise ValueError('different seeds produced duplicate modulation waveforms')
    observation=read(args.screen_observation)
    if (observation['trial_sha256']!=sha(args.trial)
        or observation['status']!='user_confirmed_finished_screen_after_completed_trial'
        or observation['active_period_motion_confirmed'] is not False):
        raise ValueError('explicit late screen observation required; no inferred active motion')
    tests=passed_host_tests(args.tests,minimum=36)
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p51-checkpoint-%Y%m%dT%H%M%S%fZ')
    reports={k:v.resolve() for k,v in vars(args).items()}
    current=dict(status='P51_thirty_minute_RX_LCD_verified_real_AI_diagnostic_not_accepted',updated_utc=now.isoformat(),
        expected_boot=trial['expected_boot'],reports={k:dict(path=rel(v),sha256=sha(v)) for k,v in reports.items()},
        record='docs/experiments/EXP-P51-stability-and-ai-input.md',resume='docs/handoff/RESUME-P51-20261023.md',checkpoint=rel(out/'report.json'),
        current_enable=rel(args.enable),current_status=rel(args.status),default_startup_display_revision='p48',
        persistent_autostart_enabled=True,RX_idle=True,serial_closed=True,board_shutdown_issued=False,
        stability=stats,screen_observation=observation,tests_passed=tests,known_RF_diagnostic_frames=36,
        nominal_diagnostic=nominal['inference'],tone_calibrated_diagnostic=calibrated['inference'],
        common_calibrated_IF_hz=calibration['calibration']['frequency_hz'],independent_real_RF_accuracy='not_measured',
        RF_model_accepted=False,live_AI_on_LCD=False,model_weights_modified=False,new_RF_training_samples=0,
        PC_only_new_source_packages=12,PC_only_modulated_waveforms=36,
        TX_operations=False,RF_attribute_writes=False,PL_changes=False,reboots_issued=0,
        PRODUCT_ID_FF_root_cause_closed=False,historical_EVM_variation_root_cause_closed=False,lossless_proven=False)
    root=read(ROOT/'TX-SOURCE-STATUS.json');root.update(status=current['status'],updated=now.isoformat(),record=current['record'],
        authoritative_current_field='p51_current',p51_current=current,
        updated_note='P51: frozen P48 thirty-minute stability; real-input frontend/C parity diagnostics, no independent AI acceptance; fresh source bank is PC-only.',
        status_note='半小时接收显示验证通过，安全停止且自启动恢复。真实AI诊断存在错误，模型未通过独立真实验收，未接入小屏。')
    write(ROOT/'TX-SOURCE-STATUS.json',root);write(ROOT/'results/p51-active.json',current)
    record=ROOT/current['record'];text=record.read_text('utf-8').split('\n## 完成结果\n')[0]
    text=text.replace('（北京时间），进行中。','（北京时间），本轮结果见下文。')
    record.write_text(text+f'''\n## 完成结果\n\n同一boot `{trial['expected_boot']}`上启动有界应用试验，没有重启、热装PL、改驱动/射频参数或发射。运行{stats['elapsed_software_s']:.3f}秒，{stats['display_updates']}次软件显示更新，轮询{stats['progress_samples']}次；首轮询/结束maxRSS为{stats['first_polled_maxrss_kib']}/{stats['last_maxrss_kib']}KiB，观察增长{stats['observed_maxrss_growth_kib']}KiB，未观察到相邻有效轮询间停止更新。这里是软件更新计数，不是物理屏刷新率或ADC连续性证明。原始最后前缀、显存、时钟和显示单位复核通过。\n\n## 真实AI输入诊断\n\n先冻结名义IF方案与模型，再在原P46已见数据每类4个DMA块、每块3个完整片段上执行，共36帧。DMA分别滤波，不拼接未知间隙；513抽头Kaiser抗混叠FIR后16倍降采样，从30.72MS/s、128点/符号转到1.92MS/s、8点/符号。\n\n名义960kHz下变频：FP32判对{nominal['inference']['fp32']['correct']}/36，INT8判对{nominal['inference']['int8']['correct']}/36。发现实际基带单音约{calibration['calibration']['frequency_hz']:.3f}Hz，名义方案仍留约33.84kHz频偏，超出原模型训练频偏范围。单独使用校准单音估计一个公共IF，未使用三类调制标签或分类得分；第二版方案在诊断前另行冻结、原方案不覆盖。公共校准后FP32判对{calibrated['inference']['fp32']['correct']}/36，INT8判对{calibrated['inference']['int8']['correct']}/36，整体未改善，不能把频偏修正写成分类错误已解决。\n\n两种方案每帧FP32/INT8的Python与冻结C实现数值/类别均匹配；因此确认适配/推理接通，但不能认为模型在真实域已达标。上述数据只有每类一个周期波形/一次采集，源seed已见，不是独立测试集；不选最高数字冒充准确率，不调权重或按标签改参数，不把未知输入三选一接入屏幕。\n\n12个新seed已划分6训练/3验证/3测试，预定各split三个不同采集轮次，36份调制发射波形均保持峰值256及原保护程序，包哈希/结构校验通过。它们只是电脑端TX素材，真实RX训练/测试样本仍为0。每轮应先采独立校准单音，统一修正该轮所有类别；测试RF在模型/预处理冻结后再采，不能随机拆周期相邻帧。\n\n## 终态与后续\n\n同一P48持久profile已恢复，RX idle、串口关闭、taint0、无pending/disabled。板仍通电未关机；下次默认自启动，先重新认身份。已知源与独立真实AI训练/验证/测试是下一步；旧P50一次冷启动成功与本轮半小时稳定性不能关闭历史0xFF/质量波动根因。检查点：{rel(out/'report.json')}。\n''',encoding='utf-8')
    (ROOT/current['resume']).write_text(f'''# P51恢复清单（2026-10-23）\n\n先读[实验记录](../experiments/EXP-P51-stability-and-ai-input.md)、TX-SOURCE-STATUS.json的p51_current和results/p51-active.json。results直接读文件系统。\n\n1. 同一boot `{trial['expected_boot']}`上，冻结P48应用有界半小时稳定性/原始前缀/显存/时钟/单位复核通过。RX现idle，串口关闭，板仍通电未关机，P48自启动已恢复。\n2. 只读入口：experiments/p43_status.py --enable-report {rel(args.enable)}。上电后boot可能变化且自动接收，先核验owned control再停；单一COM8 owner，禁止有绑定时热装PL/卸载驱动。\n3. AI适配和C/Python输出对照已通，但旧真实数据公共校准后仅29/36判对，不能称AI达标；不继续在这36个旧片段上反复调优。冻结模型/两个诊断及所有输入输出均保留。\n4. 新seed源包 {rel(args.source_bank)} 仅PC生成，未发射/未采新RF。按6/3/3 seed和独立采集轮次分开，测试留到模型/预处理冻结后再采。沿用峰值256、TX -10dB、有界保护；先读两板boot/状态与接线，再调用匹配上传/接收工具。旧P46分析脚本含seed20261016硬编码，分析新源前必须改为读取受校验的源metadata并测试，不能直接重放。\n5. 每轮单独采校准单音，公共IF不依赖分类标签，不能用各类真值拟合载波作为盲AI输入。下一步采新训练/验证会话，冻结改进模型，再采未暴露测试会话；不要把TX源文件当RX训练数据。\n6. 检查点：{rel(out/'report.json')}；断电前需正常关机，本轮未关机。\n''',encoding='utf-8')
    with record.open('a',encoding='utf-8') as handle:
        handle.write(f'''\n## 屏幕观察与内存结论的边界\n\n用户第一次回复“亮着，但不再变化”时，1800秒程序已正常结束。追问顶部状态后，用户明确回答“现在看到 RX FINISHED／RX STOPPED 等结束提示”。本次确认的是结束画面仍亮、停止更新符合结束状态；没有由此推断25分钟时的实际动态观察，更不能据软件计数证明每一帧物理LCD刷新。人机原始反馈单独保留在{rel(args.screen_observation)}。\n\n运行态轮询maxRSS最高{stats['running_polled_maxrss_max_kib']}KiB、首末运行态增长{stats['running_polled_maxrss_growth_kib']}KiB；结束摘要峰值{stats['last_maxrss_kib']}KiB，比首轮询高{stats['observed_maxrss_growth_kib']}KiB。可确认本次运行态没有观察到RSS持续增长，不能声明排除内存泄漏根因。\n''')
    with (ROOT/current['resume']).open('a',encoding='utf-8') as handle:
        handle.write('\n用户确认当前为RX FINISHED／RX STOPPED结束画面，仍亮但停止变化属于正常终态；本轮没有独立确认25分钟时的物理动态刷新。运行态RSS稳定，退出峰值增加120KiB，未据此关闭内存根因。\n')
    start=ROOT/'START-HERE.md';(ROOT/now.strftime('START-HERE-BEFORE-P51-SAVE-%Y%m%dT%H%M%SZ.md')).write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作\n\n**当前入口P51：半小时接收/显示稳定性通过；真实AI输入适配已通，模型尚未通过真实验收。** 先读[本轮记录](docs/experiments/EXP-P51-stability-and-ai-input.md)、[恢复清单](docs/handoff/RESUME-P51-20261023.md)和TX-SOURCE-STATUS.json的p51_current。\n\nP48运行{stats['elapsed_software_s']:.1f}秒/{stats['display_updates']}次更新，RSS观察增长{stats['observed_maxrss_growth_kib']}KiB，原始I/Q、显存、时钟/单位复核通过。RX已安全停止，自启动恢复，串口关闭，板仍通电未关机。最后boot `{trial['expected_boot']}`，再次工作重新认板。\n\n已见真实数据36帧：名义IF FP32/INT8为31/34判对；单独校准单音公共IF后均29判对，整体未改善。Python/C数值对照通过，但这些不是独立准确率，AI没有接入小屏。新12组seed/36份调制波形仅PC准备，未采新训练/测试数据。\n\n下一步按种子及独立会话采真实训练/验证数据，模型/预处理冻结后再采测试；不反复优化这36个旧片段。多次冷启动/更长期稳定性/校准/无损连续性仍开放，历史故障根因未关闭。\n\n检查点：`{rel(out/'report.json')}`。results不在Git，直接读文件系统。\n''',encoding='utf-8')
    print(checkpoint('p51-checkpoint',reports,out));print(current['status'])


if __name__=='__main__':main()
