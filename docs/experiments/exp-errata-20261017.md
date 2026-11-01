# 独立审查问题处置记录（2026-10-17）

- 审查来源：独立审查与规划助手。
- 处置人：主执行工程师。
- 处置原则：**先修恢复与证据问题，再做新功能**；**未实测的一律标"待验证"**；**为修记录不重复发射**；**不提前宣称新板采集与显示闭环**。
- 本轮板卡状态：**两块板均已断电**（COM9 无响应）。因此凡需上板验证的项目**全部未执行**，逐条列在 §9。

## 0. 总览

| # | 审查意见 | 处置 | 状态 |
|---|---|---|---|
| 1 | 模式切换：`S99board.off` 仍匹配 `S*`，不能停用 | 重写为模式文件驱动、位流与 overlay 成对、风扇独立 | 代码已改，**未部署/未验证** |
| 2 | 撤回"无需衰减已验证" | 撤回，新增电平核算文档，区分损坏口径与可用性口径 | 文档已改，**连接未做** |
| 3 | 旧板恢复命令的哈希与执行权限 | 两处错误已确认并修正，新增五步不发射验证清单 | 离线复核完成，**板端未验证** |
| 4 | 新板只证明枚举成功 | 已列出补证清单与判据 | **全部待验证**（板断电） |
| 5 | 复数双边 PSD 被错误翻倍 | 改用 `src/` 实现，加 13 项守恒测试，重算并归档 | ✅ **已完成并验证** |
| 6 | 0.01 dB / ±5 kHz 过度声明 | 改为证据支持的观测结论 | ✅ **已完成** |
| 7 | 统一文档、加勘误、修 `rf_operations`、补测试日志与证据 | 逐项见 §7 | 部分完成，**证据类待补** |
| 8 | 脚本与实测数据正式归档 | 新建 `board/`，含 sha256 与未验证清单 | ✅ **已完成** |

---

## 1. 模式切换（意见 1）

### 1.1 审查意见成立

sysvinit 按 `/etc/rcS.d/S*` 通配匹配。把文件改名成 `S99board.off` **仍然匹配 `S*`**，只要保持可执行就可能照旧运行。"改扩展名即停用"是错的。

**可靠停用方式（唯一无条件成立）**：把文件**移出** `/etc/rcS.d/`：

```sh
mkdir -p /etc/rcS.d.disabled
mv /etc/rcS.d/S99board /etc/rcS.d.disabled/
```

`chmod -x` 在 Debian 风格 `rc` 中有效（它检查 `-x`），但**本板 `rc` 是否检查可执行位未实测**，不得依赖。

### 1.2 重新设计：模式文件驱动

旧脚本写死显示路径，切射频要手工改文件，位流与 overlay 容易配错。新脚本从 `/etc/board-mode` 读模式，**位流与 overlay 由同一个 `$MODE` 派生**，从代码上消除配错可能：

| 模式 | 位流 | overlay | 谁加载位流 |
|---|---|---|---|
| `display` | `display.bin` | `d480p.dtbo` | overlay 内 `firmware-name=system_wrapper.bin` 自动加载 |
| `rf` | `ad9361.bin` | `pl.dtbo` | **脚本显式加载**（`pl.dtbo` 无 `firmware-name`） |

缺文件时脚本**直接退出、不半配置 fabric**。暂存前先 `cmp` 比较，避免每次开机把 17 MB 写 SD。

**风扇放在 `case` 之外**：它是 PS MIO8（gpio 914），与位流无关，两种模式都必须开。

### 1.3 文件与状态

| 文件 | 状态 |
|---|---|
| `board/boot/S99board`（3,155 B，`7429fbc4a516`） | **新，未部署** |
| `board/boot/board-mode`（1,238 B，`8ab1978e375a`） | **新，未部署** |
| `board/boot/S99board.deployed-20261017`（1,596 B，`c9a5b2649d6f`） | 板上当前运行版本（固定显示） |

部署步骤与"显示→射频→显示往返"验收见 `board/README.md` §3、§4。**往返未实测。**

---

## 2. 衰减器结论（意见 2）

### 2.1 审查意见成立，且是我违反了自己项目的纪律

`docs/design/two-board-rf-link.md` 第 53 行早就写明：

> 确认旧板 TX SMA …峰值输出上限…确认新板 RX **推荐输入范围**…**不要将 2.5 dBm 芯片绝对最大当推荐目标。**

我在 `EXP-TX-002.md` §5 做的正是被这条禁止的事：拿 **+2.5 dBm 绝对最大额定值**减实测 TX 峰值，得出"余量 27.07 dB，不需要衰减器"。**后面的结论违反了前面的纪律，且没有引用它。**

### 2.2 两个量必须分开

| 量 | 含义 | 数值 | 能否当余量基准 |
|---|---|---|---|
| 绝对最大额定值 | 超过可能**永久损坏** | AD9361 RF 输入 **+2.5 dBm peak** | ❌ 只回答"会不会烧坏" |
| 推荐/线性工作范围 | 不饱和、可用 | **本项目未确证**，取决于增益 | ✅ 才是连接判据 |

当前板上 RX：`gain_control_mode=slow_attack`（AGC）、`hardwaregain=71 dB`。**在这个增益下饱和电平远低于损坏阈值**，−24.5 dBm 直连即使不损坏也极可能削顶，测出的 IQ 是失真的。

**我没有做过饱和测试，所以不给饱和门限数字。**

### 2.3 处置

| 项 | 内容 |
|---|---|
| 新文档 | `docs/design/rx-input-budget-20261017.md` |
| 损坏余量 | 27.00 dB（−24.50 − (+2.5)），**线缆损耗按 0 dB 保守计**，且仅在 §2.3.3 冻结配置下成立 |
| 可用性 | **未确证**（推荐输入范围未取得、饱和门限未测） |
| 连接前必做 | RX 增益设 `manual`/0 dB；TX 数字峰值 512 → **64**（−18.06 dB）；逐档做饱和检查 |
| 状态 JSON | 删除布尔 `attenuator_required_for_second_board`，改为结构化 `two_board_link`（`status: calculated_not_connected`） |

**撤回的是"因此不需要衰减器"这个推论**；−24.50 / −24.57 dBm 两个实测读数和 27 dB 算术本身仍有效。

**⚠️ 64 档波形尚未生成**，现有的是 512/256/128。

---

## 3. 旧板恢复命令（意见 3）

### 3.1 两个错误均已确认

| 错误 | 原文 | 事实 |
|---|---|---|
| **哈希用错** | `-ExpectedSha256 "664e61736d88bf…"` | 那是**已废弃 CRLF 包**的哈希。好包是 `9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e` |
| **缺执行位** | 解包后直接 `./arm/arm-tx-source` | 归档里 `stage/arm/arm-tx-source` 模式是 **`-rw-rw-rw-`（0666）**，解包到 ext4 后无执行位 |

### 3.2 离线复核（不需要板子）

`experiments/p16_verify_recovery_bundle.sh`（在 WSL 跑）结果：

- 包哈希 = `9af83ce9…` ✓ 与文档原表一致
- 包内 **8 项 `sha256sum -c` 全部 OK**，退出码 0 → **包本身是好的，错的只是文档命令**
- member 模式确为 `-rw-rw-rw-`（0666）

**一个陷阱**：在 WSL 的 `/mnt/c` 上解包会显示 `-rwxrwxrwx`，那是 Windows 挂载强制 0777 的**假象**，不能用来判断板端行为。判断依据只能是归档记录的模式。

### 3.3 已修正

`START-HERE.md` 恢复命令已改为正确的 `9af83ce9…` 并补 `chmod +x`；另新增**「不发射的完整恢复验证」五步清单**：

1. `chmod +x` 并确认 `-rwxr-xr-x`
2. `sha256sum -c SHA256SUMS` → 8/8 OK
3. `--inspect` → 退出码 0
4. 六支波形逐支 `--check` → 6/6 `INPUT_CHECK_PASS`
5. `cat /proc/sys/kernel/random/boot_id` → 取当前身份

**任一条不过就不发射。本轮板断电，五步未执行，仍待验证。**

---

## 4. 新板只证明枚举成功（意见 4）

### 4.1 审查意见成立

本轮对新板 AD9361 的验证**只到驱动绑定 + 设备枚举**：`AD936x Rev 2 successfully initialized`、`iio_info -s` 列出四个设备。**没有**配置读回成功性的证明、**没有**真实 IQ、**没有**格式统计、**没有**停止/重启采集的证据。

### 4.2 补证清单（全部待验证，需板子切到 rf 模式）

| 项 | 具体做法 | 成功判据 |
|---|---|---|
| 配置读回 | 设 LO/采样率/带宽/增益后**逐项读回**并与写入值比对 | 读回值 == 写入值，记录到 json |
| 真实短段 I/Q | `iio_readdev -b 4096 -s 65536 cf-ad9361-lpc > /tmp/seg.bin` | 文件大小 == 样本数×2 通道×2 字节 |
| 格式统计 | 解析为 s16 IQ：min/max/mean(I²+Q²)/端点堆积比例 | 有数值；若端点堆积比例异常高即为削顶 |
| 停止采集 | `Ctrl-C` 结束 `iio_readdev`，确认进程退出、设备可再次打开 | 退出码正常，二次打开不报 EBUSY |
| 重启后再采一段 | `reboot` 后再采一段并比对 | 两段格式统计同量级 |

**在这些完成前，不得声称"新板采集闭环"。**

---

## 5. 复数双边 PSD 翻倍（意见 5）—— ✅ 已完成

### 5.1 缺陷

`experiments/p13_measure_obw.py` 内联的 Welch 实现有一行：

```python
acc[1:-1] *= 2.0                      # one-sided   ← 错
```

输入是复数 IQ，频谱非共轭对称，**不能套用实信号单边约定**。该行把除 DC 与末 bin 外全部翻倍，导致：

- 由 PSD 积分得到的总功率 **≈2 倍**
- 未翻倍的两个 bin（0 Hz、−7.5 kHz）**恰在 ±1 MHz 分析带内**，带内出现局部半权重畸变

### 5.2 修正

- 新增 `src/rfsig/spectrum.welch_power_spectrum()`：复数双边、功率归一化、**不翻倍**
- `tests/test_spectrum.py` 新增 **13 项**测试，含守恒与双边性
- `p13_measure_obw.py` 改为调用共享实现，并在 `measure()` 内**断言守恒比落在 [0.99, 1.01]**

### 5.3 针对性功率守恒测试

| 测试 | 断言 |
|---|---|
| `test_welch_conserves_power_for_complex_noise`（2 参数） | `sum(psd)·Δf == window_weighted_mean_power`（rel 1e-10），**翻倍会让它变成 2** |
| `test_welch_keeps_a_complex_tone_on_one_side_only`（2 参数） | 正/负单音只在各自一侧出现；功率回到 0.5625 而非 1.125 |
| `test_welch_with_one_segment_equals_the_plain_periodogram` | 单段 == 普通周期图 |
| `test_welch_reports_covered_power_not_the_whole_input` | 有余数时只报覆盖区间 |
| `test_welch_rejects_invalid_options`（7 参数） | 非法参数抛 ValueError |

**测试过程中还抓到我自己一个定义错误**：50% 重叠时"各段平均的平均"≠"覆盖区间的平均"（重叠样本被算两次）。已改为在覆盖区间上直接求平均，`window_weighted_mean_power` 保留为守恒量。

### 5.4 重新归档与影响量化

新证据：`results/p13-obw-20261017T103914Z/obw.json`，每个波形记录 `psd_power_conservation_ratio`（实测 **1.000000000**）等字段。

| 波形 | 修正前 OBW | 修正后 OBW | 差 |
|---|---:|---:|---:|
| bpsk | 282,710 Hz | 282,709 Hz | **−1 Hz** |
| qpsk | 282,380 Hz | 282,380 Hz | −1 Hz |
| qam16 | 280,300 Hz | 280,299 Hz | −1 Hz |
| 三个单音 | 22,050 Hz | 22,050 Hz | 0 |

**错误是真的，但对已归档 OBW 数值的影响只有 1 Hz（0.0004%）** —— 因为 OBW 是带内比值，带内只有 2 个噪声 bin 未翻倍。**原 OBW 结论不受影响，但方法必须改**，因为它同时给出了 3 dB 错误的总功率。

旧证据 `results/p13-obw-20261017T044735Z/obw.json` **保留不动**。

---

## 6. 过度声明（意见 6）—— ✅ 已完成

| 原表述 | 改为 | 理由 |
|---|---|---|
| "误差 ≤ 0.01 dB"／"线性度 ≤0.01 dB" | "观测偏差 0.009 dB，落在分析仪 **0.01 dB 读数分辨率**以内；该方法**无法把真实线性误差与 0 区分**" | 0.01 dB 是分辨率，不是测得的误差上限 |
| "射频端一致到 **±5 kHz（±2 ppm）**" | "三次读数 −1.83/−4.77/−0.26 kHz，**观测离散度 4.5 kHz**；**不能当作精度上限**" | 极差是观测离散，不是标定精度；分析仪频标未标定 |
| "中心频率 ✅" / "相对功率 ✅" | 改 ⚠️ 并写明限定 | 一致性与精度是两件事 |

勘误块：`EXP-P13-POWER.md` §10、`EXP-P13-OBW.md` §10.2。

---

## 7. 文档统一 / `rf_operations` / 测试日志（意见 7）

### 7.1 `rf_operations` 标志确实是错的（严重）

`experiments/p06_arm_serial_run.ps1` 第 19 行把 `rf_operations` 写死为 `$false`，且从未更新。结果：**25 次实际发射了样本的运行，归档报告里都写 `rf_operations=false`** —— 审计者据此会得出"从未发射"的结论。

**验证方式**：`experiments/p16_recompute_rf_flags.py` 从 `serial-transcript.txt` 重算（`CYCLIC_PUSH_SUBMITTED` 才是样本真的进了 TX DMA 缓冲的证据）。

| 结果 | 数量 |
|---|---:|
| 扫描证据目录 | 79 |
| **归档标志存在但错** | **25** |
| 实际 push 过样本 | 25 |
| 写过射频参数（`rf_settings_written=true`） | **0**（符合设计：程序从不写射频参数） |

**索引**：`results/rf-flags-recomputed-20261017T104507Z.json`。**原始 `report.json` 一律未改**（项目纪律：追加而非改写历史）。

**脚本已修**：`p06` 现在从 transcript 推断 `rf_operations` / `rf_transmitted` / `rf_settings_written_by_host` 并记 `basis`。

**我自己的工具也犯了同类错**：第一版重算脚本用 `json.loads` 读 PowerShell 写的 JSON，因 **BOM** 抛异常，而 `except` **静默吞掉**，得出"0 个标志错误"的假结论。已改为 `utf-8-sig` 并把解析失败**显式计数**。**静默吞异常又一次制造了错误结论。**

### 7.2 测试日志已归档

| 项目 | 结果 | 证据 |
|---|---|---|
| Python 测试 | **702 passed**（本轮 689 → 702，新增 13 项 Welch 测试） | `results/pytest-log-20261017-review-fixes/pytest.log` |
| 原生 TX mock（WSL + gcc） | **43/43 passed**，`status=passed_host_mock_only` | `results/p12-native-mock-20261017T110500/report.json` |

### 7.3 文档统一

| 文件 | 处理 |
|---|---|
| `START-HERE.md` | 顶部改为"审查清单优先"；测试基线 667→702；衰减器行改写；恢复命令哈希与 `chmod` 修正；新增五步不发射验证；双板行改为"未确定" |
| `TX-SOURCE-STATUS.json` | 删除布尔衰减器字段，改结构化 `two_board_link`；`python_tests` 667→702；新增 `rf_flags`、`errata` 指针；`native_mock_evidence` 更新 |
| `README.md` | 仍写 667，**已在 §10 标注为过期**（不在本轮改动范围） |
| `EXP-REVIEW-HANDOFF-20261017.md` | 保留原文，追加本轮处置指针 |

### 7.4 新板原始证据（部分仍缺）

| 项目 | 状态 |
|---|---|
| 显示（`state=operating`、`/dev/fb0`、`800×480×32 stride 3200`、`100x30` 控制台） | ✅ 串口 transcript 已存 `results/p15-newboard-*/` |
| 开机自启（重启后 `state=operating`、`/dev/fb0`、`gpio914=direction out`） | ✅ 同上 |
| 触摸原始事件 | ✅ 已归档 `board/touch-captures/`（3 份，含 1 份空采集） |
| **触摸重启后是否自动生效** | ❌ **仍缺**（本轮唯一遗留的触摸缺口） |
| **模式切换往返** | ❌ 缺 |

---

## 8. 正式归档（意见 8）—— ✅ 已完成

新建 `board/`，**不依赖 `tmp/`**：

| 文件 | 字节 | sha256 前 12 |
|---|---:|---|
| `board/boot/S99board` | 3,155 | `7429fbc4a516` |
| `board/boot/board-mode` | 1,238 | `8ab1978e375a` |
| `board/boot/S99board.deployed-20261017` | 1,596 | `c9a5b2649d6f` |
| `board/boot/99touch` | 1,423 | `3ab650136f39` |
| `board/boot/S99fan.superseded` | 795 | `00ccaacb2de9` |
| `board/touch-captures/tap-dump.txt` | 8,135 | `4a45f222db48` |
| `board/touch-captures/drag-dump.txt` | 11,837 | `74cf63d7b0a5` |
| `board/touch-captures/diag-dump.txt` | 137 | `ad9151ecc6c5` |

`board/README.md` 记录了每个文件的作用、部署步骤、正确的停用方式、以及**未验证清单**。

---

## 9. 未实测项汇总（不得当成已完成）

| 项 | 阻塞原因 |
|---|---|
| 新模式脚本部署 | 板断电 |
| **显示 → 射频 → 显示 完整往返** | 板断电 |
| `99touch` 重启后是否自动生效 | 未重启验证 |
| 触摸四点标定量化 | 未做 |
| 旧板五步不发射恢复验证 | 板断电 |
| 新板配置读回 / 真实 IQ / 格式统计 / 停止重启采集 | 板断电 + 需切 rf 模式 |
| 双板连接（含 64 档波形生成与饱和检查） | 需先完成电平核算与降幅波形 |
| 屏幕自绘 UI | 未开始 |

**本轮为修正记录没有做任何发射，也没有连接双板。**

## 10. 本轮新增/修改的文件

| 类别 | 文件 |
|---|---|
| 代码 | `src/rfsig/spectrum.py`（+`welch_power_spectrum`）、`experiments/p13_measure_obw.py`（改用共享实现 + 守恒断言） |
| 测试 | `tests/test_spectrum.py`（+13 项） |
| 工具 | `experiments/p16_recompute_rf_flags.py`、`p16_verify_recovery_bundle.sh` |
| 板端归档 | `board/`（5 个脚本/备份 + 3 份触摸数据 + README） |
| 文档 | 本文件、`docs/design/rx-input-budget-20261017.md`、`docs/design/NEW-BOARD-RESUME.md`（衰减器行）、`EXP-P13-OBW.md` §10、`EXP-P13-POWER.md` §10、`EXP-TX-002.md` §9 勘误、`START-HERE.md` |
| 状态 | `TX-SOURCE-STATUS.json` |
| 证据 | `results/p13-obw-20261017T103914Z/`、`results/pytest-log-20261017-review-fixes/`、`results/p12-native-mock-20261017T110500/`、`results/rf-flags-recomputed-20261017T104507Z.json`、`results/p13-bundle-offline-verify-20261017/` |

---

# 追加：第二轮复查的 6 项处置（2026-10-17 晚）

第一轮已确认有效的：PSD 修复、702 项测试日志、43 项模拟测试、25 次发送勘误索引、`board/` 归档。

以下为第二轮新增处置。

## 11.1 启动脚本：风扇优先 + 全程返回码检查

**审查意见成立**：原脚本先解析模式、最后才开风扇，且 `cp` / `mount` / overlay 应用都**没有检查返回值**。若 fabric 配置失败，风扇也不会启动，且脚本仍继续往下走。

**已重写** `board/boot/S99board`（5,040 B，`2bfc9e5f8cb7`，111 行）：

| 顺序 | 步骤 | 失败处理 |
|---:|---|---|
| 49 | **风扇最优先**（PS MIO8，与位流无关） | `fail` |
| 53 | 读模式 | — |
| 80 | `cp` 位流后 **`cmp` 复核** | `fail` |
| 85 | `mount` configfs 后**核对 `/proc/mounts`** | `fail` |
| 95 | rf 模式显式加载后**核对 `state=operating`** | `fail` |
| 104 | overlay 应用（查返回码 + 槽位存在） | `fail` |
| 112 | 最终 `state=operating` 验收 | `fail` |
| 116+ | 分模式终检（display→`/dev/fb0`；rf→`iio:device1`） | `fail` |

**17 处 `|| fail`**。三个脚本均通过 `dash -n`。**未部署，未验证。**

## 11.2 NEW-BOARD-RESUME 的三处陈旧内容已真正改写

第一轮只改了别的文档，`NEW-BOARD-RESUME.md` 本身没动 —— 审查指出后已改：

| 位置 | 原文 | 现状 |
|---|---|---|
| §3 停用法 | `mv ... S99board.off` | 加 ⚠️ 作废块，改为"移出 `/etc/rcS.d/` 是唯一可靠方式"；改为 `board-mode` + reboot |
| §4 衰减器 | "不需要衰减器…余量 27 dB" | 加 ⚠️ 撤回块，改为"现在不能直接接"，并给出降幅步骤 |
| §4 接线 | 直接接 TX1→RX1A | 改为"先设手动/0 dB 增益 + TX 降到 64 档 + 逐档饱和检查" |

## 11.3 显示与自启证据：改为"待补"

**审查意见成立，且是本轮最该认的一条。**

我当时用 `experiments/p15_serial_read.py` 在串口上直接读，而**那个工具不写 transcript**。所以：

- `xilinx-drm ... fb0: frame buffer device`
- `Console: switching to colour frame buffer device 100x30`
- 重启后的 `state=operating` / `/dev/fb0` / `gpio914=direction out`

**全部只存在于对话记录，没有落地证据文件。**

逐目录核查 `results/p15-newboard-*/`：仅 `p15-newboard-pl-state-20261017/transcript.json` 出现过 `[drm] Initialized`，那是**加载显示位流之前**的早期探测，不含 `fb0`。

**已改**：
- `EXP-HW-006` 顶部加 ⚠️ 证据缺口声明；§1.4 与 §3.3 的状态改为**"已观察、证据待补"**
- 新增 `EXP-HW-006` §11：下次上电一次跑完的采集脚本（三条命令都带 `--evidence`）与三项判据
- `START-HERE.md` 一句话总结改为"已跑通并亲眼观察到，但原始 transcript 未归档"
- `TX-SOURCE-STATUS.json`：`display.working = "observed_not_archived"`、`boot_autostart.verified_after_reboot = "observed_not_archived"`

**这次是"看到了但没归档"，按项目证据约定等价于未验证。** 教训：任何要写进记录的结论，采集那一刻就必须带 `--evidence`。

## 11.4 START-HERE 与状态 JSON 的矛盾已清

| 矛盾 | 修法 |
|---|---|
| 状态 `status_note` 写"9 次发送" | 改为 **25 次**，并加 `status_note_supersedes` 记录旧值 |
| `frequency_verified_scope` 仍写 `±5 kHz (±2 ppm)` 上限 | 改为"三次读数 −1.829/−4.767/−0.262 kHz，均值 −2.29 kHz，极差 4.5 kHz；**是观测离散度不是精度上限**" |
| `measured_tx_frequency_error_ppm = -0.93` | 改名为 `..._ppm_observed` 并加 `_scope` 说明 |
| `status` 以 `second_board_pending` 结尾 | 改为 `new_board_connected_display_and_iio_enumerated_but_evidence_pending` |
| `physical_dependencies` 含"新板…衰减器已不再阻塞" | 已移除，改为"双板连接前必须先降幅与饱和检查" |
| START-HERE「新接收板…从未接入」 | 改为"已接入，但原始证据待补" |
| `two_board_plan` 指向旧文档 | 改为 `rx-input-budget-20261017.md`，旧文档标记为 superseded |

处置脚本：`experiments/p16_unify_status.py`（幂等，解析失败即拒绝写入）。

残留的 `"9 timed transmissions"` 字样只出现在 `status_note_supersedes` 里，是**故意保留的旧值说明**，不是遗漏。

## 11.5 饱和判据方向错误已修正

`docs/design/rx-input-budget-20261017.md` §5 原表最后一行写：

> "与降幅后的对照：幅度减半后功率下降明显**大于** 6.02 dB（因为不再削顶）"

**方向反了**。若较高档已压缩，其测得功率低于真值，于是"降一档"测到的下降量**小于** 6.02 dB。按原文会把线性区误判为压缩。

已改为**主判据 = 逐档加倍的步进增益**：

| 观察到 | 判定 |
|---|---|
| 每次加倍 **+6.02 ± 0.5 dB** | 线性区，可继续 |
| 某次加倍 **< 5.5 dB** | 开始压缩，停在该档以下 |
| 加倍后 < 1 dB | 严重饱和 |

辅以端点堆积、时域平顶、带外互调抬升三面互证。

## 11.6 验证顺序（文档与脚本检查通过之后再上板）

审查要求"文档与脚本检查通过后，再依次验证"。**离线检查已完成**：

| 检查 | 结果 |
|---|---|
| 三个 shell 脚本 `dash -n` | ✅ 通过 |
| `S99board` 执行顺序核对 | ✅ 风扇 49 < 模式 53 < 复制校验 80 < configfs 85 < overlay 104 < 终验收 112 |
| `sources` 文件存在性 | ✅ 13 项全部存在（含新增 `p16_*`） |
| 文档链接 | ✅ 202 条，0 断裂 |
| `TX-SOURCE-STATUS.json` | ✅ 有效 JSON，字段已统一 |
| Python 测试 | ✅ 702 passed |

**上板验证顺序（未执行，待上电）**：

1. 部署新模式脚本（`board-mode` absent 时先 `echo display > /etc/board-mode`）
2. 采集自启证据（`EXP-HW-006` §11 A）→ 判据：`state=operating`、`/dev/fb0`、`gpio914=out`、dmesg 含 `fb0` 与 `100x30`
3. 采集触摸持久化证据（§11 B）→ 判据：`243 = 0, 1` 且 `244 = 0, 4095, 0, 4095`
4. 模式往返 display→rf→display，每步 `--evidence`
5. 旧板五步不发射恢复（`START-HERE.md`）
6. 新板配置读回 + 真实短段 I/Q + 格式统计 + 停止/重启采集

**任一步未留 transcript，就保持"待验证"。**
