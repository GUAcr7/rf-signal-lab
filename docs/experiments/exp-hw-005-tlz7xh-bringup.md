# EXP-HW-005：TLZ7xH-EVM（Zynq-7100 + AD9361）首次上板确认

- 日期：2026-10-17。
- 本轮目标：确认这块新板到底能不能用、是什么器件、预装了什么、缺什么。
- 验收标准（事先定好）：①确认器件型号有**可复现证据**而非目测；②确认系统状态；③确认预装 PL 设计是什么；④给出可直接执行的下一步。
- 本轮性质：**只读探测**。未烧写、未改配置、未加载 bitstream、未动拨码。

## 1. 结论摘要

| 问题 | 答案 | 证据强度 |
|---|---|---|
| 是新板吗 | ✅ 是，主机名 `Zynq-Tronlong`，内核 4.9.0-rt | 串口实测 |
| 器件型号 | ✅ **XC7Z100（Zynq-7100）** | 板上 bitstream sha256 与 `ad_fmcomms3_ebz_xc7z100.bin` **完全相同** |
| 系统能否启动 | ✅ 已启动，直接 root 提示符，免密 | 串口实测 |
| 系统在哪 | ✅ **SD 卡**（`mmcblk0` 的 type 是 `SD`，`root=/dev/mmcblk0p2`） | 串口实测 |
| PL 配置了吗 | ❌ **未配置**（`fpga0/state = unknown`） | 串口实测 |
| 预装 PL 是什么 | ✅ **AD9361 射频设计**，不是显示设计 | `pl.dtbo` 节点 + bitstream 哈希 |
| 能收射频吗 | ⏳ 差一步：插上 AD-FMCOMMS3 模块并加载 PL | 推断，待验证 |
| 能显示屏幕吗 | ⚠️ 需要**另一个** bitstream，与射频设计**互斥** | 见第 5 节 |

## 2. 器件型号：用 bitstream 哈希钉死

目测丝印不可靠（用户反馈看不清），改用哈希比对：

| 项目 | 值 |
|---|---|
| 板上 `/lib/firmware/system_wrapper.bin` | 17,416,348 B，sha256 **`65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a`** |
| 资料 `ad_fmcomms3_ebz_xc7z100.bin` | 17,416,348 B，sha256 **`65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a`** |
| 资料 `ad_fmcomms3_ebz_xc7z045.bin` | 13,321,404 B，sha256 `cafb6e1dcda4badebc72d64313e287ff068538e74856b6a9a189447a76a0496b` |

**逐字节相同**，因此板上预装的是 **z100 版**。创龙不会把加载不了的 bitstream 放到板上，加之手册照片丝印为 `XC7Z100`、用户亦称"7100"，三方面一致。

**仍存的逻辑边界**：哈希证明的是"厂商装的是 z100 构建"，严格意义上不等于"硅片就是 z100"。**最终确认时刻是 PL 加载成功那一刻** —— PCAP 会校验器件 ID，不匹配会拒绝。见第 6 节。

## 3. 系统现状（串口实测）

```
root@Zynq-Tronlong:~#
Linux Zynq-Tronlong 4.9.0-rt1-xilinx-g0e07141-dirty #4 SMP PREEMPT Tue Sep 1 17:20:08 CST 2020 armv7l
```

| 项目 | 值 |
|---|---|
| 设备树 model | `TLZ7xH-EVM` |
| compatible | `xlnx,zynq-zc702`、`xlnx,zynq-7000`（基于 Xilinx ZC702 参考设备树改） |
| 内存 | 916,400 kB ≈ 895 MiB |
| CPU | 2× Cortex-A9（`CPU part 0xc09`），BogoMIPS 666.66 |
| 网络 | `eth0`、`can0`、`can1`、`lo`、`sit0`（**无 eth1**，PL 未配置故 PL 网口不存在） |
| 根文件系统 | `/dev/root`（`root=/dev/mmcblk0p2`）5.8 G，已用 913 M |
| IIO 工具 | `iio_info`、`iio_readdev`、`iio_attr` 均在 `/usr/bin` |
| libiio | **`/usr/lib/libiio.so.0.20`（0.20）** |
| 现有 IIO 设备 | 仅 `iio:device0` = **`xadc`**（Zynq 内部 ADC） |

### 3.1 一个容易搞错的存储细节

`mmcblk0` 的 `device/type` 是 **`SD`**，`mmcblk1` 是 **`MMC`**（eMMC）。

所以 **`root=/dev/mmcblk0p2` 表示系统在 SD 卡上**，不是 eMMC。手册要求的"SD 卡启动"确实生效了，**拨码开关已在正确位置，不要动**。

（eMMC `mmcblk1` 也在，14.9 GiB，三个分区，其中一个 4.1 G 挂在 `/run/media/mmcblk1p2`。）

### 3.2 libiio 版本差异（会影响旧工具复用）

| 板 | libiio |
|---|---|
| 旧 P201 | **0.24** |
| 新 TLZ7xH-EVM | **0.20** |

旧项目的 `arm-tx-source` 是针对 0.24 编译的，**大概率不能直接在新板上运行**。新板的接收程序要另编，或直接用板上的 `iio_readdev`。

## 4. 预装 PL 设计是射频，不是显示

### 4.1 `pl.dtbo` 的节点（提取自板上文件）

```
ad9361-phy@0                 (adi,ad9361)
cf-ad9361-lpc@79020000       (adi,axi-ad9361-6.00.a)      ← RX DMA
cf-ad9361-dds-core-lpc@79024000 (adi,axi-ad9361-dds-6.00.a) ← TX DMA/DDS
dma@7c400000 / dma@7c420000  (adi,axi-dmac-1.00.a)
clock: ad9361_ext_refclk / rx_sampl_clk / tx_sampl_clk
```

**全是 AD9361 相关节点，没有任何 display / lcd / fb / vdma / drm 节点。**

### 4.2 加载接口

`/sys/class/fpga_manager/fpga0/` 里有老式 **`firmware`** 写入节点（2017.4 时代内核风格）：

```
--w-------  firmware      ← 写入 bitstream 的入口
-rw-r--r--  flags / iv / key
-r--r--r--  name = Xilinx Zynq FPGA Manager
-r--r--r--  state = unknown        ← 当前未配置
```

`pl.dtbo` 里**没有 `firmware-name` 属性**，所以 overlay **不会自动加载位流**；必须手动先写 bitstream，再应用 overlay。

`configfs` 已编译进内核但**未挂载**（`/sys/kernel/config` 为空）。基础设备树里有 `fpga-full` 节点（含 `fpga-mgr` phandle），供 overlay 引用。

## 5. 射频与显示：随板提供的两个设计是互斥的

| 设计 | bitstream | 大小 | 含 AD9361 | 含显示 |
|---|---|---:|---|---|
| 板上预装 | `system_wrapper.bin` | 17,416,348 B | ✅ | ❌ |
| 资料 demo | `axi_video_display_demo_xc7z100.bin` | 3,346,176 B | ❌ | ✅ |

**两者不能同时满足"收射频 + 屏幕显示"。** 这是本轮最重要的架构结论：

- 板上**没有**同时含射频与显示的现成位流
- 引脚层面两者不冲突（64 vs 53 引脚，重叠 0，见 [新板审查](../design/new-board-tlz7xh-evm-review-20261017.md) 第 5 节）
- 所以"边收边显示"必须**自己做一份合并设计**（AD9361 采集链 + VDMA + LCD），或退化为两步演示（先收存盘，重启加载显示位流再回放）

## 6. 下一步（按依赖顺序）

### 步骤 A：插上 AD-FMCOMMS3 模块（需要用户操作，**先断电**）

- 位置：右侧 `FMC` 400pin 连接器
- 断电 → 插入 → 确认卡扣 → 重新上电
- **不插模块，加载射频位流也不会成功**：`ad9361-phy` 驱动要经 SPI 读芯片 ID，读不到就 probe 失败

### 步骤 B：加载 PL 位流（我在串口上做，可逆）

```sh
cat /lib/firmware/system_wrapper.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state      # 期望 operating
```

**这一步同时是器件型号的最终验证**：若硅片不是 z100，PCAP 会拒绝并报错，state 不会变成 `operating`。

### 步骤 C：应用 overlay

```sh
mount -t configfs none /sys/kernel/config
mkdir -p /sys/kernel/config/device-tree/overlays/pl
cat /lib/firmware/pl.dtbo > /sys/kernel/config/device-tree/overlays/pl/dtbo
```

### 步骤 D：验证接收链（只读）

```sh
iio_info -s            # 应出现 ad9361-phy 与 cf-ad9361-lpc
iio_info               # 读采样率、带宽、增益等属性
```

成功判据：`iio_info` 列出 `ad9361-phy`、`cf-ad9361-lpc`、`cf-ad9361-dds-core-lpc`，且能读到 RX 采样率属性。

## 7. 本轮实际执行过的命令（全部只读）

`uname -a`、`cat /proc/device-tree/model`、`cat /proc/meminfo`、`cat /proc/cpuinfo`、`ls /sys/class/net`、`df -h`、`cat /sys/class/fpga_manager/fpga0/state`、`ls /dev/fb* /dev/iio* /dev/video*`、`cat /sys/class/iio/device0/name`、`ls /sys/devices/soc0/`、`cat /sys/devices/soc0/soc_id`、`cat /proc/cmdline`、`cat /proc/partitions`、`cat /sys/block/mmcblk0/device/type`、`ls /lib/firmware`、`mount | grep configfs`、`tr ... < /lib/firmware/pl.dtbo`、`sha256sum /lib/firmware/system_wrapper.bin`、`which iio_*`、`lsmod`、`ls -l /sys/class/fpga_manager/fpga0/`。

**没有**执行任何写操作、加载、挂载、拨码变更或文件修改。

## 8. 证据

| 内容 | 路径 |
|---|---|
| 身份探测（transcript.json） | `results/p15-newboard-identify-20261017/` |
| PL 状态与设备节点 | `results/p15-newboard-pl-state-20261017/` |
| SoC / IIO / cmdline | `results/p15-newboard-socid-20261017/` |
| 存储与分区类型 | `results/p15-newboard-storage-20261017/` |
| 固件文件与 overlay 内容 | `results/p15-newboard-firmware-20261017/` |
| **bitstream 哈希比对** | `results/p15-newboard-bitstream-hash-20261017/` |
| IIO 工具链 | `results/p15-newboard-iio-tools-20261017/` |
| fpga_manager 接口 | `results/p15-newboard-fpgamgr-20261017/` |
| 串口工具 | `experiments/p15_serial_identify.py`、`experiments/p15_serial_cmd.py` |

---

# 追加：接收链已打通（2026-10-17 同日晚）

## A. 结论

**新板 TLZ7xH-EVM 的 AD9361 接收链已完整可用。** 四个 IIO 设备全部出现，AD9361 芯片识别成功：

```
ad9361 spi32765.0: ad9361_probe : enter (ad9361)
ad9361 spi32765.0: ad9361_probe : AD936x Rev 2 successfully initialized
```

```
iio_info -s:
Available contexts:
	0: (cf-ad9361-dds-core-lpc, ad9361-phy, cf-ad9361-lpc, xadc on TLZ7xH-EVM) [local:]
```

## B. 加载步骤（已实测可复现）

```sh
# 1. 写文件名，不是写位流本体（见 B.1 的坑）
echo system_wrapper.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state        # -> operating

# 2. 挂 configfs 并应用 overlay
mount -t configfs none /sys/kernel/config
mkdir -p /sys/kernel/config/device-tree/overlays/pl
cat /lib/firmware/pl.dtbo > /sys/kernel/config/device-tree/overlays/pl/dtbo
```

内核日志：

```
fpga_manager fpga0: writing system_wrapper.bin to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Found swapped sync word
ad9361 spi32765.0: ad9361_probe : AD936x Rev 2 successfully initialized
```

### B.1 踩到的坑：`firmware` 要文件名，不是二进制

第一次我按"直接喂位流"的常见写法做了：

```sh
cat /lib/firmware/system_wrapper.bin > /sys/class/fpga_manager/fpga0/firmware   # 错
```

内核把它当**文件名字符串**解析，于是：

```
fpga_manager fpga0: writing \xffffffff\xffffffff... to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Direct firmware load for \xffffffff... failed with error -2
fpga_manager fpga0: Error requesting firmware \xffffffff...
```

`state` 变成 `firmware request error`，PL 未配置。改成 `echo system_wrapper.bin >` 后成功。

**这个内核（4.9.0-rt1-xilinx）的 `fpga0/firmware` 是"固件名"属性，走 request_firmware 从 /lib/firmware 加载，不是流式写入口。**

## C. 器件型号最终确认

`state = operating` 意味着 **PCAP 校验并接受了 z100 位流**。若硅片是 ZC7Z045，器件 ID 不匹配会被拒绝。

因此 **[EXP-HW-005 第 2 节](#2-器件型号用-bitstream-哈希钉死)里"哈希只能证明厂商装的是 z100 构建"的保留意见，现已解除：硅片确为 XC7Z100。**

## D. AD9361 默认配置与旧板逐项相同

| 属性 | 新板实测 | 旧 P201 |
|---|---|---|
| `in_voltage_sampling_frequency` | **30720000** | 30720000 |
| `in_voltage_rf_bandwidth` | **18000000** | 18000000 |
| `out_altvoltage0_RX_LO_frequency`（默认） | **2400000000** | 2400000000 |
| `in_voltage0_gain_control_mode` | **slow_attack** | slow_attack |
| `in_voltage0_rf_port_select` | **A_BALANCED** | A_BALANCED |
| `in_voltage0_hardwaregain` | **71.000000 dB** | 71.000000 dB |
| `rx_path_rates` | `BBPLL:983040000 ADC:245760000 R2:122880000 R1:61440000 RF:30720000 RXSAMP:30720000` | 同 |

**两块板的 AD9361 默认 profile 完全一致**（ADI FMCOMMS3 标准配置）。这意味着旧项目在接收侧的参数选择与 DSP 假设可以直接沿用，不需要重新标定采样率。

可用端口：`A_BALANCED B_BALANCED C_BALANCED A_N A_P B_N B_P C_N C_P TX_MONITOR1 TX_MONITOR2 TX_MONITOR1_2`。

## E. 已执行的本振设置

```sh
echo 2450960000 > out_altvoltage0_RX_LO_frequency    # 读回 2450960000
echo 2450960000 > out_altvoltage1_TX_LO_frequency    # 读回 2450960000
```

对齐旧板发射频点 2.450960 GHz（旧板 TX_LO 2.45 GHz + 数字偏移 +960 kHz）。

**这是运行时可逆配置，未写 flash、未改启动文件。**

## F. 串口工具的一个限制（重要）

Zynq 控制台在约 **80 列**处折行，长命令会被从中间截断，BusyBox sh 停在 `>` 续行提示符上。表现症状是命令回显里出现 `in_volta ge_sampling_frequency` 这样的空格断词。

因此：
- 发送的命令必须 **≤72 字符**（留余量）
- 需要长路径时先 `cd`，再执行短命令（同一会话内 `cd` 会保持）
- 工具改为**静默判定**而非长标记：`experiments/p15_serial_read.py`
- 每次运行开头发两次 Ctrl-C，清掉残留的续行状态

**PowerShell 侧还有两个坑**（本轮各踩一次）：双引号字符串里的 `$?` 和 `$p` 会被 PowerShell 先展开；含 `$` 的命令必须用单引号。

## G. 证据

| 内容 | 路径 |
|---|---|
| 加载前的板卡状态 | `results/p15-newboard-preload-20261017/` |
| 错误加载方式（\xff 被当文件名） | `results/p15-newboard-load-pl-20261017/`、`results/p15-newboard-load-pl-check-20261017/` |
| **成功加载 + state=operating** | `results/p15-newboard-load-pl2-20261017/` |
| **overlay 应用 + ad9361 probe 成功** | `results/p15-newboard-overlay-apply-20261017/` |
| IIO 设备与上下文 | `results/p15-newboard-iio-check-20261017/` |
| 属性清单与逐项取值 | `results/p15-newboard-ad9361-attrs-20261017/`、`results/p15-newboard-ad9361-values-20261017/` |
| 新串口工具 | `experiments/p15_serial_read.py` |
