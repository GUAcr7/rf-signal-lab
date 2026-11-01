# EXP-HW-002：IIO 软件启动与设备识别排查

- 日期：2026-09-22 至 2026-09-23。
- 范围：电脑 IIO GUI 启动故障、网络上下文与板端只读启动日志。
- 不涉及训练、RTL 实现或射频发射；本阶段不做算法黄金参考、量化或硬件性能评价。

## 已观察的故障

原厂配套安装包版本 v0.14-master，安装目录 D:/FPGA natch/IIO Oscilloscope。Windows Application Error 1000 多次记录 osc.exe 异常 0xc0000005、偏移 0x9668。--help 正常打印用法；指定 -p - -c 192.168.2.1 仍未打开窗口，标准输出/错误为空。不能据此认定为安全软件拦截或路径空格问题。

同目录 iio_info.exe -n 192.168.2.1 曾成功连接：客户端 libiio 0.21，服务端 0.24，模型属性 PUZHI PZSDR P201；设备列表只有 xadc，没有射频配置或采样设备。

通过已知板卡 USB 地址进行 SSH 只读检查，dmesg 包含：

```text
ad9361 spi0.0: ad9361_probe : enter (ad9361)
ad9361 spi0.0: Unrecognized CHIP_ID 0xE0
```

spi0.0 无绑定 driver，FPGA manager 状态 operating。说明射频驱动初始化未完成，不能从此断言芯片损坏、实际型号或具体供电故障。日志中的 CHIP_ID 是驱动表达式处理后的值，不保证是未经处理的芯片寄存器原值。

## 电脑 GUI 对照结果

从 ADI 官方 v0.18-main release 下载完整安装包，SHA256：22599d143db88a8a3e8e92c77b89ce199428d2c6877c68ced307a545057f8ad9。使用官方 innoextract 1.9 的 Windows 工具解包到独立目录：

`D:/FPGA natch/IIO-Oscilloscope-v0.18-portable/app/`

原目录未覆盖，未运行安装程序或改系统 PATH。新程序 bin/osc.exe 用 -p - -c 192.168.2.1 启动后出现 ADI IIO Oscilloscope 主窗和 Capture1 窗口，进程有窗口句柄且 Responding=True；存在图标 PNG 加载 warning。GUI 可以启动不代表射频采集恢复。

官方发布页：https://github.com/analogdevicesinc/iio-oscilloscope/releases/tag/v0.18-main 。旧版相同症状有 issue #372，但没有确定本机根因，不把升级测试成功当作根因证明。

## 最新连接状态（2026-09-23）

用户截图确认连接对话框已显示。随后主机复查不再列出 Pluto/RNDIS 网络适配器，也无先前的 192.168.2.10/24 地址；只有正在上网的以太网 5 在线。此时 .2.1 的 ping 回复 TTL=252，与先前板卡 TTL=64 不同，不能认定当前回复来自板卡。IIO 查询报连接拒绝，SSH 查询超时后停止。未继续访问身份不明确的目标，未修改任何网卡或路由。

当前用户操作：保持 JTAG_UART/PWR 连接，重接 OTG 数据线；先确认 Pluto USB 网卡及主机 192.168.2.10/24 地址恢复，再在 GUI 使用 Manual / ip:192.168.2.1 / Refresh 验证上下文。射频初始化报错仍待重新核验和排查，不直接开始采样。

## 证据与修改范围

命令行与板端日志位于 results/iio-startup/；下载凭据位于 tmp/iio-official-v018/download-receipt.json。SSH 辅助依赖仅安装到 tmp/iio-diagnostic-deps，没有改学习工程虚拟环境。未修改板端文件、GPIO、寄存器、固件或射频设置。
