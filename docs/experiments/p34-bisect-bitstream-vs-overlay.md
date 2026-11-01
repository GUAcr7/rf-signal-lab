# P34：二分定位 —— 位流没问题，问题在设备树 overlay

> **P35审查更正（2026-10-21）**：标题及下文“PL完全正常、唯一坏设备树、CDC已排除”是当时过强的推断，已经撤回。原始证据仅支持两种厂家树分别probe成功；本轮才补上有限RX测试，仍未完成RF/显示并行。现有合并DTS本来就由厂家树拼接，语义上只有8项必要差异；重拼不是已证实的修复。显式装PL后应用无firmware树的新候选尚待试验，详见[设备树审查](p35-overlay-audit.md)和[本轮实际状态](exp-hw-025-review-corrections-and-ttl.md)。原始历史过程保留如下。

- 日期：2026-10-20 23:00 左右（北京时间）
- 前置：[P34-merged-bitstream-hang.md](p34-merged-bitstream-hang.md)（整体替换失败、两次挂死、恢复成功）
- **本轮结论：合并位流本身是好的；把板子打死的是我们的设备树 overlay。**

## 1. 为什么先修了一个"格式陷阱"

第一次上板用的是 `write_bitstream` 直接产出的 `.bit`，它带 124 字节 ASCII 头（`00 09 0f f0 … 'a' "rf_display_top;COMPRESS=TRUE"`）。而厂家的 `display.bin` 是裸数据：

```
厂家 display.bin : ff ff … ff | 00 00 00 bb 11 22 00 44 | … | aa 99 55 66
我们最初的文件   : 00 09 0f f0 | 'a' + ASCII 头 + 二进制
```

`firmware-name` 是把文件**原样喂给 PCAP**，带 ASCII 头等于把垃圾当配置数据。**所以第一次测试无效** —— 设计从未被配置。

修正方式：`write_bitstream -bin_file` 重新生成，得到 5,034,448 B 的 `.bin`，结构为
`32×FF + 00 00 00 bb 11 22 00 44 + … + aa 99 55 66`，与厂家一致。

**不需要重传 5 MB**：`.bit` 与 `.bin` 只差 124 字节头，板上 `tail -c +125` 切掉后 sha256 与本地一致（`34eeb736…bdb6756`）。

## 2. 修正格式后仍然挂死

用正确格式再次整体替换（我们的位流 + 我们的 overlay）→ **同样挂死**，日志同样停在
`board-init: staged bitstream already current` 之后、没有任何 fpga_manager 或驱动日志。

**所以格式是另一个独立缺陷，不是挂死的原因。**

## 3. 二分实验：我们的 PL + 厂家设备树 = 能启动

### 3.1 关键机制（本轮才查清）

| 文件 | 作用 |
|---|---|
| `S99board` 把当前模式的位流 `cmp` 后拷成 `system_wrapper.bin` | 日志 `staged bitstream already current` |
| 厂家 `d480p.dtbo` 的 `firmware-name` 是 **`system_wrapper.bin`**（不是 `display.bin`） | `od -c` 实测 |

所以要测"我们的 PL + 厂家 DT"，只需把我们的位流同时写进 `display.bin` 和 `system_wrapper.bin`（让 staging 认为已是最新而跳过），**保留厂家 overlay**。

### 3.2 结果：启动成功

```
board-init: staged bitstream already current
fpga_manager fpga0: writing system_wrapper.bin to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Found swapped sync word
xilinx-vdma 43000000.dma: Xilinx AXI VDMA Engine Driver Probed!!
Console: switching to colour frame buffer device 100x30
xilinx-drm amba:xilinx_drm: fb0: frame buffer device
pwm-cadence f8001000.ttc_pwm: PWM 0/1/2 … at 111111115 Hz
backlight supply power not found, using dummy regulator
board-init: overlay applied: /lib/firmware/d480p.dtbo (attempt 1)
board-init: display ready: /dev/fb0 present
board-init: bring-up complete (mode=display)
```

运行态复核：

| 项 | 值 |
|---|---|
| `fpga_manager state` | **operating**（我们的合并位流） |
| `/dev/dri/` | `card0 controlD64` |
| `fb0 virtual_size` | `800,480` |
| `/sys/class/backlight/` | `backlight` |
| IIO | 仅 `iio:device0`（厂家显示 DT 本就不描述 AD9361，正常） |

**结论：合并设计的 PL 部分完全正常** —— VDMA、DRM、帧缓冲、背光（含 TTC 三通道）全部 probe 成功并稳定运行。

## 4. 所以问题定位到 overlay

已排除的方向：

| 方向 | 结论 | 依据 |
|---|---|---|
| 位流格式 | 已修正，非挂死原因 | 修正后仍挂 |
| AXI 地址错位 | **排除** | BD 地址 `0x7C400000 / 79020000 / 7C420000 / 43000000 / 43C10000 / 43C20000` 与 DTS 逐项一致 |
| `fpga_full` 段结构 | **排除** | 与厂家显示 overlay 除文件名外一致（`#address-cells`、`#size-cells`、`firmware-name`） |
| PL 设计本身 | **排除** | 本文第 3 节实测启动成功 |

剩余嫌疑集中在 **RF 侧节点**：`&spi1` 上的 `ad9361-phy@0`、`&amba` 上的 `dma@7c400000/7c420000`、`cf-ad9361-lpc@79020000`、`cf-ad9361-dds-core-lpc@79024000`。

它们依赖 PS 侧的 SPI/GPIO 配置，而 RF 工程与显示工程的 PS 初始化本来就不同（p29 文档记录过 UART1 MIO 48-49 vs 12-13、GPIO EMIO 64 vs 1、FCLK2 50 vs 250 MHz 等差异）。**合并的 PS 配置究竟沿用了哪一侧，尚未核对**。

## 5. 下一步（单变量，仍不需要重传位流）

在 rf 模式下测"我们的 PL + 厂家 RF overlay"：

1. 备份 `ad9361.bin`（约 17 MB）→ `ad9361.bin.vb`
2. `cp p32.raw ad9361.bin`
3. `board-mode rf`，重启

预期：

- **AD9361 三个 IIO 设备出现** → RF 侧节点在厂家 DT 下工作正常，问题在**我们的 overlay 把 RF 与显示节点组合**的方式
- **再次挂死** → 问题在 RF 侧节点与合并后 PS 配置不匹配（SPI/GPIO/时钟）

## 6. 当前板子状态（重要）

板子现在处于**混合状态**：

- PL 里跑的是**我们的合并位流**
- 设备树是**厂家的显示 overlay**
- 因此显示正常、但没有 AD9361

恢复厂家原状只需两条命令（备份都在）：

```sh
cd /lib/firmware
cp display.bin.vb display.bin
cp system_wrapper.bin.vb system_wrapper.bin
reboot
```

## 7. 证据

| 内容 | 路径 |
|---|---|
| 格式对比 | `results/p34-bitstream-format-check-20261020/` |
| 板上切头与哈希 | `results/p34-derive-raw-bin-20261020/` |
| 第二次挂死 | `results/p34-retry-verify-20261020/` |
| **二分安装与启动日志** | `results/p34-bisect1-install-20261020/`、完整启动日志见本轮抓取（19,527 B） |
| **二分运行态复核** | **`results/p34-bisect1-verify-20261020/`** |
| 厂家 overlay 备份 | `results/p34-stage-backup-20261020/` |
| 厂家 overlay 反编译 | `results/p31-board-contract-20261019T135528Z/factory-{rf,display}.dts` |

---

# 追加：另一半也通了 —— 射频侧在合并位流上初始化成功

上文第 5 节列的"下一步"已执行。结果把问题范围进一步收紧。

## B1. 实验设置

rf 模式下 `S99board` 的行为与显示模式不同：

| 模式 | 位流来源 | overlay |
|---|---|---|
| display | overlay 的 `firmware-name`（= `system_wrapper.bin`） | `d480p.dtbo` |
| **rf** | **脚本显式 `echo system_wrapper.bin > fpga_manager/firmware`** | `pl.dtbo`（无 `firmware-name`） |

所以要让 rf 模式用我们的位流，只需把 `ad9361.bin` 换成我们的裸数据（`cmp` 比较通过后 staging 会跳过拷贝）：

```
cp ad9361.bin ad9361.bin.vb        # 备份 17,416,348 B，sha256 65b44449…
cp p32.raw   ad9361.bin            # 我们的位流 sha256 34eeb736…
echo rf > /etc/board-mode
```

## B2. 结果：AD9361 完整初始化

```
board-init: mode=rf bitstream=/lib/firmware/ad9361.bin overlay=/lib/firmware/pl.dtbo
fpga_manager fpga0: writing system_wrapper.bin to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Found swapped sync word
board-init: fabric operating after explicit bitstream load
ad9361 spi32765.0: ad9361_probe : enter (ad9361)
ad9361 spi32765.0: ad9361_probe : AD936x Rev 2 successfully initialized
board-init: overlay applied: /lib/firmware/pl.dtbo (attempt 1)
cf_axi_adc 79020000.cf-ad9361-lpc: ADI AIM (10.00.b) at 0x79020000 … probed ADC AD9361 as MASTER
cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: … probed DDS AD9361
board-init: rf ready: PHY/ADC/DDS names verified (attempt 1)
board-init: bring-up complete (mode=rf)
```

运行态复核：

| 设备节点 | `name` |
|---|---|
| `iio:device0` | xadc |
| **`iio:device1`** | **ad9361-phy** |
| **`iio:device2`** | **cf-ad9361-lpc** |
| `iio:device3` | cf-ad9361-dds-core-lpc |

`fpga_manager state = operating`。

## B3. 二分表（完整）

| PL | 设备树 | 结果 |
|---|---|---|
| 我们的合并位流 | 厂家显示 overlay `d480p.dtbo` | **✅ 启动；DRM/fb0 800×480/背光正常** |
| 我们的合并位流 | 厂家射频 overlay `pl.dtbo` | **✅ 启动；AD9361 Rev 2 初始化，4 个 IIO 设备** |
| 我们的合并位流 | 我们的合并 overlay | **❌ 无输出硬挂死** |

**结论：合并位流的射频与显示两半都是好的。唯一有缺陷的是我们手工重建的那份合并设备树。**

这也顺带否掉了"CDC 导致挂死"的猜想 —— 同一个位流在两种厂家设备树下都稳定运行，VDMA、DRM、PWM、AD9361 全部正常。

## B4. 由此得到的修复路线（比调试自制 overlay 更稳）

既然两份厂家 overlay 都能在我们的位流上工作，**正确的合并方式不是"重建"，而是"忠实拼接"**：

1. 取 `factory-rf.dts`（fragment@1..3）与 `factory-display.dts`（fragment@0..2）原文
2. 重新编号 fragment（RF → 0/1/2，显示 → 3/4/5），同步改写 `__symbols__` 里的路径
3. 去掉反编译带出的 `__symbols__` / `__fixups__` / `__local_fixups__` 与旧 phandle，交给 `dtc -@` 重新生成
4. 仅把 `firmware-name` 改为我们的文件名
5. `dtc -@ -I dts -O dtb` 编译

项目里 `experiments/p31_build_overlay.py` 已有 `clean_body()` 等现成机制可复用。

**关键差别**：现成的自制 overlay 是"按理解重建"的（可能与厂家结构有细微但致命的差异），而拼接方案**逐字保留厂家原文**，只做编号重排。

## B5. 当前板子状态

- 模式：**rf**
- PL：**我们的合并位流**（`state=operating`）
- 设备树：厂家 `pl.dtbo`
- 射频：**可用**（4 个 IIO 设备）
- 显示：无（rf 模式本就没有 `/dev/fb0`）

**这是一个可用状态**，且是"我们的位流第一次真正跑起射频"。

## B6. 证据

| 内容 | 路径 |
|---|---|
| rf 模式准备（备份与哈希） | `results/p34-rf-mode-prep-20261020/` |
| rf 启动日志 | 本轮抓取 19,218 B |
| **rf 运行态复核** | **`results/p34-bisect2-rf-verify-20261020/`** |
