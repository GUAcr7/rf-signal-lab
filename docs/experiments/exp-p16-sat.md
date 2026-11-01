# EXP-P16-SAT：双板连接前的两项离线准备（64 档波形 + 饱和判据工具）

- 日期：2026-10-17 晚。
- 背景：两块板均断电，`EXP-ERRATA-20261017` §9 列的 8 项上板验证全部阻塞。本轮只做**能离线完成、且是上板验证硬前提**的两件事。
- 本轮性质：**纯离线**。未上电、未发射、未连接双板。

## 1. 为什么先做这两件

审查后的上板顺序是：部署脚本 → 采自启证据 → 触摸持久化 → 模式往返 → 旧板五步恢复 → 新板真实 I/Q → **双板连接**。

双板连接这一步有两个前置条件**当时都不具备**：

| 前置 | 缺什么 |
|---|---|
| 降幅流程需要 64 档波形 | 只有 512/256/128，**没有 64** |
| 饱和判据需要能算步进增益的工具 | 判据已写成文字（`rx-input-budget` §5），但**没有程序**，接上线只能靠眼睛 |

所以先补齐这两项，避免上板时临场手搓。

## 2. 64 档波形

`experiments/p13_prepare_power_steps.py` 增加 `--peaks` 参数（默认保持 `512,256,128`，不破坏已归档测量的复现性）。

```powershell
.venv\Scripts\python.exe experiments\p13_prepare_power_steps.py --peaks 512,256,128,64
```

结果（`results/p13-power-steps-20261017T110944Z/`）：

| 文件 | 数字峰值 | 相对 512 | `mean_I2_Q2` |
|---|---:|---:|---:|
| `tone-peak512.iq16le` | 512 | 0.0000 dB | 67,097,408 |
| `tone-peak256.iq16le` | 256 | −6.0167 dB | 16,789,504 |
| `tone-peak128.iq16le` | 128 | −12.0378 dB | 4,196,864 |
| **`tone-peak64.iq16le`** | **64** | **−18.0706 dB** | **1,046,272** |

包 2,101,760 B，sha256 `2ab0db9aa0b2d6f9120d75b986185630a8a8ab85ec7cd43a8b7fc71c9df7b66b`。

**旧的三档包 `p13-power-steps-20261017T052904Z` 保留不动** —— `EXP-P13-POWER` 的实测数字引用的是它。

## 3. 饱和判据工具

### 3.1 代码位置（按项目惯例进 `src/` 并配测试）

| 文件 | 内容 |
|---|---|
| `src/rfsig/saturation.py` | `iq_power_stats()`、`step_gain_db()`、`judge_step()`、`analyse_steps()` |
| `tests/test_saturation.py` | **19 项**测试 |
| `src/rfsig/iq_io.py` | 新增 `load_iq_binary_s16()`（`iio_readdev` 的二进制格式）、`pairs_to_complex()` |
| `experiments/p16_check_saturation.py` | 命令行：读多段采集 → 步进增益 → 判定 + JSON |
| `experiments/p16_make_saturation_fixtures.py` | 生成"已知答案"的线性/压缩 fixture |

### 3.2 判据（已按审查修正的方向）

线性接收链在输入**幅度加倍**时，功率应增 **+6.0206 dB**（= 20·log₁₀2）。**压缩表现为增量变小。**

| 观察 | `judge_step` 返回 |
|---|---|
| ≥ 6.0206 − 0.5 = 5.52 dB | `linear` |
| < 5.52 且 ≥ 1.0 dB | `compressing` |
| < 1.0 dB | `saturated` |

### 3.3 合成数据自测（证明判据真的能分辨）

`experiments/p16_make_saturation_fixtures.py` 生成四档（200/400/800/1600）两组：

- `linear/` —— 纯线性
- `compressed/` —— 经**幅度域**软限幅（`|x|` 上的 tanh）

| fixture | 逐步测得 | 判定 | 退出码 |
|---|---|---|---|
| `linear/` | +6.024 / +6.021 / +6.021 dB | **LINEAR** | 0 |
| `compressed/` | +5.937 / +5.705 / **+4.895** dB | **NON-LINEAR**（第 2 步起） | 4 |

证据：`results/p16-saturation-selftest-linear-20261017/saturation.json`、`results/p16-saturation-selftest-compressed-20261017/saturation.json`。

### 3.4 自测过程中抓到的一个真实缺陷

第一版 `soft_limit()` 写的是 `np.tanh(iq / limit)`。**`np.tanh` 作用在复数上是复双曲正切**，既不限制幅度、也不保持相位，甚至可能放大信号 —— 结果"压缩"fixture 的实测 rms 反而**大于**输入，被判成 LINEAR。

改为在**幅度域**限幅（`|x|` 过 tanh，再按比例缩回）后，压缩才如实出现在第 2 步（+4.895 dB）。

**如果没做"已知答案"的自测，这个错误会一直潜伏到真机上** —— 而真机上没有"标准答案"可比对。

## 4. 测试结果

| 项目 | 结果 |
|---|---|
| `tests/test_saturation.py` | **19 passed** |
| 全量测试 | **721 passed**（上一轮 702 + 19） |

## 5. 上板时怎么用（未执行）

```sh
# 板上：发射端用 64 档，接收端手动增益 0 dB
# 每档采集一段：
iio_readdev -b 4096 -s 65536 cf-ad9361-lpc > /tmp/rx-peak64.bin
# ... 依次 128 / 256 / 512，每档都要采
```

取回电脑后：

```powershell
.venv\Scripts\python.exe experiments\p16_check_saturation.py --full-scale 2048 `
  --segment peak64=/tmp/rx-peak64.bin `
  --segment peak128=/tmp/rx-peak128.bin `
  --segment peak256=/tmp/rx-peak256.bin `
  --segment peak512=/tmp/rx-peak512.bin `
  --output results/p16-saturation-<时间戳>
```

**`--full-scale 2048` 是假设值**（AD9361 RX 为 12 位符号扩展），**必须在新板上先确认实际满量程**再据以解读 `endpoint_fraction`。`--full-scale` 省略时该项为 `null`，不猜。

**退出码**：0 = 线性；4 = 非线性（含起始步号）；3 = 某段功率为零无法计算。

## 6. 本轮明确没做的

- 未上电、未发射、未连接双板
- 未验证 64 档波形在板上的校验（需要 `--check`）
- 未采集任何真实 RX 段，`--full-scale` 未经实测确认
- 未部署模式脚本

**`EXP-ERRATA-20261017` §9 的 8 项待验证状态不变。**

## 7. 下一步

板子上电后的顺序（每步都要 `--evidence` 落盘）：

1. 部署 `board/boot/S99board` 与 `board-mode`，设 `/etc/board-mode`
2. 采自启与触摸持久化证据（`EXP-HW-006` §11）
3. 模式往返 display → rf → display
4. 旧板五步不发射恢复
5. 新板：确认满量程 → 配置读回 → 真实短段 I/Q → 格式统计
6. 双板：64 档起步，用本轮工具逐档判线性，**通过后才逐档提高**
