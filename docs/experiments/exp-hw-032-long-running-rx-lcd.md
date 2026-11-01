# HW-032：长时间接收、内存进度文件与安全停止

日期：2026-10-22（北京时间）。本轮仅修改应用及其验收/归档工具，硬件沿用P37安全M16.5/D2/O25。

## 本轮结论

**三秒短测、duration=0直到信号停止、停止后重启并运行十分钟均通过。** 长测实际600.002秒、1175次分析/写屏；原生程序最终日志701字节，收到57次有效进度快照。结束后独立确认RX buffer/scan全0、taint0、RF参数和boot不变、串口关闭。三个会话的最后显示原始前缀均回传电脑，NumPy峰值/bin/RMS/频谱总功率核对通过；长测另有同boot时钟后验和framebuffer归档。

长测最大RSS 2572 KiB；这是本进程的高水位和有限时间观察，不能证明任意时长无泄漏。屏幕回读图：`results/p39-offline-review-20261022T025041824575Z/screen.png`（不是实物照片）。本轮没有再次向用户确认实体动画，不沿用P39的人工确认冒充本轮验收。

权威suite：`results/p42-suite-20261022T023816Z/report.json`，状态`passed_short_until_signal_stop_restart_10min_and_archived_review`。新板boot `eceb52df-5184-4bcf-ba61-238569e8bbd6`；旧板本轮仅重新认板，没有发起TX。当前没有已知源输入保证，所有频谱功率均为数字计数域，不是dBm或已识别目标。

## 恢复与实现

- 上电只读识别：`results/p32-preflight-20261022T022119Z/report.json`，两板在线，新板厂家RF_READY，taint0、空闲。
- 新hold启动：`results/p35-once-merged-20261022T022336Z/report.json`。先恢复原S99board，验证fresh/空绑定门槛，再单次PL+单次显式overlay；没有热卸驱动。默认固件、BOOT及board-mode未替换。
- 基础suite：`results/p40-recovery-suite-20261022T022826Z/report.json`。新增`--baseline-only`，只验证当前boot时钟、RF、8轮取消重建、layout和静态写屏；用不同通过状态，不能当完整P40长测通过，也不能绕过P41执行器的完整suite门槛。
- 新C源`embedded/arm_live_panel_p42/arm_live_panel_p42.c`从P39独立派生，旧P39源未改。一个libiio上下文和65536帧缓冲反复refill；只复制前8192帧到最新信箱，UI按500ms请求间隔取最新前缀分析/写屏，UI覆盖计数与ADC丢样无关。
- 原生duration=0表示直到SIGTERM；正值支持至24小时，但仅本轮十分钟完成过实板验收。主机验收工具对duration=0强制要求有界取消时间，另有拥有者PID/命令行校验及timeout后备。
- 每次更新将小于4096字节的`progress.next`关闭后rename为`progress.json`，只保留最新一份；最终再写完成态。stdout只保留启动、最后指标/序号和结束行，取消每帧历史打印。最终保存最后真正显示前缀32768字节，未保存整段流或所有画面。
- 持续写入目录为`/run/p42-HHMMSS`，实读`/proc/mounts`确认/run为tmpfs后才允许运行，无写SD/tmp的退路。上传只经已有白名单`/tmp/p35-p42-*`暂存，校验后复制到/run；暂存不是持续日志。
- 任一进度写失败即停止，cancel→有期限join→释放buffer/context；不能join时拒绝声称清理完成。最终summary、progress、独立idle读回共同验收，不凭遗留running快照宣布通过。

## 测试与证据边界

- `results/p42-build-20261022T022745Z/report.json`：21项原生mock测试及ARMhf构建通过，GLIBC兼容检查通过；包括真实信号取消、原子快照并发读取、进度写失败、错误layout/版本/RF漂移和卡住线程。mock不替代实板。
- `results/p42-common-gates-20261022.xml`：8项主机门槛测试通过，覆盖P42计数/NaN/单调性、同boot及严格归档白名单；保留P38/P39/P41原规则。
- `results/p42-final-common-gates-20261022.xml`：补上主机duration0必须有界取消/非法时长在访问板卡前拒绝，并覆盖原summary、产物复用和boot门槛，共40项通过。
- 长测结束后另行只读检查运行目录：固定9个文件，含monitor/launcher/PID/退出码/log、最终progress/summary/原始前缀/其gzip，无历史序列或progress.next残留；总占用128KiB，log701B、progress433B。具体证据`results/p42-runtime-readback-20261022T024946Z/report.json`。这些数值只属于本次已完成的长测。运行阶段快照RSS高水位2452KiB，结束保存后最终2572KiB，不把收尾增加误写成全程恒定，也不声称任意时长无泄漏。
- `results/p42-suite-20261022T023816Z/report.json`按单串口owner顺序执行：短测原始字节归档与NumPy，duration0 SIGTERM及独立idle，取消会话归档与NumPy，重启十分钟，然后时钟后验、最后IQ与屏幕归档、独立NumPy。
- 每份子报告同目录保留executed.py、命令/退出码、原始UART读写和源/产物SHA。失败记录不删除。只保留各会话最后显示的32KiB原始数据，不是十分钟完整IQ。
- ADC gaps unknown、lossless=false；没有ADC序号/overrun独立证明，软件UI覆盖不能解读为硬件丢样；写屏次数不能称实体LCD FPS；时钟软件/寄存器一致不替代物理PCLK测量。

## 后续依赖

1. 在不削弱fresh/empty/guard/hash门槛的前提下，把P42已验证应用接入可回退的持久启动；显式启动状态、只读禁用/恢复路径、禁止热重载。先隔离shell负例，再有限时长启动实测，最后才扩大运行时长。
2. 对该最终启动版本另做真正断电验收及RF启动0xFF成功/失败对照，软件重启不能替代；目前0xFF根因没有关闭。
3. 后续已知源质量/指标、真实AI及其显示联调；58项关键CDC、7输入/29输出外部时序缺项、ADC无损连续性仍开放。不得因本次长测通过而抹掉这些边界。

最终framebuffer图已人工查看：标题、绿色频谱曲线和上下RX STOPPED均可读，update1175/source block281142；它是显存回读，不是实体屏幕照片或动画确认。
