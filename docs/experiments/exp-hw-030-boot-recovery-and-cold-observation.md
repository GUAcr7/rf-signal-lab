# HW-030：重启恢复、取消重启与一次人工断电观察

日期：2026-10-21晚（北京时间）。P39精确最终二进制777b93620f211f4e516c5a17a1bc703c6da06663a9afeff9c9a1c3fe72f4c925未改；新增恢复验证、源代码复位审查及只读现场采集工具，没有启动TX。

## 完成结论

1. `results/p32-preflight-20261021T144219Z/report.json`：两板在线，旧板boot=3bcec2b6-df8d-479b-8c1f-d989bfc61c0a、新板原P39 boot=3c107af6-dcab-4ab0-8269-7f0f3a050390，RF idle、taint0。
2. `results/p40-factory-boot-20261021T144656Z/report.json`：普通软件重启回厂家RF，boot=495a5051-3def-4463-8125-5695f677ddcb。原guard/固件/DTBO哈希未变，恰好一次overlay attempt1，RF三个名字完整，无fb0、taint0。该次无0xFF；只属warm boot，不当冷启动根治证据。
3. `results/p35-once-merged-20261021T144840Z/report.json`：另一次新hold启动，guard先恢复，空绑定后单次PL+overlay，boot=7eabc5bd-15ea-40a4-809f-19fe0505a63b。`results/p40-recovery-suite-20261021T145145Z/report.json`完整17阶段通过：新boot时钟、配置读回、8轮cancel/recreate、稀疏布局/绘图、3秒监测、SIGTERM取消、再运行120秒，以及三个保留前缀和屏幕归档/NumPy。
4. `results/p40-cold-cycle-ready-20261021T150315Z/report.json`：独立核验三份前缀和屏幕均在电脑，RX idle，正常poweroff至System halted；只操作新板，旧板未关机。
5. 用户回复“新板已断电并重新上电”，单独保留`results/p40-record-20261021T153552Z/human-power-cycle.json`。最初`results/p32-preflight-20261021T150638Z/report.json`未建立shell，原件保留；随后`results/p40-cold-observe-20261021T150742Z/report.json`收到DHCP/Xserver/登录信息，不能把第一次空响应计为RF失败。原厂RF-only模式下Xserver提示缺fb0属该模式缺屏幕节点，不是合并绘图故障。
6. `results/p32-preflight-20261021T150823Z/report.json`：新boot=224b7c4a-5ff4-404d-bb38-56274893858b，原厂PHY/ADC/DDS就绪、buffer/scan全0、taint0，无0xFF。断电动作来自用户报告，没有仪器确认全部电源轨放电或复位脉冲，因此仍不能认定冷启动缺陷已根治。
7. `results/p35-once-merged-20261021T150934Z/report.json`：按安全新hold路径恢复合并配置，boot=cebdb199-ca75-4df5-9d4c-9c4f94e9f08f。`results/p40-recovery-suite-20261021T151149Z/report.json`又完整通过17阶段。接收取消后再建会话并完成两分钟，最终C二进制本身现在也有完整120秒实板证据；不是沿用修UI前的SHA。

## 最新两分钟结果

{
  "schema": "rfsig.latest_panel.v1",
  "status": "pass",
  "reason": "duration_complete",
  "duration_ms_requested": 120000,
  "UI_interval_ms_requested": 500,
  "elapsed_software_s": 120.006313,
  "published_prefixes": 56252,
  "consumed_prefixes": 235,
  "last_display_sequence": 56027,
  "UI_overwritten_prefixes": 56016,
  "pending_prefixes_at_stop": 1,
  "display_updates": 235,
  "retained_prefix_bytes": 32768,
  "prefix_frames": 8192,
  "frames_per_refill": 65536,
  "source_format": "le:S12/16>>0",
  "worker_started": true,
  "worker_joined": true,
  "refill_error": 0,
  "buffer_created": true,
  "buffer_released": true,
  "context_released": true,
  "cleanup_unconfirmed": false,
  "RF_before_valid": true,
  "RF_after_matches": true,
  "RF_attributes_written": false,
  "TX_API_loaded": false,
  "lossless_proven": false,
  "ADC_gaps": "unknown",
  "analyse_only": false,
  "maxrss_kib": 2688
}

以上为机器摘要，始终按published=consumed+UI overwritten+pending核验。单上下文/缓冲反复refill，UI每次只取最新8192帧前缀，最后一帧32KiB保存；不是全流保留或ADC无丢样证明。

全部child路径及SHA在两份suite报告；最后归档与独立复核：`results/p39-offline-review-20261021T151747017877Z/report.json`。最终framebuffer已查看，上下状态均RX STOPPED；它不是实物照片。P39用户确认实体运动保留原作用范围，不扩展成P40全程物理FPS测量。

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

正在准备/执行一次性板端自主启动：`results/p41-autonomous-once-20261021T153301Z/report.json`。它会在新boot先恢复原guard，再由板端装已固定哈希的合并PL/overlay并启动有界接收显示；不改变长期默认模式。继续前先读此报告实时status、pending wrapper与boot字段。此前完成boot不能代表此试验当前状态；完成后另写HW-031/P41状态，未验收前不宣布开机自动显示完成。

仍未关闭：厂家0xFF根因、长期稳定性/故障自恢复、ADC连续性、58项CDC与外部7输入/29输出缺延迟、永久可回退独立开机显示、已知信号质量与真实AI。
