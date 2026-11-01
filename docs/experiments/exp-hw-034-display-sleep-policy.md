# HW-034：修复独立显示终端被桌面休眠关闭背光

日期：2026-10-22。当前boot `4a6b80d6-bbb5-499b-90ae-e403d1492a6e`。本轮未修改P37 FPGA/设备树或P42原生接收程序，旧P201未启动发射。

## 结论与证据

用户先反馈实体屏全黑、无明显背光。诊断时X显示查询为Monitor Off、DPMS Enabled，待机/挂起/关闭均600秒，控制台consoleblank=600；PWM2被请求但关闭、duty0。与此同时显存和接收程序有数据。因此撤回旧的整机实体显示冷启动通过结论，保留原机器证据。

正常X显示唤醒并关闭本会话休眠后，PWM2恢复enabled、period50000ns/duty50000ns，用户直接回复“亮起，能看到RF SIGNAL LAB或频谱”。这是本次黑屏受显示休眠控制且可恢复的直接证据；不推断所有黑屏都只有这个原因。

- 原失败反馈：`results/p44-human-display-failure-20261022.json`。
- 休眠状态：`results/p44-display-state-20261022T035717Z/report.json`；唤醒操作：`results/p44-wake-20261022T035907Z/report.json`。
- 人工唤醒确认：`results/p44-human-wake-confirmation-20261022.json`。
- 首次安装：`results/p44-policy-20261022T040536Z/report.json`保留failed原结果。其服务停止后立即检查时xinit尚未完成退出；后续独立读回确认退出，不能改写原失败为通过。
- 安装补验/下一次启动选择准备：`results/p44-prepared-20261022T041040Z/report.json`；独立桌面退出读回`results/p44-display-state-20261022T040848Z/report.json`。
- 修复后一次全新软件重启：`results/p43-boot-cycle-20261022T041103Z/report.json`。板端自行初始化并启动，主机登录后观察及停止；运行741.085秒、更新1451次、RSS高水位2576KiB。
- 最后实际显示的32KiB IQ、framebuffer、同boot时钟寄存器/驱动率及独立NumPy核对：`results/p42-review-20261022T042442Z/report.json`。
- 超过原600秒后，独立只读检查consoleblank0、没有Xorg/xinit、策略marker匹配当前boot、PWM2仍enabled：`results/p44-verified-20261022T042548Z/report.json`。这是软件/背光状态验收；不冒充光学测量。
- 超过600秒的实体可见性人工确认：**True**。若False，保留为待验收，不能用显存截图替代。

## 持久实现

`/etc/init.d/xserver-nodm`改为SHA固定的条件入口，原厂家脚本精确备份在`/etc/p44-20261022T040536Z/xserver-original`。只有当前boot的P43标记、PERSISTENT_MONITOR_READY及进度文件全部存在时，由RF framebuffer终端占有显示，停止自身桌面服务，跳过X启动。通过标准VT转义将控制台blank/powerdown关闭，再用fb blank接口解除blank；不直接改PWM寄存器、不热卸任何驱动。不满足RF条件时仍委托原厂家X入口，stop也委托原入口。

策略及helper SHA固定在`results/p44-prepared-20261022T041040Z/report.json`和最终校验报告；关机/重启不会丢失这些/etc文件。/run的进度和原始前缀仍会丢失，故已回传电脑。本轮测试结束后暂时恢复原S99board供通用归档工具严格检查，复核完成后重新选择同一P43持久wrapper：`results/p43-enabled-20261022T042604Z/report.json`。最终只读状态`results/p43-status-20261022T042632Z/report.json`确认RX idle、buffer/scan0、taint0、无pending/disabled；未再关机。下次新boot会尝试自动接收/绘图。

## 验证范围及开放项

9项真实POSIX shell用例检查RF/其他模式分流、原入口委托、hash/唤醒失败；4项检查显式历史安装快照必须精确匹配，7项检查最新软件启动重新启用门禁。连同P43启动停止和P42运行归档门禁，本轮39项通过，`results/p44-final-gates-20261022.xml`。主机观察器增加有界20..900秒窗口，未放松原硬件新boot/空绑定/时钟/归档检查。测试XML及原始运行脚本随检查点保存。

修复后尚未再次人工真断电；不能声称冷启动实体显示已闭环。厂家0xFF偶发启动根因、实板故障回退、CDC/外部IO时序、物理PCLK测量、已知源质量波动、ADC无损连续性和真实AI仍开放。本轮十二分钟不等于24小时稳定性；外层24小时只是安全终止上限。
