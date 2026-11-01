# RF 与显示合并候选（P30工程 / P31设备树）

P31最新状态见[HW-023](../../docs/experiments/exp-hw-023-device-tree-cdc-and-kernel-recovery.md)。`rf-display-800x480.dts`已完成电脑端编译/应用/240项检查，以及对实际BD的30项核对和4种负例；未上板。原厂RF overlay热卸载导致内核异常，候选尚未应用，**禁止通过卸载当前overlay来试验候选**。仅部分FIFO/AXIS仲裁数字行为已仿真，58项CDC仍待验收。

这是 XC7Z100FFG900-2 的电脑端合并工程，不能当成已经上板的固件。最新验收与限制见 `docs/experiments/EXP-HW-022-rf-display-integration.md`，机器路径见 `results/p30-active-build.json`。

## 重建

在项目根目录，用现有 Python 环境依次运行：

```powershell
.venv\Scripts\python.exe experiments\p30_prepare_integration.py
.venv\Scripts\python.exe experiments\p30_prepare_stages.py
.venv\Scripts\python.exe experiments\p30_run.py create
.venv\Scripts\python.exe experiments\p30_run.py gpio-test
.venv\Scripts\python.exe experiments\p30_run.py synth
.venv\Scripts\python.exe experiments\p30_run.py audit
.venv\Scripts\python.exe experiments\p30_verify_graph.py
.venv\Scripts\python.exe experiments\p30_vtc_test.py
.venv\Scripts\python.exe experiments\p30_run.py implement
```

准备程序每次建立新的 E 盘工作目录；不要在一个构建仍在运行时再次准备。它依赖 P29 留存的两个迁移导出、已打包 ADI IP、显示原厂源和本机 Vivado 2021.1，不是可独立搬走的完整开发环境。原始 D 盘资料不变。构建日志、真实返回码与失败尝试全部进入 `results/`。

本轮先修补旧 XDC 的不支持语句，再修正 ClockWiz 的 `PRIM_SOURCE=No_buffer`。新准备脚本已经包含最终修正，无需对新工程再次调用历史 `p30_fix_clock_source.py`。后者只用于留存本轮旧配置的纠错证据。

## 连接约定

- 单一 PS7；以显示工程的载板参数为候选，补齐 RF 所需 SPI1、EMIO64、HP1/2 与 16 位中断。保留实际工作的启动固件，尚不认可任何候选 `ps7_init.c` 为当前 FSBL 输入。
- PS FCLK0 100 MHz：RF/CPU/HP1/HP2；FCLK1 200 MHz：RF delay、视频/HP0。AXI-Lite M00..M03 在 200 MHz 域，互连生成跨域转换，RF M05..M07 仍在 100 MHz 域。M04 预留未使用。
- ClockWiz的`clk_in1`实际接FCLK0/100MHz，`s_axi_aclk`接FCLK1/200MHz；设备树候选分别使用时钟索引15/16。RF DMA使用索引15和4KiB资源窗口；4KiB当前内核兼容性仍须在无驱动绑定的新启动中验证。
- RX/TX DMA 分别使用 HP1/HP2；VDMA 使用 HP0。视频外设地址和 RF 外设地址分别保留。
- 视频中断 In0..3；RF TX/RX 中断 In12/In13。其他中断输入接零。
- 触摸为 SPI0/EMIO0；AD9361 为 SPI1/EMIO32..48。`rf_display_gpio.v` 有独立原生仿真。未使用的外部 TDD sync 接零；将来启用外部 TDD 必须重新设计同步与验收。
- 显示 RTL 副本仅加入禁止错误总线推导的接口元数据；去除新增标注后与原厂逻辑文本相同，保留版权说明。
- 使用当前板的 800×480 配置；VTC 仿真采用加速像素时钟，配置完成后门控闲置 AXI 时钟，只检验计数与寄存器行为，不能证明面板、33 MHz 时钟或整条视频链已通过。

## 上板前仍须完成

1. RF CDC/复位和时钟拓扑逐项审查；布局布线时间通过不替代 CDC 验收。
2. 有实际器件及载板依据的外部时延约束；不填写虚构的零时延，不以关闭告警作为修复。
3. 实际内核/设备树、时钟动态配置与启动包配对。800×480 TTL、LVDS/HDMI 的适用范围须明确，不能用一种模式验证冒充全部接口。
4. 保存完整回滚路径后，再设计临时加载及分项上板验收。当前脚本不生成 bitstream、不替换 BOOT.BIN、不编程板卡。
