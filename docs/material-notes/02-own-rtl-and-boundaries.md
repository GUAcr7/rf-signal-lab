# 自写RTL、厂商IP与验收边界

“自写RTL模块”与“已封装并上板的计算IP”是不同的完成状态。下面按证据分别描述；AI参与生成与纠错的贡献须如实说明。

## A. 自写定点I/Q FIR：有源码、仿真和综合；当前未接入RF链

源码evidence/fpga/rtl/fixed_fir_iq.v、测试evidence/fpga/tb/tb_fixed_fir_iq.sv、系数fpga/ip/fir63_q17.hex，构建fpga/fir-vivado/synth_fir.tcl。12位有符号I/Q，63抽头、18位Q17系数、36位累加、偶数舍入、16位饱和与饱和标志，valid/ready反压及复位契约。

当前加流水级版本的完整仿真：evidence/results/p07-fir-rtl-20261011T035739182285Z/；默认系数资格：p07-fir-rtl-20261011T035905891918Z/。综合优化前后证据：p07-fir-timing-20261011/，解释见docs/experiments/EXP-P07a-TIMING-20261011.md。

| 指标 | 修改前 | 最后MAC与舍入分拍后 |
|---|---:|---:|
| 100MHz内部综合setup裕量 | -5.153ns | +1.866ns |
| LUT |828|731|
| FF |1564|1631|
| DSP |2|2|

此数据是OOC综合估计，placed/routed/board_accessed均false。当前版每66拍接收一对I/Q，100MHz结构上限约1.515MS/s，不能直接处理30.72MS/s不可暂停ADC流。它能证明做过定点RTL设计与时序改进，不能作为当前演示中的硬件FIR加速证据。项目另有ARM软件FIR，不能混同。

## B. 合并工程的自写接口映射模块：已有构建及上板关联证据

evidence/fpga/rtl/rf_display_gpio.v把PS EMIO映射至触摸中断与AD9361控制信号；tb_rf_display_gpio.sv的352项检查见p30-gpio-test-20261019T093658Z/report.json。E盘P37构建副本已与仓库源码SHA一致，副本也收录在evidence/deployed-build-source/。rf_display_top.v中实例化该模块；合并构建、位流、实际加载与时钟验证见P37报告及EXP-HW-027-safe-clock32.md。

这是自写组合接口/板级集成逻辑，体量较小。顶层rf_display_top.v带ADI版权，属于基于原厂顶层适配，不能整体声称完全原创。AD9361接口、AXI DMA、VDMA、ClockWiz等复用组件应按其原作者和许可标注。

## C. 当前不能声称已有的成果

没有证据支持“已经在演示中用自研FFT IP计算频谱”“CNN已在PL并行推理”“独立FIR已接入当前接收链”。FFT IP练习采用官方模型，不是自研FFT。旧板独立UART候选的审核/试验不等于屏幕已经直连旧板，现有成功演示仍由电脑中转。

适合报告的写法：基于厂商射频和视频基础IP完成系统集成，编写接口适配RTL，并独立实现和验证定点FIR候选模块；当前频谱/测量/AI算法部署于ARM PS。不要为了符合另一AI的建议把候选模块改写为已上板计算核心。
