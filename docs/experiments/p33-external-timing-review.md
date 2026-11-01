# P33：外部接口时序与实际 TTL 屏路径复核

日期：2026-10-20（北京时间）。范围：独立离线复核，不操作串口、板卡或软件界面；没有保存/修改 P30、PWM2 工程、原厂资料或项目入口状态。

## 结论

现有资料足以继续新候选综合、布线和受控工程验证，但不足以签署“全部外部接口时序已收敛”。P30 的 WNS/WHS 仅覆盖已经声明的约束。不能给缺失端口填零时延来消除告警。

另发现一个具体的运行模式问题：**800×480 的 33MHz 像素时钟会使继承的辅助 LVDS 串化 PLL 输入降至 16.5MHz。该 PLL 固定倍频14，其 VCO 变为约231MHz。实际 TTL 屏路径不依赖这颗辅助 PLL 或其锁定信号。** 因此优先做 TTL 专用候选，移除未使用 LVDS 分支，比为当前屏幕强行支持两种 LVDS 频率模式更直接。此结论不是板上屏幕故障定位；合并工程还没有上板。

原始复核：[报告与哈希](../../results/p33-timing-review-20261020t113053z/report.json)、[实际 DCP 端口/原语映射](../../results/p33-timing-review-20261020t113053z/clock-port-map.txt)、[33MHz 诊断模型](../../results/p33-timing-review-20261020t113053z/runtime-probe.tcl)。这些 Tcl 只打开旧 DCP、在内存中诊断、输出报告并退出，**不可当作部署 XDC**。

## 1. 物理屏幕与内部路径

实物照片确认 Tronlong **TL-70RESLCD-B2 转接板**，不能由此确定裸屏的精确型号。已有 TL070A 规格书第4页列模组 `070007T0-50`，第5页给出 RGB、800×480；这不是实物裸屏型号闭环。该10页规格书的产品参数/引脚页没有可用于签署 FPGA 输出时序的像素输入 setup/hold、采样边沿和最大/最小像素周期表。原有归档见[面板识别](../../board/display-identification/README.md)和[P31 提取页](../../results/p31-timing-sources-20261019t140648z/report.json)。

载板原理图 P15 / 第15页把两种显示接口明确分开：**CON14 是40pin RGB LCD FFC，CON15 是30pin LVDS**；PWM/背光另有 CON16。与照片中的宽FFC、电阻触摸线相符。该页还标出 RGB565→RGB888 连线。此项可确认接口路径，不能推出板/FFC传播延迟或裸屏时序。[原理图提取](../../results/p30-schematic-20261019t093956z/page-15.txt)。

实际 `E:/p32-pwm2-105934/project/combined.srcs/sources_1/bd/system/system.bd`：

- `display_clk_wiz_0_clk_out1`（约第5497行）直连 `lcd_pclk`、`v_tc_0/clk`、`v_axi4s_vid_out_0/vid_io_out_clk`，也并联到 LVDS 映射器输入。
- `v_axi4s_vid_out_0/vid_data` 经 `xlslice_R/G/B` 接 LCD RGB565；DE、HS、VS 直接接 LCD。
- TTL 视频使能/复位取自 `clk_wiz_0/locked` 与 `rst_clk_wiz_out`；没有从辅助 LVDS PLL 返回的锁定条件。
- `lvds_n_x_7to1_sdr_tx.v` 内的 `tx_mmcm_lckd` 只复位本模块的串化器；不是模块输出，不进入 TTL 的时钟、复位或使能网络。辅助模块 reset 是 PS 的 FCLK_RESET0_N，共用复位来源并不等于 TTL 依赖辅助 lock。
- `display_backlight_ttc0_ch2` 连接 `sys_ps7/TTC0_WAVE2_OUT`，与 LCD 像素时钟无关。

**据此：辅助 LVDS 不锁不能单独解释 TTL 黑屏，TTL 也不需要辅助 PLL 锁定才能工作。** TTL 是否真正显示仍要检查主 ClockWiz、VTC、VDMA、视频输出与面板信号。

## 2. 静态时钟与运行时模式不可混用

只读重开 `E:/p30c-1019-174235/merged-route.dcp`，得到：

| 时钟或端口 | P30 静态声明 | 33MHz 运行模式应有值/限制 |
|---|---:|---|
| FCLK0 / FCLK1 | 100 / 200MHz | 不因显示配置改变 |
| `rx_clk_in_p` / `rx_clk` | 4ns，即250MHz | 保守高频分析上界；不是30.72MS/s直接推得的实际 DATA_CLK |
| LCD / HDMI 并行像素时钟 | 约148.5MHz / 6.734ns | 原厂800×480配置为33MHz，1056×528总时序约59.19Hz |
| `p29_lvds_half_pclk` | 约74.25MHz / 13.468ns | 16.5MHz / 60.606ns，真实触发器二分频关系应保留 |
| 辅助 LVDS PLL VCO | 约1039.5MHz | 固定 M14、D1 时约231MHz，需停用或重新设计该分支 |
| 辅助串化时钟 | 约519.75MHz | 传播计算约115.5MHz；计算得出不代表器件能锁定 |

`lvds_n_x_7to1_sdr_tx.v` 第47–58行设 `USE_PLL="TRUE"`、`MMCM_MODE=2`；`clock_generator_pll_7_to_1_diff_sdr.v` 第187行起实际实例是 `PLLE2_ADV`，并非名称中暗示的 MMCM，M=14、DIVCLK=1、CLKOUT0_DIVIDE=2。

在内存中把主像素输出建成33MHz的**诊断源时钟**后，Vivado 确实传播出60.606ns的辅助 PLL 输入周期，原生警告 `Timing 38-305` 表示该值超出允许范围。普通 DRC 因拒绝自动更新 PLL 的旧 `CLKIN1_PERIOD=13.468`，仍沿用旧属性；不能把这个普通 DRC 的“无新增错误”当作33MHz模式有效。进一步显式设置实际周期60.606ns时，原生模型直接以 `Netlist 29-154` 拒绝：允许范围为0至52.631ns；该负例进程退出1，**没有生成显式周期 DRC 报告**，失败原文见同目录 `runtime-explicit-period.log`。

上述内部 `create_clock` 会切断上游 MMCM 自动推导并触发 `Constraints 18-1055`，只是暴露辅助分支问题的独立探针。它没有证明主 ClockWiz 的真实 DRP 配置、过渡过程或实际33MHz时序通过。最终候选应通过真实 IP 配置/DRP参数建模，保持 FCLK0→ClockWiz 的派生关系；不能把探针写回 XDC。

**建议**：当前任务只支持实际40pin TTL屏时，从新副本移除未用 LVDS 映射/PLL/串化及其顶层端口/约束，随后做差异审查、BD与顶层编译、33MHz模式重新综合/布线。保留原P30基线。若以后要恢复 LVDS，单独设计其合法频率、输入范围和启动/切换流程。不可单改倍频器让33MHz能锁：这会在原148.5MHz启动模式过频。

## 3. TTL专用33MHz候选的驱动契约

额外从已供应、未改动的4.9内核源码包提取了ClockWiz和DRM的六份源文件，见[清单及SHA](../../results/p33-timing-review-20261020t113053z/driver-sources.json)。源码包SHA与P31一致；它不是对运行内核全部dirty改动的重建证明。

- `drivers/gpu/drm/xilinx/xilinx_drm_crtc.c` 第153行把 `adjusted_mode->clock` 乘1000送 `clk_set_rate`；33000是DRM标准kHz，候选DTS继续用33000，不能改成33000000。800×480的VTC参数可保持现有配置。
- `drivers/clk/clk-xlnx-clock-wizard.c` 第551–588行从当前硬件配置寄存器读取倍频、分频，注册时钟；没有强制假定初始148.5MHz。因此合法的33MHz初始配置原则上兼容，仍需上板读回当前版本行为。
- 保留ClockWiz的动态重配置接口/寄存器映射、输出0及其provider索引、原来100MHz `clk_in1` 和200MHz `s_axi_aclk`；第543行检查AXI时钟上限250MHz，200MHz没有触及该限制。不要为了初始33MHz把IP换成没有AXI DRP的纯MMCM。
- 源包另含更旧的 `drivers/staging/clocking-wizard`，运行内核实际启用哪份驱动尚未在本轮证明；不能单靠从包里找到新驱动宣称动态调频成功。
- 主驱动的若干 `while (retries--)` 使用 `u16` 计数，耗尽时会回绕，而其后超时判断只检查0。因此 `clk_set_rate` 返回0不足以单独证明PLL已锁。上板要独立读LOCK、配置寄存器和像素频率/视频周期；本轮只记录这一验证要求，没有改内核。
- TTL专用候选初始33MHz可同时避免上电短时间向尚未确认额定上限的面板输出148.5MHz。删除LVDS/辅助并行HDMI顶层输出时，需要保留驱动内部用于TTL的VID_OUT/VTC/RGB裁剪与ClockWiz，不删除整条视频网络。

## 4. RF 时钟及外部延迟的准确缺项

只读 DCP 实查：

1. `rx_clk_in_p`→IBUFDS→BUFG→七个 RX IDDR 的 C，均属于 `rx_clk`；七路是六数据加一帧。
2. 同一 `rx_clk` 驱动 RF TX 的 ODDR C；`tx_clk_out_p` 由 `i_tx_clk/i_tx_data_oddr/Q`→OBUFDS 输出。**该顶层输出没有时钟对象**，不能据时钟报告中已有 `rx_clk` 就认为 FB_CLK 输出关系已约束。
3. `lcd_pclk`、`o_video_pclk` 具有传播的主像素时钟；辅助 `lvds_clk_out_p[0:1]` 也没有顶层时钟对象。它们是由串化时钟图案产生，不应把内部高速 bit clock 直接当成外部 pixel clock。
4. RF `dac_clksel` 会改变输出 FB_CLK 极性：LVDS RTL 第375–376行 `tx_clk_p<={~dac_clksel,dac_clksel}`，经寄存器送 ODDR 的 D1=bit0、D2=bit1。仅创建一个默认非反相的输出 generated clock 会漏掉另一种选择。实际使用哪种模式必须由运行时核心寄存器读回/驱动设置确认。

芯片主规格书 AD9361 Rev.F 第7页和接口规格第22页均支持下列**芯片引脚处**数字：LVDS DATA_CLK周期至少4.069ns；RX data/frame clock-to-out 0.25–1.25ns；TX setup 1ns、hold 0ns（接口表明确以FB_CLK falling edge描述，DDR其他有效边沿的完整映射仍应结合图17/18和RTL核对）。SPI可用第29页数字：周期至少20ns，输入setup2ns/hold1ns，输出clock-to-out3–8ns。

它们可以写入计算契约，不能直接全部变成最终引脚约束。还缺：

- 核心板+载板+FMC RF模块的 DATA_CLK/data/frame/FB_CLK 路由差异上下界与不确定度；已有载板 `.brd/.PcbDoc` 和FMComms3 `.BRD`，但本次未提取电气长度，核心板段也不可省略。原理图的连通关系不是长度报告。
- 实际 AD9361 1R/2R、DDR/端口交换配置，当前 `rx_path_rates/tx_path_rates`；不能仅凭Fs推断接口时钟。
- 运行后的 AD9361可编程RX data/clock与TX FB/data delay，以及 FPGA IDELAY/ODELAY/校准窗口。候选 DT 的 `adi,rx-data-delay=4`、`adi,tx-fb-clock-delay=7` 是初始化参数，不能冒充自动调谐后的实际值。
- RX双边沿、TX转发时钟极性/采样边沿的完整时序图。任何新增 generated clock 要断言唯一对象和 master，不能用独立主时钟切断来源。

计算方向示例（全部单位ns，`Bdata/Bclk`为板级传播，仍须叠加选定可编程延迟和不确定度）：

```
RX input_min = 0.25 + Bdata_min - Bclk_max
RX input_max = 1.25 + Bdata_max - Bclk_min
TX output_max = 1.0 + Bdata_max - Bfbclk_min
TX output_min = -0.0 + Bdata_min - Bfbclk_max
```

不能把 `-min` 一律取0或把hold写成正setup，也不能省掉DDR另一有效边沿。此处没有生成含猜测板延迟的约束文件。

## 5. 最小推进门槛与最终验收门槛

**可以现在做的离线推进**：保留供应资料/旧基线；选择TTL专用候选；修正PWM2和VDMA契约；明确33MHz模式，检查主ClockWiz输入100MHz/AXI控制200MHz，采用真实合法参数而非诊断时钟；重新综合和布线，并保存未约束端口清单、时钟关系、DRC/CDC。缺失外部参数无需阻止工具构建，但这次构建只能称“已有约束范围通过”。

**受控整合上板前至少完成**：

1. TTL专用构建不包含运行频率非法的辅助PLL；或有明确、可验证的复位/停用方案，不能只声称“没接LVDS屏所以无需管”。清理后与原候选的RF/PS/地址/IRQ差异逐项核对。
2. 主视频初始频率、驱动重配频率、锁定/复位/使能顺序明确；不能把148.5MHz静态报告套成33MHz运行报告。避免在尚未确认裸屏输入上限时依靠屏幕持续接收148.5MHz。
3. 无新的未解析单元、IO电压/引脚冲突、未约束内部端点；所有关键跨域握手与复位问题有具体审查结论，不新增整体false path或整体CDC豁免。
4. 保持新启动单次加载、风扇/启动保护和正常重启恢复；不热卸载RF/PWM驱动。先只验证TTL图案/帧缓冲/触摸/背光/系统计时，再做有限RX及并行；TX与完整采集仍独立验收。
5. 将外部时序尚未发布的限制写入当次试验结论。屏幕可见、有限RX成功都不能替代最坏条件setup/hold验收。

**最终稳定交付仍需**：确认实际裸屏规格或提供可追溯的等价模块时序；补LCD RGB/DE/HS/VS相对PCLK的setup/hold与边沿、FFC/电平转换延迟；补RF板级时延和调谐后的模式约束；在全部承诺支持的频率/温度/启动模式下关闭setup/hold/时钟范围/复位风险。可先只承诺实际TTL屏、固定RF配置，避免无必要验收未用HDMI/LVDS模式。

本轮没有增加任何时序豁免，没有宣称58项CDC已关闭，没有改动现有板卡运行状态。
