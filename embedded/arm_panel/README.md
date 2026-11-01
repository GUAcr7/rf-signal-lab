# 板端频谱程序

使用当前`arm_panel.c`和`font8x12.h`。本目录旧的`arm_panel`二进制是P34历史产物，不匹配P35源码；不要直接按文件名部署。

已核验P35二进制及源码哈希见：`results/p35-arm-panel-check-20261020T161014Z/report.json`。
新板已执行已知夹具的无屏分析复测，见：`results/p35-panel-board-20261020T161445Z/report.json`。它不证明新版屏幕绘图通过。

```text
arm-panel --analyse-only iq16le.bin 2 8 1
arm-panel iq16le.bin 2 8 1
```

参数依次是交错通道数、每次平均FFT帧数、迭代数。两通道是I/Q；四通道时使用前两通道，不能把四通道文件按两通道输入。当前读取本地小端int16文件，不是实时接收。

输出峰值为相对每FFT bin 1 count²的dB；平均FFT功率按`N*sum(Hann²)`归一化。功率与平均帧数无关；它不是dBm或每Hz PSD。RMS是I/Q每分量均方根。零输入不报告峰频偏。

`analysis_ms`仅分析，`draw_ms`仅CPU写帧缓冲，`iteration_compute_ms`为二者总计；均不包括文件读入、RF采集、日志输出或屏幕扫描/vsync。它们不能换算成已测屏幕FPS或RF吞吐率。

绘图前核对已知800×480、32bit X/ARGB8888、行跨度/可见偏移/显存边界；未知布局直接拒绝。真正RF与屏幕同时工作需要先通过合并硬件和设备树的受控新启动验收。禁止运行时卸载RF/PWM驱动或重配其PL。
