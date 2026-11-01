# EXP-TX-001：首次真实射频发射（已知单音，3 秒）

- 日期：2026-10-16（Asia/Shanghai），17:50 前后。
- 平台：璞致 PZSDR P201，Zynq-7020 + AD9361，libiio 0.24。
- 状态：**首次真实射频发射已实际执行（板卡日志与频谱照片均可证）；第二支不同偏移的单音也已实际执行。**
- **但精确频率与功率尚未验收**：唯一已归档的仪器照片上，标记停在显示伪影而非主峰（`2.45 GHz / -56.24 dBm`），主峰仅目视可见；写有 `2.4509625 GHz / -24.43 dBm` 的那张照片**当时未保存**。取证缺口与更正见第 5 节顶部。
- 仍未完成：主峰标记照片（频率+功率）、`Ref Level` 复测、TX SMA 端口映射的仪器侧确认、相对功率随衰减变化的验证、真实 RX 采集与三类调制验收。

本记录只登记"板卡侧确实发射了、并且是受控地发射"，**不声称**频率/功率/带宽已验收——那些必须等频谱分析仪的实测数字。

## 1. 发射前的供电故障与修复（同一晚）

首次尝试前发现 AD9361 读回非法，发射被程序守卫拦下，详见 [EXP-HW-004](exp-hw-004.md)。用户改用 **5V/1A 供电加强线、直插电脑 USB 口、不经集线器**后冷启动，读回恢复正常：

| 属性 | 异常时 | 修复后 |
|---|---|---|
| PHY TX `sampling_frequency` | `85727126` | `30720000` |
| PHY RX `sampling_frequency` | `85727126` | `30720000` |
| TX0/TX1 `hardwaregain` | `-16383.750000 dB` | `-10.000000 dB` |
| `rf_port_select` | `A` | `A` |
| `TX_LO` / `RX_LO` | `2450000000` / `2400000000` | 同 |
| `rf_bandwidth` | `18000000` | `18000000` |

**这是供电根因的第一次正向验证**：同一块板、同一固件，只换供电条件，非法读回消失。证据：`results/p13-post-powerfix-20261016-1735/`。

## 2. 本次发射的确切配置

**全部沿用板卡既有设置，程序未写任何射频参数。**

| 项目 | 值 | 来源 |
|---|---|---|
| 波形文件 | `existing30m72/tone-positive.iq16le` | 交付包（15 个已校验波形之一） |
| 文件 SHA256 | `36cd4ed7007721dd023b7b2c8b581a5ddb6f0365d9c0c0a40fef7c87522a0727` | 板端 `--check` 与主机双方一致 |
| 样本数 | `131072` | manifest |
| 采样率 | `30720000` | 板端读回 |
| TX LO | `2450000000` | 板端读回 |
| TX 带宽 | `18000000` | 板端读回 |
| TX 增益 | `-10` dB（数字衰减） | 板端读回 |
| 端口 | `A`（预期对应 TX1 SMA，**尚未实测确认**） | 板端读回 |
| 时长 | `3` 秒 | 本方案 |
| 预期信号频率 | **2.45096 GHz**（LO + 960 kHz 数字偏移） | 波形参数 |
| 预期载波泄漏 | **2.45000 GHz** | 芯片特性，与数字内容无关 |

板端离线检查输出：

```text
INPUT_SHA256=36cd4ed7007721dd023b7b2c8b581a5ddb6f0365d9c0c0a40fef7c87522a0727
INPUT_CHECK_PASS samples=131072 format=LE_s16_IQ low_bits_zero=4 min=-8192 max=8192 mean_I2_Q2=67097408
```

## 3. 身份门禁与使用的程序版本

本板 `hw_serial` **为空**，因此：

- 15:35 交付包里的旧版程序（源 `626f5797…`、ELF `5e242107…`）在 `--run` 会要求"非空且完全匹配的序列号"，**在本板上必然自拒**，不可用于发射。
- 本次使用 15:39 修订版：源 `b9ba90d3ec85359e5b584704702e80d544ffb26e1fd28c271563316d1e41dd30`、ELF `0a188e1e1c0c19a165231c1d5589ff5d72adbf284d98d2bdf39cfc6a65b1163b`。该版在 `hw_serial` 为空时回退到 `/proc/sys/kernel/random/boot_id`，要求严格非空 UUID。
- 实际使用的守卫身份：

```text
tx_guard_identity_kind=boot_session
tx_guard_identity=boot-session:b774f2cd-a5d9-4980-b802-e47680b0e883
```

**限制**：`boot_id` 只标识"这一次启动会话"，**重启即变**，不是永久硬件序列号。因此每次发射前都必须重新读取并核对，不能沿用上一次的值。

## 4. 发射过程实测输出（板端）

```text
DDS_ZERO_SOURCE_READBACK=PASS
CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=3
TX_SOFTWARE_DEADLINE_END elapsed_seconds=3.03109377 stop_signal=0
DDS_ZERO_SOURCE_READBACK=PASS
TX_CLEANUP buffer_released=true rf_settings_written=false status=0
LIMITATION software_deadline_not_hardware_interlock RF_silence_and_LO_leakage_unverified
```

逐条解释：

| 输出 | 含义 |
|---|---|
| `rf_settings_written=false` | **程序没有写任何射频参数**；所有值都是发射前读回并与请求精确比对通过的 |
| `elapsed_seconds=3.03109377` | 3 秒本地单调时钟截止生效；比 3 秒多的 31 ms 是收尾开销 |
| `stop_signal=0` | 由**时长截止**正常结束，不是被 Ctrl-C 或信号打断 |
| `buffer_released=true` | cyclic 缓冲已 `cancel` + `destroy`，DMA 未留下 |
| `DDS_ZERO_SOURCE_READBACK=PASS` ×2 | 发射前把 8 个 DDS 通道置零；收尾后再次置零并**读回确认** |
| 收尾后 `dds0..7_scale=0.000000` | 发射后数字源确为零 |
| `RF_silence_and_LO_leakage_unverified` | **程序自己声明**：软件截止不等于射频绝对静默，本振泄漏未在硬件上验证 |

## 5. 频谱分析仪读数

> **✅ 2026-10-17 00:5x 已补到合格证据，原缺口关闭。**
>
> 新归档照片 `results/p13-session2-peak-20261017T0100/marker-on-main-peak.jpg`（sha256 `844909957bf782bd0001d756d6562121bfdda17de6f6b4d3ce3b3a285c022944`）上，**标记落在主峰上**：
>
> ```
> Mkr1 Freq: 2.450962500 GHz
> Mkr1 Ampt: -24.57 dBm
> Trace: Max Hold        Ref Level: 0 dBm（顶端刻度 0，网格 10 dB/格）
> ```
>
> **与 10-16 17:23 那次未归档读数（2.450962500 GHz / -24.43 dBm）频率完全相同、幅度仅差 0.14 dB** —— 说明当时的口头抄录数值本身准确，缺的只是照片。
>
> 下列原始缺口说明保留以便追溯；其"未验收"结论已被本次取证取代。

> ## ⚠️ 证据完整性更正（2026-10-16 晚，由另一会话独立核对后追加）
>
> 本节初版把 **2.450962500 GHz / −24.43 dBm** 当成"已实测读数"却**没有保存对应照片**。原因有两条：
>
> 1. **当时已归档的那张照片上，标记并不在主峰上。** `results/p13-tx-m2b-5s-20261016-1800/analyzer-first-signal.jpg`（sha256 `8a8c5763…`）实际读数是 **`Mkr1 2.450000000 GHz / −56.24 dBm`**；主峰另在约 −30 dBm、中心右侧约 0.96 格处，但没有标记落在它上面。该照片不能证明主峰频率或功率。
> 2. **写有 `Mkr1 2.450962500 GHz / −24.43 dBm` 的那张照片（仪器时间 17:23:06）从未保存到磁盘。**
>
> **教训（已采纳为约定）**：仪器的每一个结论性数字，必须同时保存**标记落在被测峰上的那张照片**；口头读数先写进记录时须标注"未归档、待补图"，不得当作已验收证据。

### 5.1 已验收的读数（2026-10-17 00:5x 归档）

| 项目 | 值 | 判定 |
|---|---|---|
| Marker 频率 | **2.450962500 GHz** | 与理论 2.450960000 GHz 相差 **+2.5 kHz** |
| 该读数的分辨率 | **12.5 kHz 网格**（Span 10 MHz / 801 点） | ⚠️ 精度上限 **±6.25 kHz ≈ ±2.6 ppm**，**不足以支撑 1 ppm 结论**（见 §5.2 撤回说明） |
| Marker 电平 | **-24.57 dBm**（`Atten 20 dB`，`Ref 0 dBm`） | 分析仪**输入口**功率，非绝对校准值 |
| 重复性 | 与 17:23 读数差 **0.00 kHz / 0.14 dB** | 良好 |
| 主峰形状 | 陡升 + 右肩裙边 | 与单音经量化后的期望形状一致 |

**边界**：`-10 dB` 是板卡 TX **数字衰减读数**，不等于任何 dBm 值；接头与线缆损耗未标定。因此 −24.57 dBm 可用于**同条件相对比较**与**保守链路预算**，不能当绝对功率校准值。

### 5.2 负偏移发射与"两个峰同屏"（2026-10-17 01:1x 归档）

Max Hold 未清除，因此第二次发射（`tone-negative`，−960 kHz）的峰与上一次（`tone-positive`，+960 kHz）的峰**同时留在屏上**。这张图比单个峰更有价值：

`results/p13-session2-tx-neg-20261017T0120/marker-on-negative-peak-both-visible.jpg`
（sha256 `3106073d40719107ac191e82c0d77df670c3420566edec52a266cad8fc3c0958`）

| 峰 | 实测 | 理论 | 误差 |
|---|---|---|---|
| 负偏移 | **2.449037500 GHz** | 2.449040000 GHz | **−2.5 kHz** |
| 正偏移 | **2.450962500 GHz** | 2.450960000 GHz | **+2.5 kHz** |
| 两峰间隔 | **1.925000 MHz** | 1.920000 MHz | **+5.0 kHz** |

Marker 读数：负峰 **−24.22 dBm**（`Attn 20 dB`、`Ref 0 dBm`），与正峰 −24.57 dBm 相差 0.35 dB，**同配置下功率一致**。

#### 由此推出的一个定量结论：本振偏置 +2.5 kHz

> ## 🚫 此结论已撤回（2026-10-17 03:5x）
>
> **"+2.5 kHz 本振偏置"是错的。** 这两张照片是 **Span 10 MHz / 801 点**，标记只能落在 **12.5 kHz 网格**上；真实偏移 ±960 kHz = **±76.8 格**，四舍五入到 ±77 格正是 **±962.5 kHz**。所以**即使本振偏置恰好为 0**，这台仪器也会显示 +962.5 / −962.5 kHz 和 1.925 MHz 的间隔 —— 与记录完全一致。
>
> 复算：`experiments/p13_marker_grid_analysis.py` → `RESULT: zero LO offset reproduces both readings and the 5 kHz gap`。
>
> **该照片能支撑的频率精度上限是 ±6.25 kHz（半个网格步长）≈ ±2.6 ppm**，不足以支撑 1 ppm 量级的结论。更精细的测量见 [EXP-P13-OBW](exp-p13-obw.md) 第 6.2 节：用 1 MHz / 801 点（1.25 kHz 网格）测得与理论一致到 **约 ±2 kHz（±0.8 ppm）**。
>
> 下面保留被推翻的原始推理，以便追溯。

两个偏移的误差**大小相等、方向相反**（−2.5 / +2.5 kHz），而间隔误差正好是 **+5.0 kHz**。这曾被解释为**本振本身偏 +2.5 kHz**（相对 2.45 GHz 为 **+1.02 ppm**）的特征：

```
f_measured = f_LO_actual + f_digital_offset
若 f_LO_actual = 2.45 GHz + 2.5 kHz，则
  正偏移峰误差 = +2.5 kHz， 负偏移峰误差 = -2.5 kHz
  两峰间隔 = 1.92 MHz + 5.0 kHz     ← 与实测完全一致
```

**该推理的缺陷**：没有先检查读数本身的分辨率。±2.5 kHz 只有网格步长（12.5 kHz）的 1/5，**在这个分辨率下不可分辨**。

**同时确认的另一件事**：两次发射之间**没有关闭 Max Hold**，而两个峰位置稳定、没有漂移或展宽，说明两次发射的载波频率在分钟级时间尺度上重复性良好。

仪器：**RIGOL RSA3030**（Real-time Spectrum Analyzer，9 kHz–3 GHz，带跟踪源）。用户拍摄面板确认 `RF Input 50Ω +30 dBm / 50 VDC Max`。板卡 TX1 经 50 Ω SMA 同轴线直连分析仪 **RF Input**，**未使用衰减器**（上限 +30 dBm，且按最小数字幅度 + 5 秒短时长执行）。全程**未接第二块板的 RX**。

观察条件：Center 2.45 GHz、Span 10 MHz（**每格 1 MHz**）、RBW 25.114 kHz、`Atten 20.00 dB`、`Ref Level -20 dBm`、Trace **最大保持（Max Hold）**。

### 5.1 第一次发射（3 秒，offset +960 kHz）

**已归档照片的实测内容**（`results/p13-tx-m2b-5s-20261016-1800/analyzer-first-signal.jpg`，sha256 `8a8c5763299630c570cc79ed01a094b6596895d7f52a8a96004feee5fa33b39c`）：

| 项目 | 照片上的值 |
|---|---|
| 标记读数 | `Mkr1 2.450000000 GHz` / `-56.24 dBm` |
| 标记性质 | **不在主峰上**；该位置的真实迹线并未抬高，判定为 Density 余辉竖线的显示伪影 |
| 主峰 | 目视约 **-30 dBm**，位于中心右侧约 0.96 格（≈ +960 kHz） |
| 理论预期 | 2.450960000 GHz（LO 2.45 GHz + 960 kHz） |
| 主峰形状 | 陡升 + 右侧裙边/肩部，符合 RRC 成形特征 |

**未归档的口头抄录（不得当作证据）**：仪器时间 17:23:06 那次读数为 `Mkr1 2.450962500 GHz` / `-24.43 dBm`，即与理论相差 +2.5 kHz。该数字**待用一张标记落在主峰上的新照片重新采集**。

**待确认**：`Ref Level -20 dBm` 与峰值过近，前端可能已压缩、读数偏低。需把 `Ref Level` 改为 `0 dBm` 后连同标记一起重新拍照归档。

### 5.2 频率机动性验证（第二次发射，5 秒，offset +1.92 MHz）

单靠一个峰无法区分"我们数字搬频后的单音"和"恰好在那里的环境发射源"。因此生成第二支**已知偏移**的单音复测一次：

| 项目 | 值 |
|---|---|
| 波形 | `results/p13-agility-waveform-20261016T093417Z/tone-double-offset.iq16le` |
| SHA256 | `4aa0564fc0061ca2410795222637f812e8d246fc42ae7c6a088f18b9e6ec6362` |
| 偏移 | `1 920 000 Hz`（`cycles = 8192`，整数、bin 相干） |
| 预期峰 | `2 451 920 000 Hz` |
| 生成器 | `experiments/p13_prepare_agility_tone.py` |

生成侧独立校验：重新生成字节完全一致、低 4 位为 0、逻辑峰值 512、**FFT 主峰精确落在 1 920 000.0 Hz**、主峰比次高强 **80.3 dB**。

板端独立校验（ARM 版 `--check`，不是 x86 主机版）：

```text
INPUT_CHECK_PASS samples=131072 format=LE_s16_IQ low_bits_zero=4 min=-8192 max=8192 mean_I2_Q2=67105408
```

**反向对照**：故意传入错误 SHA256 时校验器输出 `input SHA256 mismatch` 并拒绝（退出码非 0），证明该校验确实在起作用，不是空跑。第一支波形复检仍为 `INPUT_CHECK_PASS ... mean_I2_Q2=67097408`，与第二支仅差约 **0.0005 dB**，因此两次发射的功率可直接比较。

**结果（证据等级：仅文字观察，无仪器图像）**：用户在 2.45192 GHz（中心右侧 1.92 格）报告观察到新的峰值。

**⚠️ 这条结论目前只有口头记录，没有归档照片。** 它支持"峰值随数字偏移移动"这一判断，但**不足以单独支撑"频率精度已验收"**。补证方法：清 `Max Hold` → 重新发射 → **用标记落在主峰上的照片**归档（见第 5 节顶部更正）。

若补证成立，则可支持：

- 发射频率由我们的数字波形决定，`f = f_TX_LO + f_offset` 在本板成立；
- 环境中不存在恰好落在这两个位置的固定干扰源，先前顾虑被排除；
- **发射侧的完整数字链**（Python 波形 → 包 → IIO 写缓冲 → DMA → AD9361 DAC → 板上 PA → TX SMA）通畅。

## 6. 本轮明确没有做的事

- **未改任何射频参数**：采样率、增益、本振、带宽、端口全部沿用板卡既有值（`rf_settings_written=false`）。
- 未改固件、未烧写、未动 FPGA 工程、未动设备树、未接第二块板、未接天线、未改 Git。
- 未做长时间或循环发射：单次 3 秒，程序最大允许 60 秒。
- 未把本次结果当成 P03 验收完成：P03 还要求正/负偏移、固定增益下改变已知衰减验证相对功率、以及三类调制的真实采集。

## 7. 证据位置

| 内容 | 路径 |
|---|---|
| 供电修复后的正常读回 | `results/p13-post-powerfix-20261016-1735/` |
| 新版 ARM 程序上传与校验 | `results/p13-upload-newarm-20261016-1737/` |
| 板端解包、ELF 校验、`--inspect` | `results/p13-board-inspect-newarm-20261016-1739/` |
| 波形包上传 | `results/p13-upload-waveforms-20261016-1743/` |
| 波形解包与 `--check` | `results/p13-waveform-verify-20261016-1747/` |
| **本次发射全过程** | `results/p13-first-tx-m2-20261016-1750/` |
| 波形包留存副本 | `results/p13-waveform-bundle-20261016/waveforms-existing30m72.tar`（SHA256 `1bde45e83ec416c6f219d3f4ef89c2bda973eb475bdeff5d5693e1fdd2ece50d`） |
| 前置故障记录 | [EXP-HW-004](exp-hw-004.md) |
| 发射方案与仪器限制 | [first-rf-transmit-spectrum-plan.md](../design/first-rf-transmit-spectrum-plan.md) |

每个 `results/` 目录含 `serial-transcript.txt`（串口逐字记录）与 `report.json`（命令+退出码）。
