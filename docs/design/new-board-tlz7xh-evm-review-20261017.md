# TLZ7xH-EVM（Zynq-7100 + AD9361）新板资料审查：与旧 P201 的差异、射频接收与屏幕显示

2026-10-19 更新：[HW-021](../experiments/exp-hw-021-vendor-migration-and-reconnect.md) 已完成新板接收恢复和 RF/显示独立完整综合；原厂源未改、未烧写新位流。合并、接口约束/时序、显示升级功能及冷启动可靠性仍待验收。旧工具阻塞现已解除；下文早期“待授权/找不到器件”为历史状态。

- 日期：2026-10-17。
- 资料：`D:\xilinx\xilinx`（259 文件，3,177,915,466 字节）与 `D:\AD9361\AD9361`（54 文件，3,091,408,245 字节）。
- 本轮性质：**只读审查**。未修改 D 盘任何文件，未上电、未烧写、未制卡。提取的文本在 `tmp/new-board-xilinx-review/`。
- 本文件回答三个问题：①新板与旧 P201 有什么不同；②能不能接收射频；③能不能在屏幕上显示。

> 2026-10-18 更新：显示/触摸与独立 RF 已分别上板验证，当前进度以 [START-HERE](../../start-here.md) 为准。本文件是早期资料审查，以下“未上电/待用户确认”等只描述当时状态。新检查见 [HW-019](../experiments/exp-hw-019-memory-diagnostic-and-build-readiness.md)：RF/显示源码存在，但当前 Vivado 2021.1 找不到 XC7Z100；官方 Standard 支持范围不含该器件，需要合适的 Enterprise 支持及授权后再做合并构建。

## 1. 两套资料的定位不同（先澄清一个容易混淆的点）

| 目录 | 是什么 | 关键内容 |
|---|---|---|
| `D:\AD9361\AD9361` | **AD9361 射频案例包**（创龙 2021-02-18 V1.0） | AD-FMCOMMS3-EBZ 原理图、`Demo\hw`（xv7z045/xv7z100 预编译 `.bit`/`.bin`）、`Demo\sw`（设备树 overlay）、Linux 内核/rootfs/BOOT.BIN |
| `D:\xilinx\xilinx` | **TLZ7xH-EVM 整板资料** | 核心板/评估板规格书、**底板完整原理图（含显示页）与 PCB**、BSP（U-Boot/内核/rootfs/FSBL）、`Demo.zip`（8 类 demo，含**显示 demo 的预编译 bitstream**）、Vivado/SDK 2017.4 安装包 |

**两者互补**：射频案例包给射频，整板资料给板子本身（含显示）。此前只看了射频包，因此误以为这块板"没有显示链路"——**那个结论需要更正**。

## 2. 新板与旧 P201 的差异

| 项目 | 旧 P201（PZSDR P201） | 新板 TLZ7xH-EVM | 影响 |
|---|---|---|---|
| Zynq 型号 | XC7Z020（Zynq-7020） | **XC7Z045 / XC7Z100**（Zynq-7100） | PL 资源约 **4–5 倍**（见下） |
| PL 逻辑单元 | ~85K | **XC7Z045: 350K / XC7Z100: 444K** | 足够放 AD9361 + FFT + VDMA + 显示共存 |
| ARM | 双核 A9 | 双核 A9 **800 MHz** | 推理速度可能更快 |
| DDR3 | 1 GB（PS） | PS **1 GB** + PL **1/2 GB** | PL 侧独立大缓存，适合采集缓冲 |
| 存储 | SD 卡 | **8 GB eMMC** + SPI NOR + Micro SD | 系统可固化，不依赖 SD 卡 |
| 射频 | **板载 AD9361**，4 个 SMA（TX1/RX1/RX2/TX2） | **AD9361 通过 AD-FMCOMMS3-EBZ 模块插 FMC HPC 400pin** | 射频是**独立模块**，需实物插上 |
| 显示 | 无 | **并行 RGB LCD（40pin FFC）+ LVDS 排针 + HDMI OUT/IN** | 可以本地显示，不依赖电脑 |
| 触摸 | 无 | **XPT2046 电阻触摸**（SPI0） | 可做交互 |
| 网络 | 1× USB 网卡（usb0） | **2× 千兆网口**（PS RGMII + PL RGMII） | 传输 I/Q 快得多 |
| 供电 | **5V/1A USB 加强线** | **12V 6A DC-005**（外径 5.5/内径 2.1） | **供电方式完全不同，不能沿用** |
| 调试串口 | JTAG_UART/PWR Micro USB（PS 端） | **Debug UART Micro USB（PS 端）** | 类似，但端口号需重新确认 |
| 工具链 | Vivado 2021.1（本机已装） | 资料配套 **Vivado/PetaLinux/SDK 2017.4** | 版本不同；2021.1 未必能直接打开 2017.4 工程 |
| 其它 | — | 4× SFP+、PCIe x4、CameraLink ×2、SATA、CAN ×2、RS485 | 与本题无关但说明是工业底板 |

### 2.1 为什么 PL 资源差距很关键

原“Zynq-7020 放不下”的说法撤回：不能只凭逻辑单元数判断完整设计容量。现存旧板原厂工程 routed 资源报告中 LUT 为 11950/53200（22.46%），说明该版本有资源余量；这也不证明再加入 FFT/显示后一定能满足资源或时序。旧板当前构建限制必须依据具体资源、CDC、I/O 和时序报告，不能归咎一个未证实的容量上限。证据：`results/p06-control-replication-20261015-195837/reports/utilization.rpt`。

新板 350K/444K 逻辑 + 2020 DSP（XC7Z100）量级，**同时容纳 AD9361 采集链 + FFT + VDMA + 显示**在资源上是合理的（具体仍需综合报告确认，本文件不宣称已通过）。

## 3. 能不能接收射频信号？——**能，但需要 AD9361 模块实物**

### 3.1 硬件依据

- 评估底板规格书表 1：`IO 1x 400pin FMC 连接器，1.27mm 间距，HPC 标准`。
- `D:\AD9361` 的案例说明：基于 **AD-FMCOMMS3-EBZ** 射频模块与 TLZ7xH-EVM，完成 QPSK 调制与 FM 接收。
- 预编译 bitstream 存在：`Demo\hw\bin\ad_fmcomms3_ebz_xc7z045.bit`、`ad_fmcomms3_ebz_xc7z100.bit`。
- AD-FMCOMMS3-EBZ 原理图（ADI 官方原文件）第 2 页：RX SMA **J110 RX1A**、J111 RX2A，经 balun 与 18 pF 隔直进 AD9361 差分 RX；**无独立 LNA**。

### 3.2 结论与前提

**能收**，前提是**物理上插好 AD-FMCOMMS3-EBZ 模块**并经 FMC 连接。仅凭 `D:\xilinx` 的主板资料**不能**收射频——它只有底板和核心板，AD9361 在模块上。

接收端输入绝对最大值仍是 **AD9361 芯片 RF 输入 +2.5 dBm peak**（旧项目已核实），因此**把旧 P201 的 TX 直连到新板 RX 时仍须按实测电平核算**：旧板实测 TX 峰值 **−24.5 dBm**，直连余量约 **27 dB**（见 [EXP-P13-POWER](../experiments/exp-p13-power.md)）。**该结论绑定旧板"数字幅度 512/2047、TX 数字衰减 −10 dB"这组配置，改任一项都要重算。**

## 4. 能不能在屏幕上显示？——**能，且资料里就有可用的预编译工程**

### 4.1 硬件接口（来自底板原理图与显示 demo 的 XDC）

`Demo.zip` 内 `All-Programmable-SoC-demos/axi_video_display_demo/` 的约束文件 `axi_video_display_tlz7xh.xdc` 同时定义了三种输出：

| 接口 | 信号（XDC 实际端口名） | 说明 |
|---|---|---|
| **并行 RGB LCD** | `lcd_pclk`、`lcd_vsync`、`lcd_hsync`、`lcd_de`、`lcd_pwm_backlight`、`lcd_data_r[4:0]`、`lcd_data_g[5:0]`、`lcd_data_b[4:0]` | **RGB565**，对应底板 `P15_LCD_LVDS` 的 40pin FFC |
| **LVDS 屏** | `lvds_data_out_p[7:0]`、`lvds_clk_out_p[1:0]`，`IOSTANDARD LVDS_25` | 对应底板 2×15pin LVDS 排针 |
| **HDMI OUT** | `o_video_pclk/vsync/hsync/de`、`o_video_data[23:0]` | RGB888，对应 `P16_HDMI_OUT` |
| **电阻触摸** | `SPI0_*`、`touch_intr`，注释明确写 **XPT2046（ads7846）** | 触摸控制器走 PS SPI0 |

### 4.2 屏幕型号

`TL070A显示屏规格书`：**7 英寸 TFT 电阻式触摸，分辨率 800×480**，带亚克力安装面板（172×122 mm），配 40pin FFC。评估板规格书"驱动支持"一栏亦列有 **7in Touch Screen LCD (Res)**。

### 4.3 预编译工程（可以直接用来验证屏幕）

`Demo.zip` 的 `axi_video_display_demo/hw/bin/` 下有：

- `axi_video_display_demo_xc7z045.bit` / `.bin`（3,010,739 / 3,010,604 B）
- `axi_video_display_demo_xc7z100.bit` / `.bin`（3,346,311 / 3,346,176 B）

对照：AD9361 案例的 bitstream 文件更大（`ad_fmcomms3_ebz_xc7z045.bit` 13,321,510 B、`_xc7z100.bit` 17,416,454 B）。**文件大小不等于逻辑资源占用**，不能据此比较两个设计的 LUT/DSP 使用量；必须读取综合/实现资源报告。

即**两个器件都有现成的显示 bitstream**，无需先自己搭 Vivado 工程就能验证屏幕。另外 `qt-demos/tl_image_display` 提供 Qt 图像显示示例。

### 4.4 一个必须注意的差异

`D:\xilinx` 的 BSP 设备树 `linux-xlnx-g57b87eb-v2.4/tlz7xh-evm.dtb` 与 `D:\AD9361` 案例的设备树**字节完全相同**（sha256 均为 `1de196a6…`，19,340 B），且**其中没有 display/panel/framebuffer/touch 节点**。

**解释**：随 AD9361 射频案例发布的设备树是**裁剪过的射频专用树**，不包含显示。显示要靠**显示 demo 自己的 PL + 设备树/驱动**（`Demo.zip` 内），或自行在 Vivado 里把两者合并。

**这条更正很重要**：此前审查只看到射频包的 DTB，据此判断"没有显示链路"，**结论不完整**——硬件与 demo 都支持显示，缺的只是把两者合并到一份设计里。

## 5. 关键可行性结论：射频与显示能共存于同一 PL

把两份约束文件的 `PACKAGE_PIN` 全部提取比对：

| | 引脚数 |
|---|---:|
| 显示/触摸（`axi_video_display_tlz7xh.xdc`） | **64** |
| AD9361（`ad9361_z7xh.xdc`） | **53** |
| **重叠** | **0** |

**零引脚冲突**，说明"AD9361 采集 + 显示输出"在同一块 FPGA 里同时工作是**引脚层面可行**的。资源层面：两个 demo 各自都能在 XC7Z045 上实现，合计在 XC7Z100（444K 逻辑）上应该有余量——**但这是推断，必须用实际综合/实现报告确认**，本文件不宣称已通过。

## 6. 下一步操作建议（按依赖排序，每步都有明确成功判据）

### 阶段 0：先认清实物（不做任何烧写）

1. **确认核心板到底是 XC7Z045 还是 XC7Z100**。用户说"7100"即 XC7Z100，但要看实物芯片丝印或读 JTAG IDCODE 确认。**选错器件会导致 bitstream 不匹配。**
2. 确认**AD-FMCOMMS3-EBZ 模块是否在位**、是否插在 400pin FMC 上。
3. 确认**有没有 TL070A（或其它）屏幕**、是否已接 40pin FFC。
4. 记录供电：**12V 6A，DC-005，外径 5.5 / 内径 2.1**。**不要沿用旧板的 5V USB 供电。**

> 上述四项是物理事实，只能由用户提供；在拿到之前不做任何烧写或制卡。

### 阶段 1：让板子能启动并登录（不动射频、不动 PL）

- 用底板 **Debug UART Micro USB（PS 端）**接串口，115200 8N1（沿用旧项目已验证的串口参数）。
- 供电方式按 12V 6A。**BOOT SET 6bit 拨码**决定启动方式；若要 SD 启动需按手册设置。
- 成功判据：串口出现 U-Boot 与 Linux 登录提示，能跑 `uname -a`、`cat /proc/cpuinfo`（确认 CPU 数量与型号字符串）。
- **注意**：本机没有 PetaLinux 2017.4。现有 Vivado 是 **2021.1**，与资料配套的 2017.4 不同代。**先只用现成镜像启动，不重建系统。**

### 阶段 2：验证屏幕（用现成 bitstream，风险最低）

- 用 `Demo.zip` 里对应器件的 `axi_video_display_demo_xc7z0xx.bit`，按 `2-1-评估板测试手册`/`2-7-视频案例开发手册`的步骤加载。
- 成功判据：**LCD 上出现测试图**（或 HDMI 显示器出图），触摸能响应。
- 这一步**不需要碰 AD9361**，独立可做。

### 阶段 3：验证射频接收（用现成 AD9361 bitstream）

- 用 `D:\AD9361\Demo\hw\bin\ad_fmcomms3_ebz_xc7z0xx.bit` + 对应设备树 overlay 启动。
- 成功判据：`iio_info` 能看到 `ad9361-phy` 与接收设备，能读到采样率等属性（**只读**）。
- 然后才可以考虑用旧 P201 发单音、新板收。

### 阶段 4：把两者合并（真正的工作量）

- 在 Vivado 里把 AD9361 采集链与 VDMA+VTC+LCD 放进同一 block design。
- 引脚已确认零冲突；**仍需**：时钟域处理、VDMA 缓冲、分辨率 800×480@60、内存带宽评估、综合实现报告。
- **这一阶段之前必须有阶段 2 和 3 各自的成功证据**，否则合并出问题时无法判断是哪一半坏了。

## 7. 本轮明确没有做的事

- 未修改 `D:\xilinx` 或 `D:\AD9361` 下任何文件（只读取与提取文本到项目 `tmp/`）。
- 未上电、未烧写、未制卡、未改 BOOT/拨码。
- 未声称任何 demo 已在这块实物上跑通——所有"能"都是**资料与约束层面的可行性判断**。

## 8. 待确认清单（需用户提供）

| # | 问题 | 为什么必须先知道 |
|---|---|---|
| 1 | 核心板丝印是 XC7Z045 还是 XC7Z100 | bitstream 与器件必须匹配 |
| 2 | AD-FMCOMMS3-EBZ 模块在不在手上/在不在 FMC 上 | 没有模块就没有射频 |
| 3 | 有没有屏幕、型号、是否已接 FFC | 决定阶段 2 能不能做 |
| 4 | 12V 6A 电源适配器有没有 | 供电方式与旧板完全不同 |
| 5 | 板子现在能不能上电启动 | 一切的前提 |

## 9. 证据位置

| 内容 | 路径 |
|---|---|
| 提取的一手文本（规格书/手册） | `tmp/new-board-xilinx-review/*.txt`（含 `coreboard-spec`、`evm-spec`、`lcd-tl070a-spec`、`evm-test-manual`、`linux-usage-manual`、`evm-hardware-manual`、`coreboard-hardware-manual`、`qt-build`） |
| 提取索引与字符数 | `tmp/new-board-xilinx-review/index.json` |
| 显示 demo 约束（原文件副本） | `tmp/new-board-xilinx-review/demo-peek/axi_video_display_tlz7xh.xdc` |
| AD9361 案例约束（原文件副本） | `tmp/new-board-xilinx-review/demo-peek/ad9361_z7xh.xdc` |
| 提取脚本 | `experiments/p14_extract_xilinx_docs.py` |
