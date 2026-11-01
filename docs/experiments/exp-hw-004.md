# EXP-HW-004：AD9361 上电后通道属性异常（发射前拦截）

- 日期：2026-10-16（Asia/Shanghai），17:05–17:25。
- 平台：璞致 PZSDR P201，Zynq-7020 + AD9361，libiio 0.24，内核 5.10.0-98231-g9dfba10b795d-dirty。
- 现象：计划进行**首次受控射频发射**前的只读核对时，发现射频芯片的采样率与发射增益读数非法。
- 结论：**板卡本次上电后 AD9361 未进入可用状态；发射被程序自身守卫拦截，未产生任何射频输出。**
- 本轮只读：没有写任何射频参数、没有创建 DMA/IIO 缓冲、没有发射、没有改固件/设备树/FPGA。

## 1. 为什么会在这一步发现

用户已把频谱分析仪接到 P201 的 **TX1**，并确认分析仪 `RF Input 50Ω +30 dBm / 50 VDC Max`（见 [首次发射方案](../design/first-rf-transmit-spectrum-plan.md) 第 0 节）。按方案，发射前必须先只读确认发射程序守卫要求的五项设置与请求精确一致。这次核对就是在这个环节发现异常，**因此发射没有开始**。

## 2. 实测读数（17:15 与 17:22 两次一致）

来源：`results/p13-pre-tx-iio-20261016-1715/`、`results/p13-pre-tx-iio-full-20261016-1722/`。

| 属性 | 本次实测 | 15:36 的正常值（`results/p12-board-source-check-20261016-153621/`） | 判定 |
|---|---|---|---|
| `out_voltage_sampling_frequency`（PHY TX） | `85727126` | `30720000` | **非法** |
| `out_voltage0.sampling_frequency`（TX0 通道） | `21431781` | `30720000` | **非法** |
| `in_voltage_sampling_frequency`（PHY RX） | `85727126` | 由 RX 通道报 `30720000` | **非法** |
| `out_voltage0_hardwaregain`（TX0） | `-16383.750000 dB` | `-10.000000 dB` | **远超合法范围** |
| `out_voltage1_hardwaregain`（TX1） | `-16383.750000 dB` | `-10.000000 dB` | **远超合法范围** |
| `voltage_filter_fir_en`（TX FIR） | 非 0，抽取/插值比报 `961538` | `0`（旁路） | **8 倍插值链未正确初始化** |
| `in_voltage0_hardwaregain`（RX0） | `36.000000 dB`（会话中读到过 3 dB） | `71.000000 dB`（AGC slow_attack 瞬时值） | 随 AGC 波动，不作判据 |
| `out_voltage_rf_bandwidth` | `18000000` | `18000000` | 正常 |
| `out_voltage0_rf_port_select` | `A` | `A` | 正常 |
| `out_altvoltage1_TX_LO_frequency` | `2450000000` | `2450000000` | 正常 |
| `out_altvoltage0_RX_LO_frequency` | `2400000000` | `2400000000` | 正常 |
| `in_voltage0_rf_port_select` | `A_BALANCED` | `A_BALANCED` | 正常 |

**关键判据**：`hardwaregain_available` 明确报出 TX 的合法范围是 `[-89.750000 0.250000 0.000000]`，而实测 `-16383.75` 比下限还低约 16300 dB。这不是"某个设置被改成另一个合法值"，而是**读回本身就不可信**，属于初始化失败而非配置变更。

**另一个内部矛盾**：同一块芯片上 TX 采样率在不同属性处报 `85727126` 与 `21431781`；TX FIR 报 `961538`。三者互不相容，说明数字接口/插值链没有建立起一致的速率关系。

## 3. 内核日志与状态的不一致

```text
ad9361 spi0.0: ad9361_probe : enter (ad9361)
ad9361 spi0.0: ad9361_probe : AD936x Rev 0 successfully initialized
cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: ... probed DDS AD9361
cf_axi_adc 79020000.cf-ad9361-lpc: ADI AIM (10.01.b) at 0x79020000 mapped to 0x(ptrval), probed ADC AD9361 as MASTER
```

驱动报告 "successfully initialized"，且 `cf-ad9361-lpc`（接收采样接口）**本次已注册**——这一点与 [EXP-HW-003](exp-hw-003.md) 的"缺少接收设备"不同。但通道属性仍是非法值。所以**"probe 成功"不能当作"芯片配置正确"**，必须以属性读回为准。

## 4. 板卡重启与临时文件

`uptime` 显示 `up 12 min`，即板卡在 17:00 前后重新启动过。`/tmp` 是 tmpfs（514 MB），**重启即清空**：

```text
/tmp/p12-source-stage-*  → NO_STAGE_DIR
PACKAGE_GONE
```

15:35 那次上传的 1.58 MB 交付包已不存在。重新上传是下一步的前置条件，不是异常。

## 5. 与历史记录的对照：同一现象第三次出现

| 日期 | 记录 | 现象 |
|---|---|---|
| 2026-09-23 | [EXP-HW-003](exp-hw-003.md) | TX 数字接口时序训练失败（`Tuning TX FAILED!`），`cf-ad9361-lpc` probe 失败、接收设备缺失 |
| 2026-09-28 | [EXP-P03](exp-p03.md) 第14行 | 首次启动 CHIP_ID 错误，一次正常软件重启后消失，**根因未定** |
| 2026-10-16（本次） | 本文件 | 设备全部注册，但 TX/RX 采样率与 TX 增益为非法值 |

三次都是**上电后的 AD9361 初始化问题**，表现不同但都属于"启动状态不可靠"。[EXP-HW-003](exp-hw-003.md) 第49–51行已经写明处置方向：

> 先核对供电和原厂配套线，必要时在明确可靠的 5V/1A 供电条件下做一次有记录的冷启动；保留新的启动日志和 IIO 设备名。

## 6. 供电：本次已确认的可疑根因

用户确认：**板卡用的是普通 USB 线，并且接了 USB 集线器**。

而项目自己记录的原厂要求是（[platform-notes.md](../platform-notes.md) 第28行）：

> 离 RJ45 较远的 JTAG_UART/PWR 用于供电和串口 … Pluto 教程第 6 页规格为 **5V/1A（USB 供电加强线）**

一根普通 USB 线 + 集线器同时承担**供电与串口**，是最可能的原因。**这是待验证的推断，不是已证实的根因**；本轮没有测量板卡输入电压或电流。

## 7. 发射为什么被拦下（安全行为，不是缺陷）

发射程序 `arm-tx-source --run` 要求当前设置与请求**精确相等**，否则退出且不写任何配置（`embedded/arm_tx_source/arm_tx_source.c` 第378–386行）：

```c
attr_number(p,"sampling_frequency",&actual) || actual!=(double)fs || ...
→ "current RF/DMA settings do not exactly match request; ... no configuration is written"
```

`85727126 ≠ 30720000`，因此程序会直接退出。**这次是守卫在起作用**：如果程序改成"自动改设置以匹配请求"，就会在一个状态不明的芯片上开始发射。这条设计原则应当保留。

## 8. 本轮明确没有做的事

- 未发射：没有调用 `--run`，没有任何射频输出，频谱分析仪上不应出现信号。
- 未写射频参数：**没有**用 `echo` 写 `out_voltage_sampling_frequency` / `hardwaregain` 等属性把它们"修回去"。这两个属性在 sysfs 中是 `-rw-r--r--`（可写），但**本轮刻意没写**，因为写它们属于状态变更，会掩盖而不是解决初始化问题。
- 未改固件、未烧写、未动 FPGA 工程、未动设备树、未接第二块板、未改 Git。
- 未反复运行 `iio_info` 全量枚举（[EXP-HW-003](exp-hw-003.md) 第53行建议避免），本次只做了必要的两次限定查询。
- 未测量供电电压/电流，未更换线缆。

## 9. 下一步（按优先级）

1. **按原厂要求恢复供电**：换成 5V/1A 的 USB 供电加强线，**直插电脑 USB 口，不经集线器**。这是 [EXP-HW-003](exp-hw-003.md) 早已给出的处置方向。
2. **做一次有记录的冷启动**：断电→上电，保存完整 `dmesg` 与 IIO 设备名/属性，与 15:36 的正常读回和本次异常读回三方对照。
3. 复现时**不要靠反复重启碰运气**：连续两次同一现象就应记录为可复现问题，转入供电与时钟/数据接口条件核对。
4. 只有读回值与请求**精确一致**时才继续首次发射；否则一律停在核对阶段。

## 10. 证据位置

| 内容 | 路径 |
|---|---|
| 首次侦察（重启时间、/tmp 清空） | `results/p13-pre-tx-recon-20261016-1705/` |
| 原始 sysfs 首次读数 | `results/p13-pre-tx-recon-20261016-1710/` |
| 项目同款 IIO 读回 + `iio_info` | `results/p13-pre-tx-iio-20261016-1715/` |
| TX 通道完整读数 + 可写性 + `dmesg` | `results/p13-pre-tx-iio-full-20261016-1722/` |
| 正常对照（15:36） | `results/p12-board-source-check-20261016-153621/` |
| 发射方案与仪器限制 | [first-rf-transmit-spectrum-plan.md](../design/first-rf-transmit-spectrum-plan.md) |

每个 `results/` 目录内含 `serial-transcript.txt`（原始串口逐字记录）与 `report.json`（含每条命令与其退出码）。
