# EXP-HW-001：原厂系统首次登录

- 日期：2026-09-22。
- 操作：团队成员实际操作板卡；Codex 辅助解释、只读检查电脑和记录。
- 当前结论：已验证串口登录、Linux 命令执行、板端网络地址读取与 USB 网络 ping；尚未验证 IIO 射频设备访问或采样。
- Git 被测版本：原厂固件；学习工程尚无首次 Git 提交。本次没有自行修改或构建 FPGA。
- 证据：用户截图 codex-clipboard-70029441-4589-4353-b5c4-ccaff8fba068.png，副本保存于 results/hardware-001-login-20260922.png。

## 原理和预期

JTAG_UART/PWR 经 FT2232 提供串口终端。供电与系统启动后，应出现 login 提示，登录后可以执行 Linux 命令。
这是原厂运行环境检查，Python 黄金模型、算法单元测试、RTL TestBench、资源和吞吐测试在本次检查中不适用；这些不能因此视为项目算法验证完成。

## 实际结果

| 项目 | 截图或电脑观察 |
| --- | --- |
| 串口 | USB Serial Port (COM9)，SecureCRT 串口会话 |
| 登录 | root 登录成功，出现 # 提示符 |
| 固件横幅 | PZSDR / v0.35-dirty |
| uname -a | Linux pzp201 5.10.0-98231-g9dfba10b795d-dirty，armv7l GNU/Linux |
| eth0 | 192.168.1.10，掩码 255.255.255.0 |
| usb0 | 192.168.2.1，掩码 255.255.255.0 |
| lo | 127.0.0.1，本机回环接口 |

截图中 eth0/usb0 均无 RUNNING 标记，RX/TX 均为 0；不能仅凭配置了 IP 就认定电脑已连通。登录截图也不单独证明具体启动介质。前两次 uname 拼写/空格输入错误已被正确命令纠正，不是固件故障。

## 下一步连接选择

Windows 只读检查：以太网 5 为当前唯一默认路由，地址 10.4.187.175/16，WLAN 未连接。为保留当前互联网连接，先采用 USB OTG 数据连接；不自动修改现有以太网配置。

依据厂商 Matlab 教程第 8～9 页：配套 PlutoSDR-M2k-USB-Drivers.exe 安装后，供电接口和 OTG 接口均可用 USB 线连接电脑。保留已有 JTAG_UART/PWR 串口线，再将 OTG 接口连接至同一电脑；目标是识别 USB 网络适配器，并从 Windows ping 192.168.2.1。

## 后续实测：USB 网络连通

2026-09-22 用户在 Windows 执行 ping 192.168.2.1：发送 4、收到 4、丢失 0；截图统计往返最短 0ms、最长 3ms、平均 1ms，TTL=64。这是 4 个 ICMP 请求的结果，不代表 IQ 数据传输吞吐率或系统分析延迟。

主线程只读检查确认新增以太网 6 地址 192.168.2.10/24。用户证据 codex-clipboard-4aecb4f6-60d0-4a48-abdd-68e47d9bb84a.png 保存为 results/hardware-001-usb-ping-20260922.png。

下一步使用配套 IIO Oscilloscope（安装包版本信息 v0.14-master）连接 ip:192.168.2.1，先识别射频配置和接收采样设备。软件安装、IIO 服务连接、真实采样、FPGA 自定义处理、AI 和各项性能指标仍待验证。本轮助手未执行安装、发射或射频参数修改。
