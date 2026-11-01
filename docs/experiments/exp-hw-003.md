# EXP-HW-003：接收通道缺失与数字接口自检失败

- 日期：2026-09-23。
- 用户现象：IIO Oscilloscope 的 Capture1 已打开，Plot Channels 为空。
- 当前结论：射频芯片控制驱动已注册；TX 数字接口时序训练失败导致接收 ADC 接口未注册。尚不能采样。
- 本轮以信息查询、现有日志及活动设备树对照为主，没有发起射频发射、修改固件、跳过校准或手动写延迟寄存器。

## 网络与设备状态

首先确认 Windows PlutoSDR USB Ethernet/RNDIS Gadget 为 Up，主机 192.168.2.10/24，Find-NetRoute 确认 192.168.2.1 通过此 USB 接口直连。此后才访问板卡，SSH socket 显式绑定主机 USB 地址。

客户端 libiio 0.26、板端 0.24，板端 model 属性 PUZHI PZSDR P201；本次列出三个设备：

| 名称 | 状态含义 |
| --- | --- |
| ad9361-phy | 射频芯片控制接口已注册 |
| xadc | 板内温度、电压监测 |
| cf-ad9361-dds-core-lpc | FPGA 发送数据接口已注册 |

缺少接收采样设备 cf-ad9361-lpc。这是本次实际状态，不能继续沿用上次“只有 xadc / CHIP_ID 失败”的结论。

## 本次启动日志

```text
ad9361 spi0.0: ad9361_probe : AD936x Rev 0 successfully initialized
cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: ... probed DDS AD9361
SAMPL CLK: 7680000 tuning: TX
  0:1:2:3:4:5:6:7:8:9:a:b:c:d:e:f:
0:# # # # # # # # # # # # # # # #
1:# # # # # # # # # # # # # # # #
ad9361 spi0.0: ad9361_dig_tune_delay: Tuning TX FAILED!
cf_axi_adc: probe of 79020000.cf-ad9361-lpc failed with error -5
```

SPI 设备已经绑定 ad9361 驱动，FPGA manager 状态 operating，deferred devices 列表为空。GPIO 现有状态中 reset 为高；没有写 GPIO。

## 为什么 TX 错误会让接收通道消失

随包内核源码 cf_axi_adc_core.c 的 ADC probe 调用 converter post_setup；ad9361_conv.c 的 post_setup 进行 RX/TX 数字接口训练。TX 未找到合适的时钟/数据延迟窗口，返回 -EIO（-5），ADC probe 提前退出，因此不注册 RX IIO 设备。

这是 FPGA 与射频芯片之间数字接口的内部自检，不依赖外部天线或测试信号，也不表示用户主动进行了射频发射。GUI 无法通过 Enable All 或播放按钮补出未注册的接收接口。

## 配置核对

读取 /sys/firmware/fdt，保存 loaded-20260923.dtb，解析后与 D:/FPGA natch/pluto/devicetree.dtb 对照。SPI 控制器、AD9361、参考时钟、RX/TX AXI 核等六个相关节点的属性均无差异，详见 device-tree-comparison.json。

这只证明选定的活动设备树属性与该本地文件一致；不证明实际加载 bitstream 与硬件 PCB 版本完全匹配。AD936x 驱动名也不能单独证明芯片具体料号。完整固件与实物版本、供电质量、时钟/数据接口条件仍待核对，尚未确定根因。

## 下一步边界

先核对供电和原厂配套线，必要时在明确可靠的 5V/1A 供电条件下做一次有记录的冷启动；保留新的启动日志和 IIO 设备名。若错误复现，核对准确 PCB/芯片型号与整套开机固件版本，不能通过盲目切换 compatible、1R1T/2R2T、跳过数字训练等方法宣称修复。

诊断期间不调用 bist_timing_analysis 一类可能在读取时启动硬件测试的 debug 属性；后续简单枚举优先 cat /sys/bus/iio/devices/iio:device*/name，避免反复运行会枚举大量属性的工具。

## 证据位置

results/iio-startup/ 下：iio-current-20260923.txt、dmesg-current.txt、iio-names-current.txt、drivers-current.txt、loaded-20260923.dtb、device-tree-comparison.json。用户空通道截图另保存 hardware-003-empty-channels-20260923.png。

无本项目 RTL 或 AI 更改；黄金模型/单元测试/RTL TestBench/量化测试在这次原厂开机排查中不适用。真实采样、资源、时序和吞吐率均未取得项目实测结果。
