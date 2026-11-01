# P35：TTL 专用 33MHz 候选的全新综合与布线

日期：2026-10-21 00:01–00:24（北京时间）。本项只操作电脑侧新副本 `E:/p33-ttl-114312`，没有生成位流、改板端文件、操作串口或加载 FPGA。P30/P32 关键文件前后哈希一致。

## 结论与范围

P33 创建的 **PWM2 + TTL 专用 + 初始33MHz** 副本已完成全新 IP 生成、OOC/顶层综合及布线。综合网表和布线网表都通过实际时钟/层次守卫：FCLK0=100MHz、FCLK1=200MHz，ClockWiz 输入/AXI分别继承这两路时钟，`lcd_pclk` 单一派生时钟周期30.303ns，无辅助LVDS/PLLE2支路、无旧半频约束、无未解析单元。

这是独立于 P34 旧148.5MHz/PWM2构建的新结果。它消除了未用辅助LVDS PLL在33MHz模式下超出输入范围的结构，不证明屏幕、射频或二者并行已经上板验收。

| 指标 | 本轮实际值 |
|---|---:|
| 综合原生退出 | 0 |
| 布线原生退出 | 0 |
| 路由后 WNS / WHS | **+0.490 / +0.054ns** |
| setup / hold / pulse-width 失败端点 | **0 / 0 / 0** |
| 可布线网络 / 完成网络 | 52,409 / 52,409 |
| 路由错误 | 0 |
| 内部未约束端点 / 无时钟寄存器 | 0 / 0 |
| 现有43条 bus-skew 摘要的最小余量 | +3.965ns |
| LUT / FF / BRAM / DSP | 21,836 / 38,376 / 12.5 / 69 |

原生“全部用户指定约束满足”只涵盖已经声明的条件。**仍有7路输入、29路输出缺外部时延；CDC仍有58条 Critical。** 本轮没有增加假设时延、false-path或CDC豁免，没有并入仍需独立收口的 `sync_id` 注册候选。

## 真实证据

- [综合报告](../../results/p35-ttl-synth-20261020t160148z/report.json)，[独立摘要](../../results/p35-ttl-synth-20261020t160148z/post-summary.json)。综合阶段未布线，WHS=-0.190ns，不应把综合完成误写成物理时序通过。
- [布线报告](../../results/p35-ttl-route-20261020t161703z/report.json)，[独立摘要](../../results/p35-ttl-route-20261020t161703z/post-summary.json)。摘要验证了11份原生报告SHA。
- [布线时序](../../results/p35-ttl-route-20261020t161703z/timing.rpt)、[路由状态](../../results/p35-ttl-route-20261020t161703z/route-status.rpt)、[bus-skew](../../results/p35-ttl-route-20261020t161703z/bus-skew.rpt)、[CDC](../../results/p35-ttl-route-20261020t161703z/cdc.rpt)、[外部缺项](../../results/p35-ttl-route-20261020t161703z/check-timing.rpt)。同目录保留DRC、时钟关系、IO、方法学、资源、精确执行Tcl与输入快照。
- 布线 DCP：`E:/p33-ttl-114312/p35-ttl-route.dcp`，28,715,676字节，SHA256 `214243e43c4e5f2c234e17c8c04f6c17c408d89248cc63cf56f1b4d21bfa096e`。
- BD未改变：SHA256仍为 `c373bacbfc2acc6213b60988d100f49b1a66781a009678e4a59218d99efc46f3`。

## 计数与解释纠错

1. **DRC的58条 Advisory不是CDC的58条Critical。** 路由后DRC有24条Warning（CHECK-3=1、DPIP-1=2、REQP-1839=20、RTSTAT-10=1）和58条Advisory（AVAL-4=56、REQP-181=2）。独立 `report_cdc` 则报告 CDC-1=50、CDC-10=4、CDC-12=2、CDC-13=2，总计58条Critical。两组恰好同数，不能互相代替。
2. 首版构建脚本误按带竖线表格解析CDC摘要，因此原始两份 `report.json` 的 `CDC_summary_lines` 为空。**它不是“CDC=0”。** 原生完整报告始终保留，`p35_summarize_ttl.py` 正确读取原生文本格式并在独立 `post-summary.json` 写出58条Critical；后续构建脚本也已修正。没有覆写已执行脚本快照和原始报告。
3. WHS从旧候选13ps变为本候选54ps是本次布线结果，不能把它当成所有运行模式、板级外部时序或温度条件的最终签署。

## 后续依赖

1. 保留当前外部时延及CDC未关闭限制；决定先对注册候选做新的独立构建，还是按经审查的有限工程试验条件继续。
2. 使用匹配TTL33/PWM2、FCLK0/1、IRQ/地址及VDMA时钟名的设备树；不能简单拼接厂家树后假定与本候选兼容。
3. 只有明确试验边界和回滚路径后才单独生成裸 `.bin`，记录位流格式/哈希和配对设备树；本轮未执行。
4. 新启动单次加载，先验证时钟LOCK/实际频率、背光通道2、显示和计时，再有限RX，再并行。PL加载不会自动执行Vivado的PS初始化，须重新读回运行时FCLK；不能复用上次启动的读数。
