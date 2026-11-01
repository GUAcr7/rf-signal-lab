"""Verify idle, restore P48 startup, and seal actual AI evidence for resumption."""
import argparse,json,re,subprocess,sys
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel,checkpoint

def main():
    p=argparse.ArgumentParser();p.add_argument('--flow',required=True,type=Path);p.add_argument('--live',type=Path)
    p.add_argument('--recovery',type=Path);args=p.parse_args()
    flow=read(args.flow)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-final-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='closing_hardware_and_recording_actual_outcome',stages=[],flow=rel(args.flow),flow_sha256=sha(args.flow),
        board_power_removed=False,board_shutdown=False)
    def save():write(out/'report.json',r)
    def run(label,script,*params):
        print(label,flush=True)
        q=subprocess.run([sys.executable,str(ROOT/'experiments'/script),*map(str,params)],cwd=ROOT,capture_output=True,timeout=180)
        (out/(label+'.stdout')).write_bytes(q.stdout);(out/(label+'.stderr')).write_bytes(q.stderr)
        rows=[Path(s.strip())/'report.json' for s in q.stdout.decode().splitlines() if Path(s.strip()).is_absolute() and (Path(s.strip())/'report.json').is_file()]
        entry=dict(label=label,exit_code=q.returncode);r['stages'].append(entry);save()
        if q.returncode or len(rows)!=1:raise ValueError(label+' failed')
        entry.update(report=rel(rows[0]),report_sha256=sha(rows[0]));save();return rows[0],read(rows[0])
    save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        preflight_path,preflight=run('final_both_boards_idle','p46_preflight.py')
        if preflight['status']!='read_only_both_boards_identified_DMA_idle':raise ValueError('final idle not verified')
        dds=preflight['boards']['COM9']['DDS_raw']
        values=re.findall(r'^([0-9]+)\r?$',dds,re.M)
        if values!=['0']*8:raise ValueError('DDS zero sources not confirmed')
        if args.recovery:enable_path,enable=run('restore_P48_startup','p55_rearm_profile.py','--recovery',args.recovery)
        else:enable_path,enable=run('restore_P48_startup','p52_rearm_baseline.py')
        state_path,state=run('final_startup_and_RX_status','p43_status.py','--enable-report',enable_path)
        if (state['status']!='read_only_persistent_profile_state_collected' or state['taint']!='0'
            or state['RX_buffer']!='0' or state['RX_scans']!=['0']*4 or state['native_process_observed']
            or not state['persistent_wrapper_selected'] or state['pending_present'] or state['disabled_present']):raise ValueError('final startup or idle mismatch')
        accepted=flow['status']=='passed_real_RF_AI_independent_test_ARM_and_offline_live_candidate'
        live=read(args.live) if args.live else None
        live_accepted=bool(live and live['status']=='passed_three_class_real_RF_live_ARM_AI_LCD_and_independent_archives')
        for stage in flow['stages']:
            if 'report' in stage and sha(ROOT/stage['report'])!=stage['report_sha256']:raise ValueError('flow evidence changed')
        reports=dict(flow=args.flow,preflight=preflight_path,enable=enable_path,final_status=state_path,
            final=out/'report.json',current_boot=ROOT/'results/p43-observed-cycle-20261024T031944Z/report.json',
            current_clock=ROOT/'results/p36-clockwiz-readback-20261024T032659Z/report.json',
            current_screen_review=ROOT/'results/p42-review-20261024T032421Z/report.json',
            current_units=ROOT/'results/p48-unit-review-20261024T034519Z/report.json')
        if args.recovery:
            recovered=read(args.recovery);warm_review=read(ROOT/recovered['review'])
            if recovered['expected_boot']!=state['boot_id']:raise ValueError('recovery boot differs from final state')
            reports.update(recovery=args.recovery,current_boot=ROOT/recovered['warm_cycle'],current_screen_review=ROOT/recovered['review'],
                current_units=ROOT/recovered['units'],current_clock=Path(warm_review['post_clock_acceptance']))
        if accepted:
            dataset=read(ROOT/flow['dataset']);trained=read(ROOT/flow['train']);test=read(ROOT/flow['independent_test']);arm=read(ROOT/flow['ARM_verification'])
            frozen=read(ROOT/flow['freeze'])
            for value in frozen['frozen_inputs'].values():
                if sha(ROOT/value['path'])!=value['sha256']:raise ValueError('frozen pipeline changed before checkpoint')
            r.update(independent_test=test['evaluation'],selected_mode=test['selected_mode'],per_seed=test['by_seed'],
                training_frames=dataset['training_frames'],validation_frames=dataset['validation_frames'],test_frames=test['test_real_frames'],
                training_source_seeds=6,validation_source_seeds=3,test_source_seeds=3,
                model_sha256=trained['model_sha256'],quantized_model_sha256=trained['quantized_model_sha256'],
                ARM_benchmarks=arm['benchmarks'],ARM_full_frontend_CNN_matches_Python=True)
            r.update(heldout_RF_capture_boot=read(ROOT/flow['test_acquisition'])['expected_boot'],ARM_execution_boot=arm['expected_boot'])
            for key in ('dataset','train','freeze','test_acquisition','independent_test','ARM_verification','live_candidate_build'):reports[key]=ROOT/flow[key]
        if live:
            r.update(live=rel(args.live),live_sha256=sha(args.live),live_status=live['status']);reports['live']=args.live
        r.update(status='passed_controlled_real_RF_AI_and_live_LCD_checkpoint_ready' if accepted and live_accepted else 'passed_controlled_real_RF_AI_checkpoint_ready_live_LCD_pending' if accepted else 'saved_partial_AI_work_not_accepted',
            AI_accepted=accepted,live_AI_on_LCD_verified=live_accepted,ten_minute_whole_system_AI_trial=False,
            expected_boot=state['boot_id'],TX_expected_boot=preflight['boards']['COM9']['boot_id'],
            TX_DMA_idle=True,DDS_zero_readback=True,RX_DMA_idle=True,serial_closed=True,
            startup_paused_for_archiving=False,P48_persistent_startup_restored=True,AI_persistent_autostart=False,
            scope='BPSK/QPSK/16QAM at fixed 2450MHz LO, nominal IF960kHz, 240ksym/s, TX-10dB/peak256 and RX manual0dB; RF-test, ARM-execution and live-display boots recorded separately',
            signal_SNR_measured=False,unknown_rejection_accepted=False,ADC_gaps='unknown',lossless_proven=False,
            physical_LCD_confirmation_this_trial=False,independent_cold_boot_generalization=False)
        checkpoint_dir=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-checkpoint-%Y%m%dT%H%M%S%fZ');r['checkpoint']=rel(checkpoint_dir/'report.json');save()
        current=dict(report=rel(out/'report.json'),status=r['status'],updated_utc=datetime.now(timezone.utc).isoformat(),
            expected_boot=r['expected_boot'],TX_expected_boot=r['TX_expected_boot'],serial_closed=True,RX_idle=True,TX_idle=True,
            startup_paused_for_archiving=False,P48_persistent_startup_restored=True,AI_model_accepted=accepted,
            live_AI_on_LCD_verified=live_accepted,AI_persistent_autostart=False,checkpoint=r['checkpoint'],
            final_enable=rel(enable_path),final_status=rel(state_path))
        state_root=read(ROOT/'TX-SOURCE-STATUS.json');state_root.update(status=r['status'],authoritative_current_field='p52_current',p52_current=current)
        write(ROOT/'TX-SOURCE-STATUS.json',state_root);write(ROOT/'results/p52-active.json',current)
        if live:
            write(ROOT/'results/p53-active.json',dict(current,live_report=rel(args.live)))
        resume=ROOT/'docs/handoff/RESUME-P52-20261024.md'
        lines=['# P52/P53恢复记录（2026-10-24）','',
            '当前结果：'+r['status']+'。',
            '权威报告：`'+rel(out/'report.json')+'`；检查点：`'+r['checkpoint']+'`。','',
            '## 保存时硬件状态','',
            '两板仍通电，未关机。当前TX/RX DMA闲置、DDS八路源为零、串口关闭；新板恢复原P48持久自启动，未将AI候选替换为默认启动程序。',
            '新板boot：`'+r['expected_boot']+'`；旧板boot：`'+r['TX_expected_boot']+'`。这些身份只适用于本次上电，不能重放到下一次。','',
            '## 已完成与范围','',
            'AI独立测试验收：'+str(accepted)+'；真实RF实时ARM分类与LCD文件/像素核验：'+str(live_accepted)+'。',
            '数据计划按源seed及采集组隔离，六组训练、三组验证、三组测试；具体完成量见权威报告。小屏实时演示的最后三个窗口/类另核验，不能冒称独立测试成绩。',
            '限BPSK/QPSK/16QAM、固定240ksym/s、名义960kHz中频、当前接线/增益。公共IF只来自单音，没有用各类标签调预处理；未验证任意信号、空输入拒识、校准置信度或跨冷启动泛化。','',
            '## 再次工作','',
            '1. 先读START-HERE.md、本记录和权威报告。只用实际枚举的FTDI旧板/CH340新板识别设备，不单凭Win32_SerialPort。',
            '2. 重新只读识别两板、boot/taint、程序/DMA、源状态。P48可能已自主运行，按已有owned control安全停止后才归档/采集；不要抢占串口或重装PL。',
            '3. 旧板RAM源包断电丢失，从电脑已校验源包恢复并更新boot-session身份；新板先做同boot完整DMA smoke。当前-10dB/峰值256与RX0dB、原衰减接线保持。',
            '4. 用新采单音重新校准公共IF后复用冻结模型。P52通用ARM程序接收显式IF；当前P53显示候选编译入了本次IF，下一次上电不能把它直接当新校准值。',
            '5. 既有独立测试已经暴露，后续调模型不能重用它作为新独立验收。需要新模型时先新建未见源seed/采集组并冻结协议。','',
            '## 后续工作','',
            '- 将公共IF校准、信号有效/未知/停止状态和AI启动流程固化，再完成十分钟整机已知信号切换演示。',
            '- 确认正式赛题对自研PL FFT/功率谱的要求，ARM频谱不替代其独立验收。',
            '- 跨电源周期和更广频偏/符号率/信号强度条件另做验证，现阶段不宣称通过。',
            '- 旧P201外接UART候选仍未部署，未加入本轮射频/显示固件。','',
            '## 失败证据','',
            'COM9曾出现Windows ClearCommError，原失败批次/中断tone和BPSK原始数据均保留并排除AI。经同boot只读识别、恢复回显/提示符、核验DMA和DDS后显式恢复；未复位板卡或修改射频功率。系统USB偶发错误根因没有宣称根治。']
        if accepted:lines.extend(['','选定模式独立测试：`'+json.dumps(r['independent_test'][r['selected_mode']],ensure_ascii=False)+'`。'])
        resume.write_text('\n'.join(lines)+'\n',encoding='utf-8')
        start=ROOT/'START-HERE.md';backup=ROOT/('START-HERE-BEFORE-P52-'+out.name[-16:]+'.md')
        if not backup.exists():backup.write_bytes(start.read_bytes())
        text='# 从这里恢复项目工作\n\n**2026-10-24最新：'+r['status']+'。**\n\n'
        if accepted:
            m=r['independent_test'][r['selected_mode']];text+='受控真实RF独立测试（'+r['selected_mode']+'）：'+str(m['correct'])+'/'+str(m['frames'])+'帧；实际ARM完整前端/分类与Python一致。小屏实时AI核验：'+str(live_accepted)+'。\n\n'
        text+='先读[恢复清单](docs/handoff/RESUME-P52-20261024.md)、[实验记录](docs/experiments/EXP-P52-real-RF-AI.md)和results/p52-active.json。权威字段为TX-SOURCE-STATUS.json的p52_current。\n\n'
        text+='已停止收发、关闭串口并恢复原P48下一次自启动；板仍通电，未关机。AI候选尚未设为开机默认，十分钟AI整机演示未验收。重新通电需重新认板、更新boot身份并用单音校准，不能重放旧命令。\n\n'
        text+='results/被Git忽略，必须直接读文件系统。检查点：`'+r['checkpoint']+'`。\n\n此前完整入口保存在`'+backup.name+'`，旧P51和UART记录为历史，不能替代当前状态。\n'
        start.write_text(text,encoding='utf-8')
        with (ROOT/'docs/experiments/EXP-P52-real-RF-AI.md').open('a',encoding='utf-8') as f:
            f.write('\n## 最终保存\n\n权威结果：`'+rel(out/'report.json')+'`，状态`'+r['status']+'`。\n\n')
            if accepted:f.write('独立测试：`'+json.dumps(r['independent_test'],ensure_ascii=False)+'`。实际ARM耗时：`'+json.dumps(r['ARM_benchmarks'],ensure_ascii=False)+'`。\n\n')
            f.write('恢复原P48持久自启动；最后两板DMA/源/新板启动选择均已读回。串口关闭，板未关机。AI候选未替换持久程序，10分钟整机AI与任意信号拒识仍待验收。\n')
        reports['active']=ROOT/'results/p52-active.json'
        for name in ('p53-active.json','p54-active.json','p55-active.json'):
            if (ROOT/'results'/name).is_file():reports[name]=ROOT/'results'/name
        checkpoint('p52-checkpoint',reports,destination=checkpoint_dir)
    except Exception as e:r.update(status='failed_work_close_requires_review',error=repr(e));save()
    print(out);print(r['status']);return 0 if r['status']!='failed_work_close_requires_review' else 1
if __name__=='__main__':raise SystemExit(main())
