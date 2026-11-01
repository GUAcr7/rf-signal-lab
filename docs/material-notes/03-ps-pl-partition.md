# 实际PS/PL与电脑分工

| 部位 | 实际职责 | 主要证据/源码 |
|---|---|---|
| 旧板P201，Zynq-7020 PS | 配置AD9361、运行受限时长的原生发射与停止清理程序 | embedded/arm_tx_source/、host/board_control.py、P81按键/原生回执 |
| 旧板P201 PL | 复用射频数字接口、DDS/缓冲选择与DMA发送通路 | 原厂HDL基线及射频任务记录；不声称独立重写整条发送IP |
| 新板TLZ7xH，Zynq-7100 PS | Linux/IIO读取I/Q；下变频、软件FIR/抽取、FFT、ROI参数估计、CNN/相位池策略、绘图计算 | results/p75-build-20261026T100057Z/bundle中的monitor.c、rf_frontend.h、measurements.h、phase_pool.h、trained_cnn_infer.c、dashboard.h |
| 新板PL | AD9361数字接口及DMA到DDR；RF与视频合并工程、显示数据输出、时钟及EMIO接口映射 | P37合并构建与布线报告、rf_display_gpio.v、合并顶层及P37实际加载记录 |
| AD9361 | 模拟射频接收/发送、混频与ADC/DAC等片内处理 | 配置/读回记录。30.72MS/s是I/Q采样率，不是显示刷新率 |
| PC | 淘晶驰USB-TTL屏控中转、任务启动与源包恢复、校准组织和证据归档 | host/source_screen_rf.py、fast_panel_control.py、P81原始记录 |
| 两块屏 | 淘晶驰触屏控制发送类别/时长；新板7寸屏展示四区数据 | P81人工操作、P84实屏照片 |

接收路径：RF→AD9361→PL数字接口/DMA→DDR→ARM分析/AI及绘图→显示缓冲→PL视频输出→LCD。
控制路径：淘晶驰屏→USB-TTL→PC→旧板PS受控发送→旧板PL/AD9361→衰减/同轴→新板。

因此本项目有PS/PL协同和真实射频闭环，但当前不能把ARM计算描述为PL FFT或PL CNN硬件加速，也不能把电脑中转控制描述为整机完全脱机。自写FIR是独立验证候选，不在上面当前演示数据路径中。
