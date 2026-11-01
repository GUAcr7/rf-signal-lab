# EXP-P01：IIO 接收通道与真实采样验收

- 日期：2026-09-28（Asia/Shanghai）。
- 平台：璞致 PZSDR P201，板端 Linux 5.10.0-98231-g9dfba10b795d-dirty；电脑软件为独立目录中的 ADI IIO Oscilloscope v0.18。
- 范围：确认原厂接收链路、采集、显示与保存。本轮没有发射射频信号、修改 SD 固件或开发自有 FPGA/AI 模块。
- 结论：**P01 在本次启动状态下通过**。板卡曾在首次开机时初始化失败；软件重启后恢复。根因未定，不能视为永久修复。

## 先理解的概念

IIO 是软件访问板卡采样设备的接口。串口登录和 USB 网络可用，只能证明电脑能够与板卡通信；需要看到接收设备 cf-ad9361-lpc，并真正得到变化的样本，才能证明当前接收数据链路可用。

I 与 Q 是一路接收信号的两串配对数字。GUI 上本次选择原厂接收设备的 voltage0、voltage1，后续在 P02/P03 用已知信号进一步核对具体通道顺序与频率方向。本次波形主要是当前接收环境与接收机噪声，不能把它标注为特定通信调制信号。

## 本次经过与依据

1. 电脑当前识别到 PlutoSDR USB Ethernet/RNDIS Gadget，直连 USB 网卡为 192.168.2.10/24；到板卡 192.168.2.1 的路由经过该网卡。串口本次枚举为 COM5。
2. IIO v0.18 GUI 的连接窗口识别上下文 PUZHI PZSDR P201。首次设备列表只有 xadc；板端日志为 `Unrecognized CHIP_ID 0xF8`，射频控制及接收设备都未注册。当时没有尝试伪造采样。
3. 保存首次状态后，向板卡发出一次正常软件 reboot。重启后板端设备名依次列出 ad9361-phy、xadc、cf-ad9361-dds-core-lpc、cf-ad9361-lpc；日志有 `AD936x Rev 0 successfully initialized` 和 `probed ADC AD9361 as MASTER`。
4. 在 IIO 软件中重新扫描并连接 P201 上下文，Capture1 出现 cf-ad9361-lpc 下 voltage0～voltage3。选择 voltage0、voltage1 后，时域图连续更新。
5. 停止采集并保存第一份 CSV；重新开始采集，观察到新波形；再次停止并保存第二份 CSV。切换 Frequency Domain 后，软件用当前采样显示频谱。

首次启动与重启后的板端日志分别保存于 [board-before-reboot.txt](../../results/p01-20260928/board-before-reboot.txt)、[board-after-reboot.txt](../../results/p01-20260928/board-after-reboot.txt)。SSH 主机指纹在重启前后分别为 `SHA256:RJLSoTwn5/suvvhou8aL/AehMKJALcLUn7zuhXHWQTs` 和 `SHA256:5GYZ92o5dw3MgaX7KC1ImLWztxObbkR5sBr+hyQHRFk`；重启后的主机身份通过直连 USB 路由、IIO 的 P201 模型和板端 model 再核对。不能把一次指纹变化单独解释为硬件故障。

## 采样配置和数据

板端只读配置快照见 [receive-configuration.txt](../../results/p01-20260928/receive-configuration.txt)：

| 项目 | 本次记录 |
| --- | --- |
| RX 本振设置 | 2,400,000,000 Hz |
| 采样率 | 30,720,000 复数样本/秒 |
| RX 射频带宽设置 | 18,000,000 Hz |
| RX 增益模式 | slow_attack（自动增益） |
| RX0 增益读数 | 71 dB，读取时刻的快照，不是固定全程值 |
| 扫描格式 | voltage0/1 均为 le:S12/16>>0，即每通道 12 位有效有符号数存于 16 位位置 |
| 时域显示 | 400 samples，分别选择 voltage0、voltage1 |
| 频域显示 | 软件 FFT Size 16384、Hanning 窗、窗修正开启、平均次数 1；这是电脑软件的频谱，不代表自有 FPGA FFT 已完成 |

原始证据：

- [首次采集 CSV](../../results/p01-20260928/capture-initial.csv)：400 行，voltage0/1 两列数值。
- [重新开始后的 CSV](../../results/p01-20260928/capture-restarted.csv)：400 行；与首次数据不同。
- [频谱界面截图](../../results/p01-20260928/frequency-capture.jpg)：显示接收设备、选中通道和频谱。

用独立 CSV 读取统计而非仅观察曲线：

| 数据 | voltage0 不同取值数/标准差 | voltage1 不同取值数/标准差 |
| --- | --- | --- |
| 首次 400 行 | 269 / 120.28 | 264 / 119.22 |
| 重启采集 400 行 | 285 / 152.22 | 286 / 145.21 |

两份 CSV 内容不相同，数据均可解析且不是固定常数。两份 CSV 的 SHA256 分别为：
`AA9326D017B7F1747D2629F0D0D88366A6AA7157DA12C8124DE0130004C7D430`、
`C182B88994321AD9F001837023BE2458A729451EC2D55E06CCE5790F4B59F7D3`。

## 逐项验收

| 要求 | 结果 | 证据 |
| --- | --- | --- |
| IIO 连到正确板卡 | 通过 | USB 直连路由、GUI P201 上下文、板端 model |
| 射频控制和接收采样设备可见 | 通过 | 重启后 ad9361-phy 与 cf-ad9361-lpc 均已注册 |
| I/Q 接收通道可选择 | 通过 | Capture1 中 voltage0、voltage1 可选择并显示数据 |
| 采到合理且更新的数据，记录配置 | 通过 | 两份 400 行 CSV、非恒定统计与配置快照 |
| 停止后重新开始仍可采集 | 通过 | 两次采样数据不同，GUI 开始/停止均正常 |
| 保存复核证据 | 通过 | 启动日志、配置、两份 CSV、频谱截图 |

本次 P01 属于原厂采集链路验收，Python 黄金算法模型、算法单元测试、自有 RTL TestBench、AI 量化及 FPGA 资源时序测试均不适用。本次 FFT 图由 IIO 软件产生，不能计作项目 FPGA FFT 成果。

## 限制、恢复与下一阶段条件

首次启动仅出现 xadc 且 AD9361 CHIP_ID 读取失败，软件重启后成功。这个现象说明接收初始化状态曾不稳定，原因仍未证实。当前无需为 P01 再反复重启；下次开机先检查 IIO 设备名，若只出现 xadc，保留新日志并核对可靠的供电、原厂配套线、准确 PCB/芯片型号与整套固件匹配，再判断是否复现。不要将一次成功软件重启写成已修复供电或时序问题。

恢复工作时：确认板卡已启动、USB 数据网卡是当前直连路径；在 IIO 软件重新扫描 P201 上下文，选择 cf-ad9361-lpc 的 voltage0/1，再做一小段采样。COM 号会因重新枚举变化，以实际设备管理器为准。

P02 的开始条件已在本次状态下满足：接收设备可见、真实采样可保存、配置可读取。P02 将学习 I/Q 与采样并用 Python 直接读取和回放数据；本次没有开始 P02。
