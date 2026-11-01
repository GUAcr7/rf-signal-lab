# EXP-HW-009：新板真实 I/Q 采集（格式、统计、中断恢复）

- 日期：2026-10-17 深夜。
- 承接 [EXP-HW-008](exp-hw-008-mode-round-trip.md)（模式往返闭环）。
- 本轮目标：处理审查意见 4 —— "新板目前只证明驱动和设备枚举成功"。
- **结果：真实 I/Q 已采到、解码、统计，中断后设备可恢复。** 但**没有信号源接入**，所以本轮证明的是**采集通路与数据格式**，不是"收到了调制信号"。
- 本轮性质：真实上板。

## 1. 配置读回（写入已知值后核对）

| 属性 | 读回值 | 说明 |
|---|---|---|
| `iio_info -s` | 4 个设备 | `cf-ad9361-dds-core-lpc, ad9361-phy, cf-ad9361-lpc, xadc` |
| `iio:device1/name` | `ad9361-phy` | — |
| `in_voltage_sampling_frequency` | 30720000 | 与设计一致 |
| `in_voltage_rf_bandwidth` | 18000000 | 与设计一致 |
| `in_voltage0_gain_control_mode` | `slow_attack` | — |
| `out_altvoltage0_RX_LO_frequency` | **写入 2450960000 → 读回 2450960000** | **这是真正的"写后读回"验证** |

## 2. 数据格式：4 通道，不是 2 通道

一开始按 2 通道解析会得到错误结果。实测链条：

1. `iio_readdev -b 4096 -s 8192 cf-ad9361-lpc` → 文件 **65,536 字节**
2. `8192 × 2 通道 × 2 字节 = 32,768` ≠ 65,536 → 说明通道数不对
3. `8192 × 4 × 2 = 65,536` ✓ → **4 通道**
4. `iio:device2` = `cf-ad9361-lpc`；`scan_elements/in_voltage0_type` = **`le:S12/16>>0`**，`in_voltage1_type` 相同
5. 捕获后 `*_en` 全为 0 —— `iio_readdev` 自己启停通道，退出后复位

**结论**：布局是 **I1, Q1, I2, Q2** 四通道交错，每通道 2 字节（12 位有符号）。RX1 的 I/Q 是 ch0/ch1。

**这个坑很隐蔽**：`8192` 字节数恰好是 4 的倍数，按 2 通道解析不会报错，只会**静默给出半数样本且通道混叠**。

## 3. 采集与回传

板子没有网络路径，数据只能走串口回传：

```sh
# 板上：采一小段并计算哈希
iio_readdev -b 1024 -s 1024 cf-ad9361-lpc > /tmp/rx2.bin     # 8192 字节
sha256sum /tmp/rx2.bin
base64 /tmp/rx2.bin
```

base64 输出由 `experiments/p15_serial_read.py --evidence` 存进 `transcript.json`；
`experiments/p18_extract_capture.py` 从中取出载荷、**与板上算出的 sha256 比对**、再解码统计。

**为什么要比对哈希**：串口回读可能被截断或被命令行回显污染。不校验的话，一份残缺的载荷看起来和正常数据一样。

## 4. 解码与格式统计

```
payload bytes : 8,192
sha256        : 4b2e3d1202b0873b4eb9488fe8809ccc84bf495b51c210a97a871c61f72674f4  → MATCH
channels      : 4  (I=ch0, Q=ch1)
frames        : 1,024   (1,024 expected)
raw word range: min -650, max 677
mean power    : 21,414.8
rms           : 146.34
peak abs      : 221
crest factor  : 3.57 dB
endpoint frac : 0.0  (full_scale=2048)
```

| 判据 | 解读 |
|---|---|
| 帧数 1,024 与 `-s 1024` 一致 | 通道数与布局**解析正确** |
| 原始字 −650…677，远小于 ±2048 | **未削顶**（与 `endpoint frac = 0.0` 一致） |
| 峰均比 3.57 dB | 复高斯噪声（瑞利幅度）的典型值，符合"只接了噪声"的预期 |
| RMS 146 / 满量程 2048 | 约 7%，对 71 dB 增益下无输入的底噪是合理量级 |

**重要限定**：**没有接入任何信号源**，这段数据是 ADC 底噪。它证明采集通路、四通道布局、格式与回传校验都正确；**不证明**能收到调制信号，也不构成 `--full-scale` 的实测确认（2048 仍是按 12 位推断的假设值）。

## 5. 停止 / 重启采集

**第一次尝试不算数**：`timeout 5 iio_readdev -s 100000` 写出 800,000 字节，正好是完整尺寸 —— 30.72 MS/s 下只需 3 ms 就采完，`timeout` 从未触发。这不是中断测试。

**重做（真实中断）**：

| 步骤 | 结果 |
|---|---|
| `timeout 1 iio_readdev -b 1024 -s 20000000` | 写出 **73,760,768 字节**（完整应为 160,000,000）→ **确认被中途杀死** |
| 紧接着 `iio_readdev -b 1024 -s 1024` | **8,192 字节** ✓ → **设备未卡死，可立即重采** |

另外两次连续正常采集（`rx2` / `rx4` / `rx6`）哈希各不相同，说明每次都是新数据，不是缓存的旧缓冲。

## 6. 本轮新增的代码

| 文件 | 内容 |
|---|---|
| `src/rfsig/iq_io.py` | 新增 `decode_iq_dma_s16()` / `load_iq_dma_s16()`，支持任意通道数与 I/Q 通道选择 |
| `tests/test_iq_dma.py` | **8 项**测试，含"把 4 通道当 2 通道会静默出错"这一条 |
| `experiments/p18_extract_capture.py` | 从 transcript 提取 base64 → 校验哈希 → 解码 → 格式统计 |

## 7. 证据

| 内容 | 路径 |
|---|---|
| 配置读回 | `results/p18-iio-readback-20261017/`、`p18-config-writeback-20261017/` |
| 通道布局与格式 | `results/p18-iio-format-20261017/`、`p18-iio-channels-20261017/` |
| 采集与哈希 | `results/p18-capture-small-20261017/` |
| base64 回传 | `results/p18-capture-transfer-20261017/` |
| **解码与格式统计** | `results/p18-capture-decoded-20261017/characterisation.json` + `segment.bin` |
| 连续采集 | `results/p18-stop-restart-20261017/` |
| **真实中断 + 恢复** | `results/p18-interrupt-test-20261017/` |

## 8. 仍未验证

| 项 | 说明 |
|---|---|
| **收到调制信号** | 需要旧板发射 + 射频线，且必须先做降幅与饱和检查（[rx-input-budget](../design/rx-input-budget-20261017.md)） |
| **`--full-scale` 实测确认** | 2048 是按 12 位推断，未用已知幅度信号标定 |
| 双通道（RX2）数据 | 本轮只解析了 ch0/ch1；ch2/ch3 存在但未单独验证 |
| 更长的连续采集 | 只测到 73.7 MB / 1 s 被中断，未做长时间稳定性 |
