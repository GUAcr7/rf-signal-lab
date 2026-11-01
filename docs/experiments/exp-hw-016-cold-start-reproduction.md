# EXP-HW-016：冷启动复现验证 + AD9361 探测失败的定位与修复

> 2026-10-18 审查更新：以下 −37.04 ~ −37.18 dB 为原流程的历史读数。独立已知符号复算为 BPSK −37.19、QPSK −37.97、16QAM −37.64 dB，每份 502 个有效符号，后半段 251 个检查符号零错；原字节、回传与板端 SHA 一致，见 `results/p26-independent-audit-20261018T121819Z/report.json`。不能把不同测量口径混作同一比较。S99board 审查版哈希 `2a5533091321e1fe6329f8ac95ad63a0fc07f13407d865a37d1cda97484afb3e`，部署证据 `results/p26-boot-deployment-20261018T121928Z/report.json`；按名检查三设备、755 权限和只读就绪检查通过，真实重试分支未验证。完整报告见 [HW-018](exp-hw-018-review-and-streaming.md)。

- 日期：2026-10-18 晚（两块板重新上电后）。
- 目标：按 [RESUME-20261018](../handoff/resume-20261018.md) 的流程，验证整套链路在**断电重启后**能否复现。
- **结果：三调制全部复现，EVM −37.04 ~ −37.18 dB，彼此相差 0.14 dB。**
- 顺带定位并修复了一个新问题：**AD9361 开机探测失败（PRODUCT_ID 0xFF），重试即成功。**

## 1. 冷启动后的问题：AD9361 没有应答

开机时 `board-init` 日志：

```
board-init: overlay applied: /lib/firmware/pl.dtbo
board-init: FAILED: rf mode selected but no second IIO device
ad9361 spi32765.0: ad9361_probe : enter (ad9361)
ad9361 spi32765.0: ad9361_probe : Unsupported PRODUCT_ID 0xFF
```

`PRODUCT_ID 0xFF` 是该次 SPI 产品 ID 读回全 1。以下检查证明文件匹配且 FPGA 管理器报告 operating；不能单独证明硬件链不存在间歇故障：

| 检查 | 结果 |
|---|---|
| `ad9361.bin` vs `system_wrapper.bin` | 相同，`65b44449…`，17,416,348 B |
| `fpga0/state` | `operating` |

### 1.1 重新绑定 overlay 后成功

```sh
rmdir /sys/kernel/config/device-tree/overlays/pl
mkdir /sys/kernel/config/device-tree/overlays/pl
cat pl.dtbo > /sys/kernel/config/device-tree/overlays/pl/dtbo
```

```
ad9361 spi32764.0: ad936x Rev 2 successfully initialized
cf_axi_adc 79020000.cf-ad9361-lpc: probed ADC AD9361 as MASTER
cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: probed DDS AD9361
iio:device0  iio:device1  iio:device2  iio:device3
```

**同一次开机内，第一次探测失败、第二次成功**：证明该次故障可重绑恢复。具体时序/复位或间歇硬件原因待验证，不能排除硬件故障。

### 1.2 修复：`S99board` 现在会重试

原脚本检测到没有第二个 IIO 设备就 `fail` 中止，把**可恢复**的情况留成了"无射频"。

6193 B 历史版等待 `iio:device1` 并最多重绑三次。HW-018 审查版等待实际名字同时满足 PHY、ADC、DDS；移除失败立即停止，第 3 次仍不齐才退出，避免目录存在或残缺驱动被误当成功。

| 项 | 值 |
|---|---|
| 文件 | `board/boot/S99board` |
| 大小 | 5,040 → **6,193 B** |
| 检查点 | 仍为 **17 处** `\|\| fail` |
| 语法 | `dash -n` 通过 |
| 日志 | 会打印 `attempt N` 与 `no AD9361 after attempt N; rebinding the overlay` |

6193 B 历史版后来已部署，有三次 attempt 1 重启记录；这不等于重试分支实测。审查版又改为按名字同时确认 PHY/ADC/DDS，并检查移除返回码，已部署核验。详见文件顶部更新。

## 2. 三调制复现结果

配置：TX 端口 A、`tx0_hardwaregain = -10 dB`、`tx_lo = 2450 MHz`、数字峰值 256；RX `manual` + `0 dB`、RX_LO 2450 MHz；Fs 30.72 MS/s、RF 带宽 18 MHz。
采集：`iio_readdev -b 65536 -s 65536`（**单缓冲**），每段 524,288 字节，回传后与板上 sha256 逐一校验通过。

| 调制 | 载波 (Hz) | 定时相位 | EVM (dB) | 正交抑制 (dB) | 幅度 CV |
|---|---:|---:|---:|---:|---:|
| BPSK | 993,213.6 | 49 | **−37.18** | **+45.27** | 0.0127 |
| QPSK | 993,455.6 | 7 | **−37.07** | −0.02 | **0.0083** |
| 16QAM | 993,654.7 | 36 | **−37.04** | +0.05 | **0.3447** |

原始数据 sha256：

| 调制 | 采集文件 sha256 |
|---|---|
| BPSK | `0d06610cd1a50d5d11c846edbb649e4465d21ae85bc54102a47ffe682c853f3b` |
| QPSK | `d24026928e338b3618d9170e055a8d8394ddda4c50c4c50fdf0ac81cc07ae1a2` |
| 16QAM | `d8e4f729b262f8dae52f644420e2260da00f86f9b121f6cc09f0cc54fbbb73b6` |

### 2.1 与昨天的对比

| 调制 | 昨天 (big1/big2) | 今天 | 差 |
|---|---|---|---:|
| BPSK EVM | −37.58 / −37.72 | −37.18 | ≤0.54 dB |
| QPSK EVM | −37.54 / −37.90 | −37.07 | ≤0.83 dB |
| 16QAM EVM | −23.80 / −34.86（我的盲估计有缺陷） | **−37.04** | 见下 |

**16QAM 的提升来自今天的处理顺序**：先 PLL 精化载波，再 `align_rotation()`。昨天没做这两步时只有 −23.8 dB。今天 −37.04 dB 与 `EXP-HW-014` 的已知符号 EVM（−37.23 / −37.30）一致。

### 2.2 载波偏差

今天三次采集的载波是 **993,213 ~ 993,655 Hz**，昨天是 994,448 ~ 994,639 Hz。

- 昨天内部三次相差约 200 Hz
- 今天内部三次相差约 440 Hz
- **两天之间相差约 1.2 kHz**

观测是跨会话载波变化约 1.2 kHz，不能仅凭此归因哪块板的晶振。相对于 2450 MHz 是 **0.49 ppm**；不能除以采样率而称为 RF 或采样时钟误差。**每次上电都必须重新估计，不能沿用上次的载波值。**

## 3. 可分性（今日数据）

| 判别 | 读数 | 间隙 |
|---|---|---|
| BPSK 正交抑制 vs 其余 | **+45.27 dB** vs −0.02 / +0.05 | **45.2 dB** |
| QPSK 幅度 CV vs 16QAM | **0.0083** vs **0.3447** | **41.5 倍** |

与昨晚用 `p22` 数据算出的（44.5 dB / 39.8 倍）一致到 1 dB / 4% 以内。

## 4. 今天验证了什么

| 结论 | 依据 |
|---|---|
| 整套链路**冷启动后可复现** | 三调制 EVM 全在 −37.0 ~ −37.2 dB，两次独立上电一致 |
| 单缓冲快照质量通过 | 原始字节与已知源强匹配；不能证明长期无丢样 |
| 旧板恢复流程**可重复** | 上传、8/8 载荷、`--inspect`、6/6 `--check`、新 boot_id 全通过 |
| AD9361 探测失败**可软件恢复** | 重新应用 overlay 即成功，已加入启动脚本重试 |
| 载波必须**每次重新估计** | 两天差 1.2 kHz |

## 5. 未验证 / 仍待做

| 项 | 状态 |
|---|---|
| 新的 `S99board` 重试逻辑 | 已部署；真实 attempt 2/3 分支待验证，模拟测试通过 |
| 长时间无丢样采集 | 仍只接受单缓冲 2.133 ms 快照 |
| 独立数据集 + SNR 标注 + 数据划分 | 未做 |
| 压缩发生在 TX 还是 RX | 需频谱仪旁路 |
| `--full-scale 2048` 实测确认 | 未做 |
| 屏幕自绘 UI / 显示与射频共存 | 未做 |

## 6. 证据

| 内容 | 路径 |
|---|---|
| 认板与状态 | `results/p24-newboard-state-20261018/`、`p24-newboard-iio-diag-20261018/` |
| 位流核对 | `results/p24-firmware-check-20261018/` |
| **overlay 重绑成功** | **`results/p24-overlay-rebind3-20261018/`** |
| RX 配置 | `results/p24-rx-config-20261018/` |
| 旧板上传与恢复 | `results/p24-oldboard-upload-20261018/`、`p24-oldboard-recovery-20261018/`、`p24-oldboard-inspect-20261018/`、`p24-oldboard-waveforms-20261018/` |
| 调制波形上传与校验 | `results/p24-mod-upload-20261018/`、`p24-mod-extract-20261018/` |
| 三调制发射与采集 | `results/p24-tx-{bpsk,qpsk,qam16}-20261018/`、`p24-rx-{bpsk,qpsk,qam16}-20261018/` |
| **解码后原始数据** | `results/p24-rx-{bpsk,qpsk,qam16}-decoded/segment.bin` |

---

# 勘误 E1：40 ppm 是错的，正确的是 0.49 ppm

> 独立审查（[EXP-HW-018](exp-hw-018-review-and-streaming.md)）指出本文件把 1.2 kHz 的载波变化写成"约 40 ppm"，混淆了 RF 本振与采样时钟。核对属实。

| 参照 | 计算 | 结果 |
|---|---|---:|
| **2450 MHz 本振**（正确参照） | 1200 / 2450e6 | **0.49 ppm** |
| 30.72 MHz 采样时钟 | 1200 / 30.72e6 | 39.06 ppm |

**我把采样时钟当成了分母。** 两者的物理含义完全不同：

- 相对本振的偏差是 **CFO**（载波频偏）
- 相对采样时钟的偏差是 **SCO**（采样钟偏）
- 由一次 CFO 观测**不能**判定是哪块板的 LO 不准，也**不能**换算成 SCO

**结论修订**：两次上电之间载波变化约 1.2 kHz，相当于 **0.49 ppm @ 2450 MHz**。
"每次上电必须重新估计载波"这条操作要求不变，但理由要改成"绝对偏差虽小，在 2450 MHz 上仍是千赫兹级，足以在长块内累积成相位斜坡"。
