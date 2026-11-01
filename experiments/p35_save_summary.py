"""Save the actual post-interruption summary, without any board access."""
from datetime import datetime,timezone
import json
from p32_session import ROOT

def main():
    status=ROOT/'TX-SOURCE-STATUS.json'
    data=json.loads(status.read_text('utf-8'))
    bit='results/p35-ttl-bin-20261020T162454Z/report.json'
    route='results/p35-ttl-route-20261020T161703Z/report.json'
    close='results/p35-interrupt-close-20261020T162845Z/report.json'
    b=json.loads((ROOT/bit).read_text('utf-8'))
    c=json.loads((ROOT/close).read_text('utf-8'))
    if b['status']!='passed_TTL33_native_bin_not_deployed' or c['status']!='upload_interrupted_before_arm_current_RF_idle_guard_unchanged':
        raise RuntimeError('summary evidence incomplete')
    current=data['p35_current']
    current.update(updated_utc=datetime.now(timezone.utc).isoformat(),
        status='summary_checkpoint_TTL33_bin_ready_not_programmed_no_background_trial',
        interruption_close=close,partial_trial='results/p35-once-merged-20261020T162656Z/report.json',
        panel_host='results/p35-arm-panel-check-20261020T161014Z/report.json',
        panel_ARM_known_fixture_test='results/p35-panel-board-20261020T161445Z/report.json',
        sparse_raw_archive='results/p31-sparse-archive-20261020T162105Z/report.json',
        no_background_trial=True,next_task='Reidentify current boot, repeat fresh upload into new timestamp, controlled one-shot fresh boot + explicit PL load + no-firmware overlay; then finite RX/display/parallel tests')
    current['TTL33_candidate'].update(status='native_bin_exported_not_programmed',
        build=route,bitstream_report=bit,bitstream_sha256=b['bitstream_sha256'],
        bitstream_bytes=b['bitstream_bytes'],WNS_ns=.490,WHS_ns=.054,
        CDC_Critical_remaining=58,external_input_delay_missing=7,external_output_delay_missing=29,
        hardware_tested=False)
    current['new_board']['latest_idle_check']=close
    data['authoritative_current_field']='p35_current'
    status.write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    path=ROOT/'START-HERE.md'
    text=path.read_text('utf-8')
    text=text.replace('新TTL33/PWM2副本`E:/p33-ttl-114312/project/combined.xpr`在重新构建，','新TTL33/PWM2副本`E:/p33-ttl-114312/project/combined.xpr`已完成综合/布线及原生裸bin导出（WNS+0.490ns/WHS+0.054ns），尚未配置上板，')
    text=text.replace('主机回归与ARM交叉编译结果见独立审查；','62项主机回归/结构检查、ARM交叉编译及板端无屏已知夹具分析已通过；')
    text+='\n**00:29汇总检查点**：用户要求先汇总，未完成上传已安全中止；新启动/新PL/新overlay均未执行，无后台任务会自动重启。串口echo及原guard核验恢复，当前boot未变、RF空闲、taint0。继续前读[本轮收尾段](docs/experiments/EXP-HW-025-review-corrections-and-ttl.md)和[恢复清单](docs/handoff/RESUME-20261021.md)。\n'
    path.write_text(text,encoding='utf-8',newline='\n')
    handoff='''# 2026-10-21 P35恢复清单

先读START-HERE和EXP-HW-025。当前权威字段p35_current；P34“唯一坏设备树/CDC排除”已经撤回。

当前boot8033ec3f-0588-4e7a-8572-e440c547cf43，新板RF空闲、taint0，运行P32合并PL+厂家RF树，无fb0；默认厂家磁盘固件已经恢复。旧板未启动TX。

TTL33工程E:/p33-ttl-114312已重新布线，DCP与裸bin来源及SHA见results/p35-ttl-bin-20261020T162454Z/report.json。新位流尚未配置。配对无firmware overlay见results/p35-explicit-overlay-20261020T160459Z/report.json。

上传中断记录results/p35-once-merged-20261020T162656Z/report.json，结束验证results/p35-interrupt-close-20261020T162845Z/report.json。没有安装hold，没有重启/装PL/应用overlay，没有后台自动运行。不要使用未完成RAM文件。

继续时重新认板/读boot与哈希，再以新时间戳调用experiments/p35_once_merged_trial.py，参数expected-boot使用新读值，bitstream-report/overlay-report使用上述已核验文件。禁止热卸载或在驱动下重配PL。该脚本在新启动先恢复原guard后才单次配置；失败只保存日志，不热重试。

若单次合并初始化成功：独立读FCLK/ClockWiz LOCK及配置、PWM2/计时与设备绑定；再有限RX/取消恢复、ARM实际绘图及并行。此前62项主机检查、已知夹具ARM分析和P32有限RX均不能替代此新硬件验收。

58条CDC及7输入/29输出外部延迟缺项保留；固定RF配置试验不进行活动DMA期间动态切钟。失联根因、连续完整IQ、真实AI、整机验收仍开放。
'''
    (ROOT/'docs/handoff/RESUME-20261021.md').write_text(handoff,encoding='utf-8',newline='\n')
    print('P35 summary and resume state saved; no board operations')

if __name__=='__main__':main()
