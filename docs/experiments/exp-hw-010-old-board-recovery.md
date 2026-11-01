# EXP-HW-010：旧板断电恢复五步验证（零发射）

- 日期：2026-10-17 深夜。
- 承接 `EXP-ERRATA-20261017` §3（恢复命令的哈希与执行位缺陷已确认并修正）。
- 本轮目标：按修正后的流程，在真实旧板上**完整跑一遍恢复验证，且不发射**。
- **结果：五步全部通过。** 全程 `--inspect` / `--check`，**没有任何 `--run`**。
- 本轮性质：真实上板（旧板 P201 重新接入，串口 COM9）。

## 1. 背景：为什么这五步值得单独做一次

审查发现旧板的恢复指引有两处会导致失败：

| 缺陷 | 原状 | 修正后 |
|---|---|---|
| **哈希写错** | 命令里传 `664e6173…`（已废弃的 CRLF 包） | `9af83ce9…`（CR-free 包） |
| **缺执行位** | 归档里 `arm-tx-source` 模式是 **0666**，解包后 `./arm/arm-tx-source` → `Permission denied` | 解包后必须 `chmod +x` |

本轮的目的就是**用一次真实操作证明修正后的流程可用**，而不是靠推理。

## 2. 五步实测

### 第 1 步：上传（3.2 MB）

```
UPLOAD_PASS sha256=9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e
```

上传器自己的哈希校验通过。

### 第 2 步：补执行位 + 载荷完整性

```
EXTRACT_OK
-rwxrwxrwx    1 root     root         37588 Oct 17  2026 arm/arm-tx-source
arm/arm-tx-source: OK
arm/arm_tx_source.c: OK
waveforms/bpsk.iq16le: OK
waveforms/qam16.iq16le: OK
waveforms/qpsk.iq16le: OK
waveforms/tone-double-offset.iq16le: OK
waveforms/tone-negative.iq16le: OK
waveforms/tone-positive.iq16le: OK
```

**8/8 OK，退出码 0。** `chmod +x` 之前该文件确实是 0666（归档记录如此），这一步不能省。

### 第 3 步：`--inspect`（只读，不发射）

退出码 0，关键读数：

| 属性 | 值 | 要求 | 判定 |
|---|---|---|---|
| `hw_model` | `PUZHI PZSDR P201` | — | ✓ |
| `hw_serial` | （空） | 空 → 用 boot_session 身份 | ✓ |
| `TX_DMA_sampling_frequency` | 30720000 | 30720000 | ✓ |
| `tx0_hardwaregain` | **−10.000000 dB** | −10 | ✓ |
| `tx_lo` | **2450000000** | 2450000000 | ✓ |
| `tx0_rf_bandwidth` | 18000000 | 18000000 | ✓ |
| `rx0_sampling_frequency` | 30720000 | — | ✓ |
| `rx0_rf_bandwidth` | 18000000 | — | ✓ |
| `rx0_hardwaregain` | 71.000000 dB | — | ✓ |

**六项射频属性全部符合冻结配置**（`EXP-P13-POWER` §3.3 要求的那组）。

### 第 4 步：六支波形逐支校验（不发射）

| 波形 | 结果 | min/max | `mean_I2_Q2` |
|---|---|---|---|
| `tone-positive` | `INPUT_CHECK_PASS` | −8192/8192 | 67,097,408 |
| `tone-negative` | `INPUT_CHECK_PASS` | −8192/8192 | 67,097,408 |
| `tone-double-offset` | `INPUT_CHECK_PASS` | −8192/8192 | 67,105,408 |
| `bpsk` | `INPUT_CHECK_PASS` | −8144/8192 | 26,896,694.91 |
| `qpsk` | `INPUT_CHECK_PASS` | −8192/8192 | 28,594,213.37 |
| `qam16` | `INPUT_CHECK_PASS` | −8192/8144 | 18,668,820.86 |

**6/6 PASS**，`format=LE_s16_IQ low_bits_zero=4` 每支都报。

这些 `mean_I2_Q2` 与 `EXP-P13-POWER` §2 记录的值**逐位一致**（例如 tone 组 67,097,408），说明恢复出来的波形与当初发射的完全相同。

### 第 5 步：`boot_id`

```
ea863ecc-1935-4d1e-92dc-a26ba4877199
```

`--inspect` 报 `tx_guard_identity=boot-session:ea863ecc-1935-4d1e-92dc-a26ba4877199`，**与直接读 `/proc/sys/kernel/random/boot_id` 完全一致**。

这是发射守卫的身份来源：每次断电重启都会变，用旧值发射会被拒绝（程序退出且**不写任何射频参数**）。

## 3. 这次验证证明了什么

| 结论 | 依据 |
|---|---|
| 修正后的恢复流程**可用** | 五步全部通过，退出码均为 0 |
| 归档里的 **0666 缺陷真实存在**，`chmod +x` 必需 | `chmod` 后模式才变 `-rwxrwxrwx` |
| 恢复出来的波形**与当初逐字节相同** | 六支 `mean_I2_Q2` 与历史记录逐位一致 |
| 板卡射频配置**未被改动** | 六项属性符合冻结值；全程未执行 `--run` |
| `boot_id` 守卫身份**可正确获取** | 程序内部身份与 `/proc` 直读一致 |

## 4. 本轮明确没做

- **没有发射**：没有任何 `--run` 命令，`rf_settings_written` 不可能为 true
- 没有连接射频线
- 没有改板上任何配置

## 5. 证据

| 内容 | 路径 |
|---|---|
| 上传 | `results/p19-oldboard-upload-20261017/` |
| 解包 + 执行位 + 载荷校验 | `results/p19-oldboard-recovery-20261017/` |
| `--inspect` + `boot_id` | `results/p19-oldboard-inspect-20261017/` |
| 六支波形校验 | `results/p19-oldboard-waveform-checks-20261017/` |

## 6. 下一步的条件

双板链路仍需要：

1. **新板重新接上 USB**（当前只有旧板在 COM9/COM5，新板未接入）
2. **旧板写入 64 档波形**（本轮已开始上传 4 档包，见 `p19-oldboard-powersteps-upload-*`）
3. **射频线**（TX1 → 新板 RX1A）
4. 按 `rx-input-budget` 从 64 档起步、RX 手动 0 dB、逐档判线性
