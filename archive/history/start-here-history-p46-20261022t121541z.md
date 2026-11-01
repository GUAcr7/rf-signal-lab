# 从这里恢复项目工作

**当前阶段P46：已知射频源质量复测进行中。** 先读[HW-036](docs/experiments/exp-hw-036-merged-known-rf-quality.md)、[P46恢复清单](docs/handoff/resume-p46-20261022.md)及p46_current/results/p46-active.json。四种峰值256的限时发射和完整RX1缓冲采集均已结束，原生TX清理及RX释放确认；全部原始IQ回传、离线质量判定仍在进行。COM8由归档任务独占。为严格归档校验，下一次S99board选择暂时是原guard，归档后须重新启用持久wrapper；未重启/卸驱动/重配PL。下方P45为已完成父检查点，不代表本轮已恢复自启动。

**当前入口：P45受控断电验证（2026-10-22）。** 先读[HW-035](docs/experiments/exp-hw-035-cold-display-verification.md)、[P45恢复步骤](docs/handoff/resume-p45-20261022.md)和p45_current。修复后一次人工真正断电，零UART发送被动记录新启动，板端自行接收/频谱显示724.5秒、1419次更新。原始IQ/显存、时钟和防休眠状态复核通过；600秒后实体屏仍亮且动态更新的人工确认=True。

当前RX idle、串口关闭、板仍通电，未再次关机；持久启动及防休眠策略已启用。一次成功不代表0xFF根因、故障回退、全流连续性或真实AI已通过。下方所有旧停工/关机/等待断电/旧boot均为历史，不重放旧命令。

---

**P45受控冷启动验收进行中：** 用户已确认真正断电再上电；零UART发送捕获新内核及READY，新boot `343afe82-88e6-4a03-a5d4-c09ee6929e36`已自动接收超过600秒，用户确认实体屏仍亮且持续更新。当前试验`results/p43-cold-cycle-20261022T104726Z/report.json`观察至720秒并受控停止，COM8由该试验独占；后验IQ/显存/时钟及最终保存仍待完成。下方等待人工断电/旧关机说明均为历史，不再另发启动或装PL命令。

**P45待人工断电：** 新板正常关机已确认System halted，数据/代码及准备已保存。零输入被动启动监听窗口已再次开启，最长600秒，实时报告和COM8 owner见`results/p45-active.json`。先检查该报告是否serial_closed；监听未关闭时不要打开第二个COM8。用户完成电源操作后，先收取被动启动记录，再只读检查新boot和自动接收；不要先发重启/装PL命令。首个空监听窗口不算硬件失败，受控冷启动尚未通过。

**最新状态：新板已正常关机，等待人工真正断电再上电做P45冷启动验证。** 记录`results/p45-power-cycle-prepare-20261022T102927Z/report.json`已确认System halted；旧P201板未操作。P43持久wrapper及P44显示策略仍启用，最后boot只是停机前历史。接电后先按当前恢复说明只读认板/新boot/首次进度；不先重启、不热重装。下方“板仍通电/未关机”是此前历史状态。

**最新停工保存（P44）：** 用户要求下次继续。先读[停工记录](docs/handoff/stop-p44-20261022.md)和p44_current。接收停止、资源释放、串口关闭；**板卡仍通电，未执行关机。** 自动启动及防休眠设置已保存。下次首先做修复后的真正断电及十分钟以上实屏验证，不重放旧boot。

**当前入口：P44显示休眠修复（2026-10-22）。** 先读[HW-034](docs/experiments/exp-hw-034-display-sleep-policy.md)、[P44恢复步骤](docs/handoff/resume-p44-20261022.md)及TX-SOURCE-STATUS.json的p44_current。已定位桌面DPMS在600秒后关闭背光；用户确认正常唤醒后屏幕亮起。条件启动策略已持久保存，修复后一次全新软件启动运行741.1秒、更新1451次，超过600秒的背光/无X/consoleblank0读回及IQ/显存/时钟独立复核通过。超过600秒实体可见人工确认=True；**修复后真断电尚待验收**。

当前RX idle、串口关闭、板仍通电，未关机；P43持久wrapper和P44显示策略均已启用。下次新boot会尝试自动初始化接收/绘图。0xFF根因及其他项目开放项未关闭。旧P43“整机冷启动通过”已被实体黑屏反馈撤回，以下所有旧“当前”均为历史；不要重放旧boot或热卸驱动/重配PL。

---

**P44正在做修复后的十二分钟新启动验证。** 当前会话见`results/p43-active.json`，试验`results/p43-boot-cycle-20261022T041103Z/report.json`；COM8由该试验独占，不另开串口。用户已确认正常唤醒后屏幕亮起；条件X启动策略已安装并读回，`results/p44-prepared-20261022T041040Z/report.json`。本轮尚未完成后验归档/重新启用及修复后真断电验收，下方只读诊断/P43旧状态都是历史。不要重复启动或操作PL/驱动。

**最新纠正：用户反馈P43冷启动后实体屏幕完全黑、无明显背光，实体显示未通过。** 先看`results/p44-human-display-failure-20261022.json`。接收/显存/时钟机器证据只在原范围成立，不能由下方“冷启动验收”推断实体屏幕正常。P44正在只读诊断，不重启或热卸驱动；后续以新记录为准。

**当前入口：P43已完成两次软件重启及一次人工断电验收，持久自启动已启用（2026-10-22）。** 先读[HW-033](docs/experiments/exp-hw-033-persistent-startup.md)、[P43恢复步骤](docs/handoff/resume-p43-20261022.md)和TX-SOURCE-STATUS.json的p43_current。当前RX已停止、板仍通电、串口关闭；S99board现在是已固定SHA的P43 wrapper，下次新boot会尝试自动初始化和接收/频谱显示。本轮一次真断电已验证，故障回退实板验证仍待做，0xFF根因未根治。

**不要按下方P42/P41历史说明恢复原guard或判定“普通重启仍仅RF-only”。** 先用P43只读status核对当前wrapper/boot/latch；禁止热卸驱动或在已绑定时重配PL。下方等待人工断电、P43正在推进及更早状态均为历史，以本段与p43_current为准。

**最新状态：新板已正常关机，等待人工真正断电再上电做P43冷启动验证。** 记录`results/p43-power-cycle-prepare-20261022T032530Z/report.json`已确认System halted；旧P201板未操作。P43持久wrapper仍启用，最后boot只是停机前历史。接电后先按P43恢复说明只读认板/新boot/首次进度；不先重启、不热重装。下方“板仍通电/未关机”是此前历史状态。

**当前入口：P43已完成两次软件重启验收，持久自启动已启用（2026-10-22）。** 先读[HW-033](docs/experiments/exp-hw-033-persistent-startup.md)、[P43恢复步骤](docs/handoff/resume-p43-20261022.md)和TX-SOURCE-STATUS.json的p43_current。当前RX已停止、板仍通电、串口关闭；S99board现在是已固定SHA的P43 wrapper，下次新boot会尝试自动初始化和接收/频谱显示。真断电及故障回退实板验证仍待做，0xFF根因未根治。

**不要按下方P42/P41历史说明恢复原guard或判定“普通重启仍仅RF-only”。** 先用P43只读status核对当前wrapper/boot/latch；禁止热卸驱动或在已绑定时重配PL。下方“P43正在推进”及更早状态均保留为历史，以本段与p43_current为准。

**P43正在推进（2026-10-22）：** 开机自启动与回退试验，先读`results/p43-active.json`及其指向报告；该报告若提示wrapper可能已安装或native完成未确认，不再打开第二个COM8 owner、不重放P42旧boot。下方P42是已完成的父检查点，不能代替当前板卡状态。成功停机归档时会暂时恢复原S99board，最终是否重新启用必须看本轮交接。

**当前入口：P42（2026-10-22）**。先读[HW-032](docs/experiments/exp-hw-032-long-running-rx-lcd.md)、[P42恢复步骤](docs/handoff/resume-p42-20261022.md)及TX-SOURCE-STATUS.json的`p42_current`。状态以其指向的实际suite报告为准；下方P41停机及其他“当前”字样均为历史。今天两板已重新上电，新板重新建立P37合并配置。

**普通重启仍回厂家RF-only，不是永久自动显示。** 不重放旧boot，不热卸ADC/PWM/显示驱动，不在驱动绑定时重配PL。`results/`不在Git，须直接读文件系统。当前运行是否结束以P42报告为准，不能照搬昨天的“已关机”。

**最新停工保存：** `results/p41-session-stop-20261021T155249Z/report.json`；两板正常halt确认=True，未关闭电脑。先读[停工/下次接线说明](docs/handoff/stop-p41-20261021.md)，下方P41运行状态为停机前历史。

**P41为当前状态（2026-10-21晚）：** 先读[HW-031](docs/experiments/exp-hw-031-autonomous-once-startup.md)、[P41恢复清单](docs/handoff/resume-p41-20261021.md)及TX-SOURCE-STATUS.json的p41_current。一次性板端开机初始化+120秒接收/频谱写屏通过，电脑登录后没有发送启动应用或装PL命令；新boot时钟后验、IQ/屏幕归档和NumPy复核通过。原guard已在装PL前恢复，当前RX正常停止、串口关闭。用户本次只看到RX STOPPED，P41动态人工确认不算通过。

**下次普通重启仍回厂家RF-only，不会永久自动显示。** P41是一次性有限时长试验，长期运行/安全停止/有界日志和可回退持久启动仍待做；0xFF根因、CDC/外部时序、无损连续性、已知源质量和真实AI仍开放。下方P40“试验进行中”及更早“当前”段均为历史，已被本段与p41_current取代，不重放历史boot命令。

**P41为当前状态（2026-10-21晚）：** 先读[HW-031](docs/experiments/exp-hw-031-autonomous-once-startup.md)、[P41恢复清单](docs/handoff/resume-p41-20261021.md)及TX-SOURCE-STATUS.json的p41_current。一次性板端开机初始化+120秒接收/频谱写屏通过，电脑登录后没有发送启动应用或装PL命令；新boot时钟后验、IQ/屏幕归档和NumPy复核通过。原guard已在装PL前恢复，当前RX正常停止、串口关闭。用户本次只看到RX STOPPED，P41动态人工确认不算通过。

**下次普通重启仍回厂家RF-only，不会永久自动显示。** P41是一次性有限时长试验，长期运行/安全停止/有界日志和可回退持久启动仍待做；0xFF根因、CDC/外部时序、无损连续性、已知源质量和真实AI仍开放。下方P40“试验进行中”及更早“当前”段均为历史，已被本段与p41_current取代，不重放历史boot命令。

**P40已完成，P41试验进行中（2026-10-21晚）：** 先读[HW-030](docs/experiments/exp-hw-030-boot-recovery-and-cold-observation.md)、TX-SOURCE-STATUS.json的p40_current及`results/p41-autonomous-once-20261021T153301Z/report.json`。两次新boot恢复suite、一次人工断电后的原厂RF就绪已验证，0xFF根因仍未关闭。P41还不是通过结论，不重放下方任何历史boot。

**P39为当前软件状态（2026-10-21晚）：** 先读[HW-029](docs/experiments/exp-hw-029-latest-prefix-rx-lcd.md)、[P39恢复步骤](docs/handoff/resume-p39-20261021.md)和TX-SOURCE-STATUS.json的p39_current。一个RX上下文/缓冲反复refill，最新前缀与频谱写屏分线程；两分钟235次更新、SIGTERM取消/释放及最后显示数据的独立NumPy复核通过，用户明确确认“这次可以看到运动的画面了”。已修复停止后顶部残留RX active，最终精确二进制另有3秒实板短测和回读证据。当前已停止、RX空闲、串口关闭，普通重启仍须按新boot初始化P37合并配置。

本轮五次会话只保留各自最后实际显示的32KiB原始前缀，均电脑归档，不是全流无损录制；ADC gaps未知，UI覆盖不是硬件丢样。厂家0xFF根因、长期稳定性、可回退自动启动、CDC/外部时序、已知源质量和真实AI仍未全部验收。P38停工保存包完整保留，作为历史父检查点；下方P38及更早“当前”字样均为历史状态，以本段和p39_current为准。

**停工保存（2026-10-21）：** 已补齐P38全部64轮及8轮原始数据并核验逐轮SHA。先读[停工与再次上电步骤](docs/handoff/stop-p38-20261021.md)，再按下方P38入口恢复。普通重启仍须重新初始化合并配置，不能复用旧boot。

**P38当前软件入口：以`TX-SOURCE-STATUS.json`的`p38_current`、[HW-028](docs/experiments/exp-hw-028-periodic-rx-lcd.md)及[P38恢复步骤](docs/handoff/resume-p38-20261021.md)为准。** 沿用已通过的P37硬件配置，新增板端周期采集/分析/写屏：8轮短测和64轮66.54秒测试通过，RX在每次采集后释放，再更新频谱；最后一轮数据与屏幕回读已电脑归档，独立NumPy数值核对通过。当前程序已自动停止，屏幕显示`RX STOPPED | last snapshot`。它不是持续无缝采集或长期稳定性验收，也没有设置开机自动启动；普通重启仍需按新boot恢复合并固件。P37实屏静态确认不能替代P38动画/刷新率确认。

**P37为当前硬件配置依据和上一软件检查点：** `TX-SOURCE-STATUS.json`的`p37_current`、[HW-027](docs/experiments/exp-hw-027-safe-clock32.md)及[恢复清单](docs/handoff/resume-p37-20261021.md)。安全时钟16.5/2/25已完成综合/布线及一次上板，driver/寄存器一致性验收通过；同boot完成8轮取消重建、有限接收、板端频谱绘图，用户明确确认实体屏幕标题/绿色曲线可见且稳定。完整16个返回缓冲的4MiB IQ及屏幕回读图已归档电脑并校验。冷启动0xFF、外部PCLK仪器测量、长期连续性和真实AI仍未验收。下次普通重启仍走原厂家RF模式，不自动恢复合并固件/显示应用；必须重新认板，禁止重放旧boot。不要把下方历史状态当成当前结论。

**以下P36为历史检查点，已由上方P37取代：** [历史结果及重要时钟问题](docs/experiments/exp-hw-026-fresh-boot-ttl33.md)及`TX-SOURCE-STATUS.json`的`p36_current`保留原始结论，不能用于当前恢复操作。

- TTL33/显式PL加载+无firmware overlay已同一次干净启动完成RF/DRM/PWM2初始化、8轮取消重建、有限RX和帧缓冲绘制。原主试验因虚拟800×960双缓冲误判而failed，原结果保留，成功依据是独立补验。
- **新定位32位时钟率溢出：软件33MHz与硬件影子分频不一致。修复候选M16.5/D2/O25还没有生成、构建或上板，不得宣布已根治或物理显示时钟通过。**
- 完整4MiB返回缓冲已板端保存，但电脑回传中断在15/53块。屏幕回读图已完整保存为`results/p36-file-archive-20261021T031834Z/screen.png`；它不是物理屏幕照片。
- 最近只读恢复会话COM8无回应，当前boot/运行状态未确认；串口已关闭，无后台采集/发射/回传程序被观察到。先重新认板，禁止盲重放旧boot。

**以下为P35历史检查点，不是当前状态；保留供追溯。**

先读[本轮实际纠错与补验](docs/experiments/exp-hw-025-review-corrections-and-ttl.md)、[独立审查](docs/experiments/p35-p34-independent-audit.md)、[设备树候选与加载步骤](docs/experiments/p35-overlay-audit.md)。

- P34的工具授权/位流生成成功是真实进展；两种厂家树分别probe成功也成立。**“PL完全正常、CDC已排除、唯一坏设备树”证据不足，已经撤回。** 合并初始化失联的根因未确定。
- 新板当前串口可响应，boot=`8033ec3f-0588-4e7a-8572-e440c547cf43`；运行P32 PWM2合并PL+厂家RF树，无fb0。三份默认磁盘固件及厂家DTBO已核验/恢复；尚未重启，不能说运行PL也恢复厂家。
- 同一启动中8轮RX取消/重建、每轮重建后2次refill，以及随后16缓冲有限采集通过；结果和范围见本轮记录。采集仅保存1.5625%稀疏样本，完整连续IQ和已知信号质量未验收。未启动TX。
- 旧部署包`results/p34-deploy-package`已停用，旧部署脚本立即退出3。原“.bin”是带头`.bit`，原始文件保留取证。新的变长头解析与原生bin对比已完成；禁止把124字节当通用规则。
- 新TTL33/PWM2副本`E:/p33-ttl-114312/project/combined.xpr`已完成综合/布线及原生裸bin导出（WNS+0.490ns/WHS+0.054ns），尚未配置上板，移除未用LVDS分支、初始像素33MHz。**不要引用P30/P34的148.5MHz时序作为本候选结果。** 配对候选`fpga/integration/rf-display-p35-explicit.dts`要求先显式装PL再应用设备节点，电脑FDT已验证，上板未验证。
- 面板程序已修复功率归一化、计时及framebuffer布局检查，62项主机回归/结构检查、ARM交叉编译及板端无屏已知夹具分析已通过；旧2.34ms只是旧绘制段时间，不能声称接收/分析/显示整条链速度。
- **继续禁止热卸载RF overlay/PWM驱动，禁止在驱动绑定时重配PL。** 下次合并试验走一次新启动hold，先恢复启动保护、确认无驱动/overlay，再分步装匹配bin和DTS。失败通过普通重启回厂家文件；失联才用既有U-Boot恢复办法。
- CDC、外部IO时序、冷启动0xFF、旧内核卸载缺陷、RF/屏幕/触摸并行、真实AI与整机性能仍未全部验收。即时起流DMA疑点保留；不以加等待或消告警代替根因修复。

`results/`被gitignore排除，必须直接读文件系统。再次断电后重新认板、读取boot_id与文件哈希，不重放绑定旧boot的脚本。需要停机时先正常关机，再断电。

**00:29汇总检查点**：用户要求先汇总，未完成上传已安全中止；新启动/新PL/新overlay均未执行，无后台任务会自动重启。串口echo及原guard核验恢复，当前boot未变、RF空闲、taint0。继续前读[本轮收尾段](docs/experiments/exp-hw-025-review-corrections-and-ttl.md)和[恢复清单](docs/handoff/resume-20261021.md)。
