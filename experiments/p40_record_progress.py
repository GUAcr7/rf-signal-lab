"""Record the completed warm/cold recovery evidence and active trial pointer."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from p32_session import ROOT


def read(path):return json.loads((ROOT/path).read_text('utf-8'))
def write(path,obj):(ROOT/path).write_text(json.dumps(obj,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def rel(path):return Path(path).resolve().relative_to(ROOT).as_posix()


def main():
    suite_path='results/p40-recovery-suite-20261021T151149Z/report.json';suite=read(suite_path)
    prior='results/p40-recovery-suite-20261021T145145Z/report.json'
    if any(read(path)['status']!='passed_fresh_boot_cancel_restart_120s_RX_LCD_and_archived_NumPy_review' for path in (suite_path,prior)):raise ValueError('accepted suites required')
    cold_path='results/p32-preflight-20261021T150823Z/report.json';cold=read(cold_path)
    if cold['status']!='both_boards_identified' or not cold['boards']['COM8']['rf_ready']:raise ValueError('cold readiness required')
    final=read(rel(suite['final_review']));last=read(rel(suite['longest_monitor']))
    for stage in suite['stages']:
        path=Path(stage['report'])
        if hashlib.sha256(path.read_bytes()).hexdigest()!=stage['report_sha256']:raise ValueError('suite evidence changed')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p40-record-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    human=dict(source='direct user reply in current chat',quote='新板已断电并重新上电',
        preceded_by_normal_halt='results/p40-cold-cycle-ready-20261021T150315Z/report.json',
        post_cycle_identification=cold_path,user_reported_power_cycle=True,
        power_rail_discharge_instrument_verified=False,old_board_power_cycle_requested=False)
    write(rel(out/'human-power-cycle.json'),human)
    record='docs/experiments/EXP-HW-030-boot-recovery-and-cold-observation.md'
    resume='docs/handoff/RESUME-P40-20261021.md'
    active='results/p41-autonomous-once-20261021T153301Z/report.json'
    state=read('TX-SOURCE-STATUS.json');state['authoritative_current_field']='p40_current'
    state['p39_current']['software_checkpoint_superseded_by']='p40_current'
    state['p40_current']=dict(updated_utc=datetime.now(timezone.utc).isoformat(),record=record,resume_record=resume,
        status='two_fresh_boot_recovery_suites_and_one_user_reported_cold_cycle_verified_P41_trial_in_progress',
        final_completed_suite=suite_path,previous_suite=prior,last_completed_boot=suite['expected_boot'],
        cold_factory_boot=cold['boards']['COM8']['boot_id'],cold_preflight=cold_path,
        cold_human_evidence=rel(out/'human-power-cycle.json'),factory_PRODUCT_ID_FF_seen_this_power_cycle=False,
        PRODUCT_ID_FF_root_cause_closed=False,software_reboots_before_P41=3,
        latest_completed_clock_acceptance=rel(suite['clock_acceptance']),
        latest_completed_monitor=rel(suite['longest_monitor']),latest_native_summary=last['native_summary'],
        native_build='results/p39-build-20261021T142930Z/report.json',native_binary_sha256=last['binary_sha256'],
        latest_IQ_and_screen_review=rel(suite['final_review']),screen_png=rel(final['screen_png']),
        source_audit='results/p40-reset-source-20261021T145244Z/report.json',
        reset_before_cycle='results/p40-reset-readback-20261021T145951Z/report.json',
        reset_after_cycle='results/p40-reset-readback-20261021T150910Z/report.json',
        physical_LCD_motion_evidence='P39 direct user confirmation; no new P40 human FPS/whole-session observation',
        active_trial_report=active,active_trial_is_not_accepted=True,
        do_not_replay_last_completed_boot=True,TX_started=False,persistent_autostart_enabled=False,
        lossless_proven=False,known_target_proven=False,real_AI_verified=False,
        CDC_Critical_remaining=58,external_input_delay_missing=7,external_output_delay_missing=29)
    state['active_trial_report']=active;write('TX-SOURCE-STATUS.json',state)
    text=f'''# HW-030：重启恢复、取消重启与一次人工断电观察

日期：2026-10-21晚（北京时间）。P39精确最终二进制777b93620f211f4e516c5a17a1bc703c6da06663a9afeff9c9a1c3fe72f4c925未改；新增恢复验证、源代码复位审查及只读现场采集工具，没有启动TX。

## 完成结论

1. `results/p32-preflight-20261021T144219Z/report.json`：两板在线，旧板boot=3bcec2b6-df8d-479b-8c1f-d989bfc61c0a、新板原P39 boot=3c107af6-dcab-4ab0-8269-7f0f3a050390，RF idle、taint0。
2. `results/p40-factory-boot-20261021T144656Z/report.json`：普通软件重启回厂家RF，boot=495a5051-3def-4463-8125-5695f677ddcb。原guard/固件/DTBO哈希未变，恰好一次overlay attempt1，RF三个名字完整，无fb0、taint0。该次无0xFF；只属warm boot，不当冷启动根治证据。
3. `results/p35-once-merged-20261021T144840Z/report.json`：另一次新hold启动，guard先恢复，空绑定后单次PL+overlay，boot=7eabc5bd-15ea-40a4-809f-19fe0505a63b。`{prior}`完整17阶段通过：新boot时钟、配置读回、8轮cancel/recreate、稀疏布局/绘图、3秒监测、SIGTERM取消、再运行120秒，以及三个保留前缀和屏幕归档/NumPy。
4. `results/p40-cold-cycle-ready-20261021T150315Z/report.json`：独立核验三份前缀和屏幕均在电脑，RX idle，正常poweroff至System halted；只操作新板，旧板未关机。
5. 用户回复“新板已断电并重新上电”，单独保留`{rel(out/'human-power-cycle.json')}`。最初`results/p32-preflight-20261021T150638Z/report.json`未建立shell，原件保留；随后`results/p40-cold-observe-20261021T150742Z/report.json`收到DHCP/Xserver/登录信息，不能把第一次空响应计为RF失败。原厂RF-only模式下Xserver提示缺fb0属该模式缺屏幕节点，不是合并绘图故障。
6. `{cold_path}`：新boot=224b7c4a-5ff4-404d-bb38-56274893858b，原厂PHY/ADC/DDS就绪、buffer/scan全0、taint0，无0xFF。断电动作来自用户报告，没有仪器确认全部电源轨放电或复位脉冲，因此仍不能认定冷启动缺陷已根治。
7. `results/p35-once-merged-20261021T150934Z/report.json`：按安全新hold路径恢复合并配置，boot={suite['expected_boot']}。`{suite_path}`又完整通过17阶段。接收取消后再建会话并完成两分钟，最终C二进制本身现在也有完整120秒实板证据；不是沿用修UI前的SHA。

## 最新两分钟结果

{json.dumps(last['native_summary'],ensure_ascii=False,indent=2)}

以上为机器摘要，始终按published=consumed+UI overwritten+pending核验。单上下文/缓冲反复refill，UI每次只取最新8192帧前缀，最后一帧32KiB保存；不是全流保留或ADC无丢样证明。

全部child路径及SHA在两份suite报告；最后归档与独立复核：`{rel(suite['final_review'])}`。最终framebuffer已查看，上下状态均RX STOPPED；它不是实物照片。P39用户确认实体运动保留原作用范围，不扩展成P40全程物理FPS测量。

## 冷启动根因的新增证据与限度

- `results/p40-reset-source-20261021T145244Z/report.json`固定原厂内核tar.gz的SHA，提取ad9361.c/.h和SPI core；原包和内核未修改。供应dirty源树与运行镜像精确构建匹配仍未证明。
- 提取ad9361.c:934-955显示GPIO reset逻辑置0、等待1ms、置1、再等1ms；9316附近请求reset GPIO，9347调用复位后9349读PRODUCT_ID；712-754通过spi_write_then_read读字节。**不能仅凭0xFF断言源码根本没有硬件复位。** 也不能把源码中的延时当作针脚实测脉冲。
- `results/p40-reset-readback-20261021T145951Z/report.json`及`results/p40-reset-readback-20261021T150910Z/report.json`：live DT reset cells=[8,100,0]，GPIO controller base906、118 pins，debug显示gpio-1006 reset out hi；SPI上限10MHz、CPHA属性存在。未写GPIO、未访问SPI寄存器。高电平只属于读取时刻，不能确认探测时脉宽/电源/40MHz参考时钟或SPI物理波形。
- 下一次若再现0xFF，先保留全部dmesg、live DT、GPIO归属、SPI driver绑定/版本、默认文件SHA；不热卸载、不重绑、不在已绑定驱动下翻转reset。只有有失败/成功成对现场后再判断是否需要测复位/参考时钟/SPI线，或在独立新启动中做单变量SPI速率试验。不能用随意加等待代替定位。

## 工具与测试

- `p40_factory_boot.py`：验证电脑检查点、两板身份和idle后只重启新板一次，按名字/单次apply/taint/日志验收，不自动retry。新增9项分类负例；连同P39 reuse/hold回归，共23 passed，见results/p40-recovery-gate-tests-20261021.xml。
- `p40_recovery_suite.py`：各child严格串行，命令、日志、退出码、报告SHA持久化；任一步失败即停，不偷偷重试。两次各17阶段实际通过。
- `p35_once_merged_trial.py`补充P39原生程序/launcher的活动进程拦截，保留buffer/scan门槛。
- `p40_reset_readback.py`新版允许只读保留失败probe状态，不要求RF_READY才观察；成功现场的原执行副本均保留。未把读取工具修改说成固件修复。

## 当前进一步试验（尚不算通过）

正在准备/执行一次性板端自主启动：`{active}`。它会在新boot先恢复原guard，再由板端装已固定哈希的合并PL/overlay并启动有界接收显示；不改变长期默认模式。继续前先读此报告实时status、pending wrapper与boot字段。此前完成boot不能代表此试验当前状态；完成后另写HW-031/P41状态，未验收前不宣布开机自动显示完成。

仍未关闭：厂家0xFF根因、长期稳定性/故障自恢复、ADC连续性、58项CDC与外部7输入/29输出缺延迟、永久可回退独立开机显示、已知信号质量与真实AI。
'''
    (ROOT/record).write_text(text,encoding='utf-8')
    (ROOT/resume).write_text(f'''# P40恢复入口

读START-HERE、TX-SOURCE-STATUS.json、[HW-030](../experiments/EXP-HW-030-boot-recovery-and-cold-observation.md)。

P40两份恢复suite已通过并归档；其中最后完成boot={suite['expected_boot']}。但P41一次性启动正在运行，**先读`{active}`并重新认板**，不重放P40旧boot。若pending_one_shot_wrapper=true，先核查真实guard/backup与已保存的boot.sh，不重复arm或热加载PL。若P41新boot已restore原guard，遵循该报告的新boot做只读后验。失联保留UART尾迹，不热卸ADC/PWM。

P40有一次用户报告的断电上电，RF正常，无0xFF；不代表根因关闭。临时RAM/运行PL不随断电保存。电脑原始文件均保留，results被gitignore排除。
''',encoding='utf-8')
    start=ROOT/'START-HERE.md';old=start.read_text('utf-8')
    banner=f'''**P40已完成，P41试验进行中（2026-10-21晚）：** 先读[HW-030](docs/experiments/EXP-HW-030-boot-recovery-and-cold-observation.md)、TX-SOURCE-STATUS.json的p40_current及`{active}`。两次新boot恢复suite、一次人工断电后的原厂RF就绪已验证，0xFF根因仍未关闭。P41还不是通过结论，不重放下方任何历史boot。\n\n'''
    start.write_text('# 从这里恢复项目工作\n\n'+banner+old.split('\n',1)[1].lstrip('\n'),encoding='utf-8')
    write(rel(out/'report.json'),dict(status='P40_completed_evidence_recorded_P41_active_pointer_saved',suite=suite_path,
        user_power_cycle=rel(out/'human-power-cycle.json'),active_trial=active,board_operations=False))
    print(out)


if __name__=='__main__':main()
