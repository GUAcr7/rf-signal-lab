# 新板 TLZ7xH-EVM 接续说明（HW-014 后更新）

完整项目进度以 [START-HERE](../../start-here.md)、[HW-014 实验记录](../experiments/exp-hw-014-dma-continuity-resolution.md) 和 `TX-SOURCE-STATUS.json` 为准。旧版本保存在 `results/p22-document-backup-20261017/NEW-BOARD-RESUME.md`。

## 1. 已验证的能力与当前模式

新板为 TLZ7xH-EVM、XC7Z100 + AD-FMCOMMS3，libiio 0.20，SD 根文件系统。显示、风扇、触摸持久化及 display→rf→display 重启往返已有 [HW-007](../experiments/exp-hw-007-touch-persistence.md)、[HW-008](../experiments/exp-hw-008-mode-round-trip.md) 证据。

本轮最后在线读回是 **rf 模式**。真实 BPSK、QPSK、16QAM 各两次 65536 点单 DMA 缓冲采样已验收；每段 2.133 ms，已知源 EVM 约 −37 至 −38 dB。尚未验收长期无丢样流或盲 AI。

RF 和显示仍使用互斥位流。RF 模式黑屏符合现有设计，不能因此重装驱动；桌面能显示也不代表同时在收 RF。

## 2. 重连后先只读检查

重新枚举串口并用板卡身份认板。本次新板 COM8、旧板 COM9，115200/8N1；端口可能变化。不要让 SecureCRT 和脚本同时占用同一串口。

```sh
uname -a
cat /etc/board-mode
cat /sys/class/fpga_manager/fpga0/state
cat /sys/class/gpio/gpio914/direction
```

新板应显示 Zynq-Tronlong，fabric 为 operating，风扇 direction 为 out。然后按实际模式检查：

- display：`/dev/fb0` 存在，XFCE 和触摸可用；通常仅枚举 XADC。
- rf：`iio_info -s` 可见 ad9361-phy、cf-ad9361-lpc、DDS 和 XADC；不用要求 `/dev/fb0` 存在。

设备编号不是永久约定，应先查各 `iio:device*/name`，再读取对应属性。本轮 PHY 是 device1，RX DMA 是 device2。

## 3. 模式选择与持久化文件

`board-mode` 无参数只读模式；`board-mode rf` 或 `board-mode display` 写入 `/etc/board-mode`，**重启后**由启动脚本成对加载位流和 overlay。不是热切换。本轮没有重启或修改启动配置。

| 文件 | 当前用途 |
|---|---|
| `/etc/rcS.d/S99board` | 5040 B、755；先风扇，后成对装载与终检；HW-008 已验证 |
| `/usr/bin/board-mode` | 1238 B；选择下一次启动模式 |
| `/lib/firmware/display.bin`、`d480p.dtbo` | 显示模式来源 |
| `/lib/firmware/ad9361.bin`、`pl.dtbo` | RF 模式来源 |
| `/lib/firmware/system_wrapper.bin` | 按模式暂存的活动位流，不总是显示位流 |
| `/etc/pointercal.xinput` | 222 B；X 的主要触摸标定来源 |
| `/etc/X11/Xsession.d/99touch` | 3025 B、755；可被 source 的触摸回退钩子 |

权威源码在 [board/](../../board/README.md)，不依赖 `tmp/`。不要重新部署旧的 1596 B S99board 或旧的触摸脚本；不要把脚本改名为 `S99board.off` 以为已停用，它仍匹配启动通配符。

触摸异常时先保存 pointercal.xinput、Xorg/Xsession 日志及 `DISPLAY=:0 xinput list` 输出。按实际设备查询属性，不照抄旧属性编号/设备 ID。Xsession.d 被 source，`exit` 会结束桌面，必须用可返回的钩子。其他启动条件下自动标定是否覆盖配置，仍需单独核验。

## 4. 已实测的 RF 配置和采集边界

本轮复用的配置：双方 Fs 30.72 MS/s、LO 2450 MHz、RF 带宽 18 MHz；旧板 TX1/port A、gain −10 dB、数字单分量峰值 256；新板 RX1A/A_BALANCED、manual/0 dB。旧板 TX1→新板 RX1A 的连接已实测，不是“尚未接线”。

这是限定配置的验证，不能推广成任意发射电平、RX 增益或频率都可直连。不要用芯片绝对最大值代替接收线性条件，也不要为复现而自动提高电平。步进测试的正确关系是**幅度加倍＝功率四倍＝+6.02 dB**；功率加倍只有 +3.01 dB。

RX DMA 为 I1,Q1,I2,Q2 四通道、每帧 8 B，格式 `le:S12/16>>0`；RX1 用 ch0/ch1。码端点 −2048/+2047，未触端点不能单独排除模拟压缩。

HW-014 已验证的短快照是 `-b 65536 -s 65536`。旧的 `-b 4096 -s 65536` 文件虽然字节数和 SHA 正确，仍有跨缓冲时间跳跃。禁止不带边界信息直接滤波/跟踪整份拼接文件。旧数据不做补样伪造；真实长期流需要丢帧证据。

采样后先在板端计算 SHA256，再回传核验，保留原始四通道文件、配置、缓冲长度和日志。`p22_acquire_comparison.py` 会实际限时发射，不是文件读取工具；只检查证据时使用离线分析入口。

## 5. 后续任务

1. 保持当前已验收的短快照数据接口及元数据。
2. 做长期采集时验证跨缓冲连续性、序号/丢帧和实际吞吐。
3. 采多会话、多 SNR 的独立真实 RF 数据集，再评估 AI、划分、准确率及量化。
4. 继续 FPGA FFT 的 CDC/时序/ADC-DMA 接入；RF+显示并行需要合并 PL 或另行设计显示路径。

本轮三个限时发送都已结束并记录清理。电脑侧证据已保存；旧 P201 的 `/tmp` 断电即丢，新板 SD 模式文件保留。下次不可复用旧 boot_id，恢复流程以 START-HERE 和 HW-010 为准。
