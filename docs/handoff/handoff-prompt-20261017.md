# 历史交接，当前入口已更新

最新请读 [HANDOFF-P22](handoff-p22-20261017.md)。下面内容是此前阶段的历史交接，不再作为当前任务顺序。

# 交接提示词：RF 信号分析实验台（给另一个 AI）

> 直接把本文件全文作为提示词交给对方即可。文中所有数字都来自已归档的实测或代码，路径相对工程根目录。

---

## 0. 你的角色与工作方式

你是这个项目的**执行工程师**。工作目录：

```
C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab
```

Python 环境：`.venv\Scripts\python.exe`（**不要**用系统 python）。

### 必须遵守的五条纪律

1. **一条结论只有三种状态**：已实现 / 已验证 / 待做。任何写进文档的结论必须能指向 `results/` 下的 transcript、report.json 或原始数据。**没有归档就等于没验证。**
2. **不改写历史**。发现旧结论错了，**追加勘误**（在原文加 ⚠️ 作废块 + 说明），不要删掉重写。这样追溯链不断。
3. **不要为了修正记录而重新发射**。测量值就是测量值，记录错了改记录。
4. **每次上板操作都带 `--evidence`**（`p15_serial_read.py`、`p06_arm_serial_run.ps1`、`p12_serial_upload.ps1` 都有这个参数）。本期最大的浪费就是"看到了但没归档"。
5. **区分"代码写完"、"模拟通过"、"上板通过"、"真实射频验证"** —— 四者不可互相冒充。

---

## 1. 项目目标（竞赛任务）

Zynq + AD9361 软件无线电平台，做三件事：

1. 屏幕显示频谱/星座等实时信息
2. 对接收信号估计**中心频率、占用带宽、相对功率**
3. 对 **BPSK / QPSK / 16QAM** 做自动调制识别

目前 2、3 已在真实双板链路上打通；1 只在自绘 UI 层面完全空白。

---

## 2. 硬件与当前状态

| | 旧板 | 新板 |
|---|---|---|
| 型号 | PUZHI PZSDR P201（XC7Z020） | Tronlong TLZ7xH-EVM（**XC7Z100**） |
| 串口 | **COM9**（也占 COM10），需登录，密码 `analog`，用户 `root` | **COM8**，免密 root，主机名 `Zynq-Tronlong` |
| 内核 | 5.10.0 | 4.9.0-rt1-xilinx |
| libiio | 0.24 | **0.20**（旧板的 ARM 程序不能直接用在新板） |
| 存储 | **根文件系统是 `rootfs`，`size 0`，全内存 —— 断电全清** | SD 卡，持久 |
| 当前模式 | — | `/etc/board-mode` 决定，现为 `display` |

两板通过 **旧板 TX1 → 新板 RX1A(J110) 直连 SMA 线**，**无衰减器**。

### 2.1 上板环境的关键约束（都是踩过的坑）

- **串口控制台 80 列自动换行**：单条命令 ≤ **72 字符**，否则被截断。
- **旧板 `/tmp` 是内存**：任何上传在重启后消失，必须同一次开机内完成"上传→验证→发射"。也没有持久目录可用。
- **`boot_id` 每次重启都变**，它是发射守卫的身份，用旧值会被拒。上传前先读 `cat /proc/sys/kernel/random/boot_id`。
- **上传工具** `experiments\p12_serial_upload.ps1`：
  - 板端目录必须匹配 `/tmp/p12-source-stage-[a-z0-9-]+`
  - 单次 ≤ 4 MiB
  - `-ExpectedSha256` 是**输入文件**的哈希，传错会直接拒绝
- **串口是独占资源**：两个后台任务同时用会 `访问被拒绝`，表现为"发射没发生但采到了数据"。必须串行。
- **新板显示与射频互斥**：PL 里只有一份位流。`board-mode display|rf` + 重启切换，不能热切换。

---

## 3. 已完成并验证的能力

### 3.1 旧板恢复（零发射）

`docs/experiments/EXP-HW-010-old-board-recovery.md`

| 步 | 结果 |
|---|---|
| 上传 | `UPLOAD_PASS sha256=9af83ce9…` |
| 执行位 + 载荷 | `chmod +x` 后 **8/8 OK** |
| `--inspect` | 退出码 0，六项射频属性符合冻结配置 |
| 六支波形 `--check` | **6/6 `INPUT_CHECK_PASS`** |
| `boot_id` | 与 `tx_guard_identity` 一致 |

**注意**：归档里 `arm-tx-source` 存储模式是 **0666**，解包后必须 `chmod +x`，否则 `Permission denied`。

### 3.2 新板显示/触摸/模式/采集

`docs/experiments/EXP-HW-007`、`008`、`009`

- **显示自启**：`fpga0/state=operating`、`/dev/fb0`、`gpio914/direction=out`、dmesg 含 `fb0: frame buffer device` 与 `100x30`
- **触摸持久化**：重启后 `Evdev Axis Inversion(243) = 0, 1`、`Evdev Axis Calibration(244) = 0, 4095, 0, 4095`、`Divide by Zero` 计数 **70 → 0**、X 存活。用户已确认"点的很准"
- **模式往返** display → rf → display：每段 dmesg 都有六行 `board-init: …`，rf 段 IIO 设备 4 个、display 段回到 1 个
- **真实 I/Q**：`iio_readdev` 可采、可打断、可恢复

### 3.3 双板链路与线性上限

`docs/experiments/EXP-HW-011-two-board-link.md`

配置：TX 端口 A、`tx0_hardwaregain = -10 dB`、`tx_lo = 2450 MHz`；RX `manual` + `in_voltage0_hardwaregain = 0`、RX_LO **必须改成 2450 MHz**（默认 2400）。

| 数字峰值 | 平均功率 | 峰均比 | 步进增益 | 判定 |
|---|---:|---:|---:|---|
| 64 | 13,243 | 1.59 dB | — | — |
| 128 | 51,353 | 0.82 dB | +5.886 dB | 线性 |
| 256 | 192,362 | 0.50 dB | +5.736 dB | 线性 |
| **512** | 636,868 | 0.26 dB | **+5.199 dB** | **压缩** |

**结论：直连可用，上限 256 档（RX 0 dB）。** 全程 `endpoint=0`、峰值最高 823/2048，**不是 ADC 削顶，是模拟链路压缩**，但**无法区分 TX 侧还是 RX 侧**。

### 3.4 三调制接收与分离

`docs/experiments/EXP-HW-012-modulated-reception.md`

因为 512 档压缩，重新生成了 **256 幅度**的调制波形（控制实验：用相同参数重生成 512 档，三支 sha256 与归档**逐字节一致**，证明只改了幅度）。

每段 65,536 样本切成 **8 块 × 8,192（64 符号）**，每块独立估载波、独立定相位：

| 调制 | 载波 (Hz) | 正交抑制 (dB) | 幅度 CV |
|---|---|---|---|
| BPSK | 994,404 ± 819 | **+26.08 ± 16.14**（最小 +9.04） | 0.360 ± 0.215 |
| QPSK | 986,550 ± 21,218 | **+0.17 ± 1.31**（最大 +2.94） | **0.137 ± 0.085**（最大 0.294） |
| 16QAM | 987,891 ± 30,857 | −0.17 ± 0.67 | **0.393 ± 0.057**（最小 0.346） |

**可分性**：BPSK 用正交抑制可与其余分开（间隙 6.1 dB，无交叠）；QPSK 与 16QAM 用幅度 CV 分开（间隙 0.052，约 15%，**偏窄**）。

**载波偏差**：三次采集都落在 987–994 kHz，相对标称 960 kHz 偏 **+28～+34 kHz ≈ 11–14 ppm**。

### 3.5 工具与测试

- `729` 项 Python 测试通过
- `src/rfsig/saturation.py` + `tests/test_saturation.py`（19 项）：步进线性判据
- `src/rfsig/iq_io.py`：`decode_iq_dma_s16()` 支持任意通道数
- `experiments/p16_check_saturation.py`：CLI，退出码 0=线性 / 4=非线性
- `experiments/p18_extract_capture.py`：从 transcript 提取 base64 → 校验板上 sha256 → 解码
- `experiments/p21_analyse_mod_capture.py`、`p21_block_analysis.py`：星座分析与分块特征

---

## 4. 未解决的问题（按优先级）

### P1：块内载波跟踪（最关键的信号处理缺口）

**现象**：把采集从 8,192 加到 65,536 样本，正交抑制从 **+11.26 dB 掉到 +5.97 dB**。分块后回到 **+26.08 dB**。

**已确认的因果**：两块板独立晶振，载波在 2.13 ms 内漂移；单一载波估计只能对齐块内一段。分块把漂移问题绕开了，但**每块只有 64 符号，单块样本并没有增加**。

**要做**：每块加长到 256–512 符号，**同时**在块内做载波跟踪（PLL 或判决反馈），而不是二选一。目标是把正交抑制在 512 符号/块下也维持在 +20 dB 以上。

**已被排除的错误做法**（别重走）：
- 用 500 Hz 步进的频率网格搜索：65,536 样本时矩峰宽约 470 Hz，**比步进还窄**，搜索会走到窗口边界（实测 −206 kHz）
- 在未去载波的数据上做矩估计却限制搜索带：真峰在 `order × 1 MHz ≈ 2 MHz`，窄带内只有噪声（实测载波估计散在 33–361 kHz）

### P2：QPSK 与 16QAM 的区分太窄

幅度 CV 间隙只有 0.052（相对约 15%）。需要更强的判别量（例如判决后残差、幅度直方图拟合、符号率谱线），或给出置信区间而非单阈值。

### P3：缺 EVM / 误符号率

没有判决定量指标，就谈不上"识别器"。当前只有特征值。

### P4：压缩发生在 TX 还是 RX

需要频谱仪旁路观察。影响：若在 TX 侧，即使把 RX 增益降到 0 dB 也无法靠降增益恢复线性。

### P5：`--full-scale 2048` 未实测

现在按 AD9361 12 位推断。需要用已知幅度信号标定，否则 `endpoint_fraction` 只能当相对量。

### P6：屏幕自绘 UI 完全空白

任务 ① 的展示层还是零。现在屏幕上只有 XFCE 桌面，没有任何本项目的东西。可用 `/dev/fb0`（800×480×32，stride 3200）直接绘制，但要注意**射频模式下没有 fb0**。

### P7：FPGA FFT 未上板

---

## 5. 一期踩过的坑（照抄，别重犯）

### 5.1 触摸/桌面

- `/etc/X11/Xsession` 用 **`.` source** `Xsession.d` 里的脚本。**在里面写 `exit` 会杀掉整个桌面会话**，症状只有一句 `xinit: connection to X server lost`。辅助函数用 `return`，**顶层不要 `exit`**。
- `/etc/X11/Xinit.d` 对本板启动路径**无效**（它属于另一个客户端 `/etc/X11/Xinit`）。
- 上传后文件是 **644**，而 Xsession 循环检查 `-x`，所以**脚本静默不执行**。部署后必须 `chmod 755`。
- 真正的标定来源是 **`/etc/pointercal.xinput`**，X 每次会话都会加载它。厂商脚本 `30xTs_Calibrate.sh` / `30xinput_calibrate.sh` 会在触摸不可用时写出**退化值** `2915, 2915, 2759, 2662`。现已改成正确值并保留 `99touch` 作兜底。
- 桌面是 **XFCE**，不是 LXDE（早期文档写错过）。

### 5.2 采集/格式

- `cf-ad9361-lpc` 是 **4 通道**（I1,Q1,I2,Q2），`-s N` 写出 `N × 4 × 2` 字节。**按 2 通道解析不会报错，只会静默给出半数样本且通道混叠。**
- 通道格式 `le:S12/16>>0`（12 位符号扩展到 16 位）。
- `iio_readdev` 退出后会把 `scan_elements/*_en` 复位为 0，**不能用它判断刚才的采集配置**。
- 打断采集（`timeout` 杀掉）后设备**可立即恢复**，已验证。

### 5.3 文件/工具

- **CRLF 陷阱（已犯两次）**：`Path.write_text` 在 Windows 上把 `\n` 转 `\r\n`，BusyBox `sha256sum -c` 于是按 `name\r` 找文件报 `can't open`。写清单文件用 **`write_bytes`**。
- 发射守卫会**自己算文件 sha256** 并与命令行参数比对，不符即退出 2 且**不发射**。别把 A 波形的哈希配 B 文件。
- 三支调制波形在 512 幅度下已归档；256 幅度版在 `results/p21-mod-waveforms-20261017T122536Z/`。
- **PowerShell 陷阱**：here-string 里嵌双引号/中文/`$?` 会被展开或截断；Python f-string 会被破坏。**写 `.py` 文件再跑**，不要用 `python -c` 传长脚本。
- `p06_arm_serial_run.ps1` 的 `-EvidenceDirectory` **不能重复使用**（存在即拒绝），每次换个名字。

### 5.4 一个方法论教训

分析脚本第一版没有载波精搜，直接拿 PSD 峰值下变频，得到"正交抑制 +0.92 dB"，差点得出"这不是 BPSK"的错误结论。
`|⟨unit^m⟩|` 本身就是"星座是否对齐"的指标 —— **先用它找频偏，再用对齐后的数据算特征**，顺序反了会自我否定正确答案。

---

## 6. 建议的下一步

1. 先写**块内载波跟踪**（含单元测试，用合成 BPSK/QPSK/16QAM 验证收敛），再上板
2. 用 256 档、每块 256–512 符号重采三类，给出带区间的可分性表
3. 加 EVM / 误符号率
4. 再做屏幕自绘 UI（注意模式互斥：显示模式才有 `/dev/fb0`）

**不要**在这三步之前谈"AI 调制识别"——没有可信的输入质量基线，训练出的模型只是在拟合自己的接收链缺陷。

---

## 7. 关键文件索引

| 用途 | 路径 |
|---|---|
| 总览与现状 | `START-HERE.md` |
| 机器可读状态 | `TX-SOURCE-STATUS.json` |
| 勘误总账 | `docs/experiments/EXP-ERRATA-20261017.md` |
| 双板链路 | `docs/experiments/EXP-HW-011-two-board-link.md` |
| 调制接收 | `docs/experiments/EXP-HW-012-modulated-reception.md` |
| 新板显示/触摸 | `docs/experiments/EXP-HW-007-touch-persistence.md` |
| 模式往返 | `docs/experiments/EXP-HW-008-mode-round-trip.md` |
| 新板 I/Q 格式 | `docs/experiments/EXP-HW-009-new-board-iq-capture.md` |
| 电平核算与饱和判据 | `docs/design/rx-input-budget-20261017.md` |
| 板端脚本归档 | `board/`（含 README 与触摸原始数据） |
| 串口工具 | `experiments/p15_serial_read.py`、`p15_serial_send.py`、`p06_arm_serial_run.ps1`、`p12_serial_upload.ps1` |
| 信号处理 | `src/rfsig/saturation.py`、`iq_io.py`、`spectrum.py`、`pulse_shaping.py`、`bandwidth.py` |
