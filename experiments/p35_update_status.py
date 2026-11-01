"""Record evidence-scoped P35 state; preserve the superseded entry files."""
from datetime import datetime,timezone
import json
from p32_session import ROOT

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-status-correction-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    paths=['START-HERE.md','TX-SOURCE-STATUS.json']
    for name in paths:(out/name).write_bytes((ROOT/name).read_bytes())
    data=json.loads((ROOT/'TX-SOURCE-STATUS.json').read_text('utf-8-sig'))
    for key in ['p34_bisect','p34_bisect_rf_half','p34_session_close']:
        data[key]['historical_claims_superseded_by']='p35_current'
    package=data['p34_deploy_package']
    package.update(deployment_allowed=False,deprecated=True,
        never_loaded_on_board=False,
        format_correction='Original .bin is a .bit container; payload equals native raw only after parsed header extraction.',
        rollback='No hot unload. Use verified one-shot boot hold and normal reboot to hash-verified factory files; U-Boot recovery only when required.',
        notice='results/p34-deploy-package/DEPLOYMENT-BLOCKED.json')
    current=dict(updated_utc=datetime.now(timezone.utc).isoformat(),
        record='docs/experiments/EXP-HW-025-review-corrections-and-ttl.md',
        status='finite_RX_verified_TTL33_build_in_progress_combined_init_root_cause_open',
        board_readback='results/p35-firmware-readback-20261020T155937Z/report.json',
        vendor_file_restore='results/p35-restore-vendor-files-20261020T160202Z/report.json',
        RX_configuration='results/p35-finite-rx-prep-20261020T160650Z/report.json',
        RX_cancel_recreate='results/p33-rx-cancel-board-20261020T160708Z/report.json',
        RX_finite_sparse='results/p27-smoke-20261020T160826Z/report.json',
        new_board=dict(port='COM8',boot_id='8033ec3f-0588-4e7a-8572-e440c547cf43',
            running_fabric='P32 PWM2 merged design from P34; not TTL33',
            running_overlay='factory RF pl.dtbo',framebuffer_present=False,
            disk_default_firmware='restored hash-verified factory originals; no reboot yet',
            mode='rf',RX_LO_Hz=2450000000,RX_gain_mode='manual',RX_gain_dB=0,
            latest_cancel_postcheck=dict(tainted=0,buffer_enable=0,scan_enable=[0,0,0,0]),
            serial_closed=True),
        old_board=dict(port='COM9',boot_id='182e235d-a1d2-4964-856c-feb7ecf5873f',TX_app_observed=False),
        TTL33_candidate=dict(project='E:/p33-ttl-114312/project/combined.xpr',
            build='results/p35-ttl-synth-20261020T160148Z/report.json',status='building',
            ADI_sync_id_patch_applied=False,hardware_tested=False),
        explicit_overlay='results/p35-explicit-overlay-20261020T160459Z/report.json',
        package_format='results/p35-package-format-audit-20261020T160521Z/report.json',
        conclusions=dict(combined_RF_display_verified=False,CDC_closed=False,
            hang_root_cause_verified=False,continuous_lossless_IQ=False,real_AI_verified=False),
        serial_protocol='One owner per port; short commands with actual exit markers; no hot unload/reconfigure under bound drivers')
    data['p35_current']=current
    data['authoritative_current_field']='p35_current'
    (ROOT/'TX-SOURCE-STATUS.json').write_text(json.dumps(data,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    text='''# 从这里恢复项目工作

**2026-10-21 P35更新。当前机器状态以`TX-SOURCE-STATUS.json`的`p35_current`为准。P32/P34字段仅保留各自历史作用域。**

先读[本轮实际纠错与补验](docs/experiments/EXP-HW-025-review-corrections-and-ttl.md)、[独立审查](docs/experiments/P35-p34-independent-audit.md)、[设备树候选与加载步骤](docs/experiments/P35-overlay-audit.md)。

- P34的工具授权/位流生成成功是真实进展；两种厂家树分别probe成功也成立。**“PL完全正常、CDC已排除、唯一坏设备树”证据不足，已经撤回。** 合并初始化失联的根因未确定。
- 新板当前串口可响应，boot=`8033ec3f-0588-4e7a-8572-e440c547cf43`；运行P32 PWM2合并PL+厂家RF树，无fb0。三份默认磁盘固件及厂家DTBO已核验/恢复；尚未重启，不能说运行PL也恢复厂家。
- 同一启动中8轮RX取消/重建、每轮重建后2次refill，以及随后16缓冲有限采集通过；结果和范围见本轮记录。采集仅保存1.5625%稀疏样本，完整连续IQ和已知信号质量未验收。未启动TX。
- 旧部署包`results/p34-deploy-package`已停用，旧部署脚本立即退出3。原“.bin”是带头`.bit`，原始文件保留取证。新的变长头解析与原生bin对比已完成；禁止把124字节当通用规则。
- 新TTL33/PWM2副本`E:/p33-ttl-114312/project/combined.xpr`在重新构建，移除未用LVDS分支、初始像素33MHz。**不要引用P30/P34的148.5MHz时序作为本候选结果。** 配对候选`fpga/integration/rf-display-p35-explicit.dts`要求先显式装PL再应用设备节点，电脑FDT已验证，上板未验证。
- 面板程序已修复功率归一化、计时及framebuffer布局检查，主机回归与ARM交叉编译结果见独立审查；旧2.34ms只是旧绘制段时间，不能声称接收/分析/显示整条链速度。
- **继续禁止热卸载RF overlay/PWM驱动，禁止在驱动绑定时重配PL。** 下次合并试验走一次新启动hold，先恢复启动保护、确认无驱动/overlay，再分步装匹配bin和DTS。失败通过普通重启回厂家文件；失联才用既有U-Boot恢复办法。
- CDC、外部IO时序、冷启动0xFF、旧内核卸载缺陷、RF/屏幕/触摸并行、真实AI与整机性能仍未全部验收。即时起流DMA疑点保留；不以加等待或消告警代替根因修复。

`results/`被gitignore排除，必须直接读文件系统。再次断电后重新认板、读取boot_id与文件哈希，不重放绑定旧boot的脚本。需要停机时先正常关机，再断电。
'''
    (ROOT/'START-HERE.md').write_text(text,encoding='utf-8',newline='\n')
    report=dict(status='current_entry_corrected',snapshot=str(out),authoritative_current_field='p35_current')
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out)

if __name__=='__main__':main()
