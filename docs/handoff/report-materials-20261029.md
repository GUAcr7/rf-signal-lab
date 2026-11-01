# 项目实测数据与自研情况说明（供报告撰写使用）

- 整理日期：2026-10-29
- 用途：供队友撰写比赛/项目报告时直接引用，回答三个问题：**有没有实测数据**、**有没有自研 IP 与 PS/PL 分工**、**有没有可提炼的通用 skill**
- 原则：**只写有证据的结论**，并把"已验证 / 未验证"分开标注；不把计划当作已完成

---

## 一、实测数据（有，且可追溯到原始报告）

### A. AI 调制识别 —— 独立测试（最有说服力）

| 项 | 值 |
|---|---|
| 数据集 | 108 训练帧 / 54 验证帧 / **54 测试帧** |
| 测试来源 | 3 个**未参与训练的 seed**（2313/2314/2315），来自 18 个调制 DMA 块 |
| 分组方式 | 同一采集会话的所有片段归入同一 split，**不做相邻片段随机拆分** |
| **INT8 准确率** | **52/54 = 96.30%** |
| 逐类 | BPSK 17/18、QPSK 17/18、**16QAM 18/18** |
| FP32 准确率 | 51/54 = 94.44% |
| INT8 混淆矩阵 | `[[17,1,0],[0,17,1],[0,0,18]]`（行=真值，列=预测） |
| 基线对照（300 轮，保留为失败记录） | 39/54 |
| 完整 C 前端数值/分类一致性 | 36 次检查通过 |

**必须同时声明的适用条件**：仅限 BPSK/QPSK/16QAM 三类、固定 2450 MHz、240 ksym/s、名义 960 kHz 中频、当前接线与增益。**不等于任意信号识别，也不代表实测 SNR 泛化。**

证据：`results/p52-test-20261024T045844Z/report.json`、`results/p52-final-20261024T081254Z/report.json`

### B. ARM 端实际推理（板端实测，非电脑模拟）

| 信号 | 平均每块 | 峰值 | 内存 RSS |
|---|---:|---:|---:|
| BPSK | 22.55 ms | 22.68 ms | 2.5 MiB |
| QPSK | 22.46 ms | 22.61 ms | 2.6 MiB |
| 16QAM | 22.46 ms | 22.57 ms | 2.5 MiB |

- 计算范围：mix / FIR / 降采样 / DC / RMS / CNN 三窗口分类
- **不含文件 IO**，**不是端到端射频延迟**
- 18 个归档完整 DMA 输入 × 每类 54 窗口，FP32/INT8 的 ARM 输出与冻结的 Python、主机 C 结果一致

证据：`results/p52-ARM-20261024T075009Z/report.json`

### C. 整机冷启动 —— 真正断电后自主运行

| 项 | 值 |
|---|---|
| 触发方式 | **用户真实断电再上电**（非软件重启） |
| 会话时长 | **631.08 秒** |
| 显示更新次数 | **1164 次** |
| 计分区观察 | 207 次 |
| 报出类别次数 | 187 次 |
| **报出类别正确次数** | **187 次（100%）** |
| 计分区覆盖率 | **90.34%** |
| 稳定背景观察 | 257 次，**一次都没有误报类别** |
| 人眼确认 | 用户确认"屏幕亮着，数字或曲线持续更新" |

**必须同时声明**：这 631 秒包含开机等待校准与无源观察，**不等于 631 秒持续调制分类**；且沿用的是已暴露的 seed 2315，属**部署与冷启动回归**，不能替代 A 项的独立测试成绩。

证据：`results/p58-final-20261024T101036Z/report.json`、`results/p58-cold-20261024T095834Z/report.json`、`results/p58-visual-20261024T100220Z/human-event.json`

### D. 射频与解调物理指标（真实采集）

| 调制 | EVM | 正交抑制 | 幅度 CV |
|---|---:|---:|---:|
| BPSK | −37.18 dB | +45.27 dB | 0.0127 |
| QPSK | −37.07 dB | −0.02 dB | 0.0083 |
| 16QAM | −37.04 dB | −0.12 dB | 0.3447 |

可分离性结论：BPSK 的正交抑制约 44–45 dB，QPSK 与 16QAM 的幅度 CV 相差约 40 倍 —— 两类判据都可独立支撑分类。

证据：`docs/experiments/EXP-HW-016-cold-start-reproduction.md`

### E. 其它实测

| 项 | 实测值 |
|---|---|
| DMA 取消/重建 | **8 轮全部通过**，每轮重建后 2 次有效 refill |
| 一次性采集 | 16 × 65536 帧 = **4,194,304 字节**，耗时 **0.0354 s** |
| 显示几何 | 可见 **800×480**、虚拟 **800×960**（双缓冲）、32 bit、stride **3200** |
| 显示时钟 | FCLK0 99,999,999 Hz、FCLK1 199,999,998 Hz、软件像素率 32,999,000 Hz |
| 时钟配置 | **M16.5 / D2 / O25**，LOCK=1（寄存器读回） |
| 自动化测试规模 | **103 个测试文件、608 个 test 函数** |

证据：`results/p33-rx-cancel-board-20261021T031013Z/report.json`、`results/p36-full-rx-board-20261021T032307Z/report.json`、`results/p36-display-readback-20261021T030850Z/report.json`

### F. 自研 FIR 的独立验证数据

| 项 | 值 |
|---|---|
| 结构 | 63 抽头、12 bit 有符号 I/Q、Q17 系数、36 bit 累加器 |
| 处理细节 | 偶舍入（ties-to-even）+ 饱和到 16 bit + 溢出标志 |
| 仿真比对 | **18 组 / 72,356 个输出**逐一比对通过 |
| 综合 | xc7z020clg400-2，100 MHz，**内部 setup/hold 估计 +1.866 / +0.246 ns** |
| 吞吐（结构预期） | 每 66 拍收一对 I/Q → 约 **1.515 MS/s**（非实测吞吐） |

证据：`fpga/rtl/fixed_fir_iq.v`、`fpga/tb/tb_fixed_fir_iq.sv`、`docs/experiments/EXP-P07a-FIXED-FIR.md`、`docs/experiments/EXP-P07a-TIMING-20261011.md`

---

## 二、自研 IP 与 PS/PL 分工

### 2.1 已有的自研 RTL

| 文件 | 内容 | 验证程度 |
|---|---|---|
| `fixed_fir_iq.v` | 63 抽头定点 FIR（自研） | 穷举仿真 72,356 输出 + 独立综合 + 时序修复；**未接入射频链** |
| `rf_display_gpio.v` | PS↔PL GPIO 映射（自研） | 有自写 testbench |
| `rf_display_top.v` | 射频 + 显示顶层封装（自研） | 已用于合并位流 |

**自写 testbench 共 10 个**（`fpga/tb/`）：ADI 异步 FIFO、DMAC 仲裁、显示半时钟、FIR、FIFO/MM 接口、DMA abort、GPIO、VTC 运行时等。

### 2.2 必须如实说明的三点边界

| 事实 | 说明 |
|---|---|
| **部署位流的信号通路仍是厂家 IP** | axi_ad9361 + axi_dmac + VDMA + DRM |
| **FFT 使用的是 Vivado `xfft` IP（v9.1）** | 我们自写的是自检 testbench（`tb_fft1024.sv`，11 帧比对），**不是自研 FFT 核** |
| **自研 FIR 未接入 ADC→DMA 通路** | 源码首行注释原文：*"Standalone P07 reference FIR. Not connected to the AD9361/DMA baseline."* |

### 2.3 PS / PL 分工（这块是清晰的）

| 侧 | 承担内容 |
|---|---|
| **PL** | AD9361 数字接口、DMA、显示控制器（VDMA / DRM / PWM 背光）；合并后同时提供射频与显示 |
| **PS** | libiio 采集控制、公共 IF 校准、AI 推理（ARM C）、帧缓冲绘制、启动与恢复脚本 |
| **电脑** | 离线训练、数据回放、报告与可视化的开发环境（不作为部署依赖） |

文档：`docs/WORKFLOW-NEXT-20261024.md`、`fpga/integration/README.md`、`docs/experiments/EXP-HW-022-rf-display-integration.md`

### 2.4 结论（建议在报告里这样表述）

> 项目已有**自研 RTL 模块并完成独立验证**（FIR、GPIO 映射、顶层封装、10 个自写 testbench），
> 但**当前部署位流的信号处理链仍以厂家 IP 为主**，自研 FIR 尚未接入实际数据通路，
> 自研 PL FFT/功率谱为**下一步必做项**，且明确不能用 ARM 频谱替代其独立验收。

---

## 三、可提炼的通用 skill（有，且已有实物）

| 候选 | 内容 | 为什么符合"通用 skill" |
|---|---|---|
| **真实射频学习与离线回放套件**（约 12 MB） | 4 个案例（tone / BPSK / QPSK / 16QAM）× 4 个 DMA 块 × 65536 采样；含 NPZ 数据、查看器、数据 API、`manifest.json`（逐文件 SHA256）、预览图 | **离线可复现、带完整性校验、别人拿到就能跑** —— 最推荐作为 skill 交付 |
| **固定板卡控制入口** | `host/board_control.py` 菜单式：查板 / 启停 RX / 选空闲 TX 源 / 触发校准 | 把"每次临时写脚本"固化为可复用流程 |
| **主机算法库** `src/rfsig/` | 频谱、占用带宽、功率、解调、载波跟踪、对齐、捕获连续性、面板渲染 | 608 个 test 函数覆盖，可独立复用 |
| **双实现面板渲染** | Python（主机）+ C（板端）使用同一套版面定义 | 跨平台复用同一版面 |
| **实验方法学** | 预注册判据、证据链、失败保留、"静态检查通过≠可上板" | 可单独成节，属评审加分点 |

RF 学习套件说明：`deliverables/rf-learning-kit-20261022T130520Z/README.md`（内含 `manifest.json` 哈希清单）

---

## 四、写入报告时的边界声明（建议原文照抄）

1. **实测数据需标条件**：96.3% 是固定频点、符号率、接线与增益下的受控结果，不等于任意信号识别能力。
2. **"自研 IP"表述要准确**：应写"已完成自研 FIR 的独立验证，尚未接入实际数据通路；当前信号链为厂家 IP；自研 PL FFT 为下一步必做项"，**不能写"全部自研"**。
3. **冷启动 631 秒不是持续分类**：其中包含开机等待校准与无源观察；有效计分为 207 次观察 / 187 次报类别 / 187 次正确。
4. **显示相关**：界面更新次数多**不等于** ADC 无丢样；帧缓冲回读图**不等于**物理屏幕照片（物理屏幕另有用户目视确认记录）。
5. **功率口径**：当前为 ADC 数字码值（counts），**未校准到 dBm**；频率为基带估计值，不等于仪器校准的中心频率。

---

## 五、证据路径索引

| 内容 | 路径 |
|---|---|
| AI 独立测试 | `results/p52-test-20261024T045844Z/report.json` |
| AI 最终验收 | `results/p52-final-20261024T081254Z/report.json` |
| ARM 端推理 | `results/p52-ARM-20261024T075009Z/report.json` |
| 冷启动整机 | `results/p58-final-20261024T101036Z/report.json`、`results/p58-cold-20261024T095834Z/report.json` |
| 人眼确认记录 | `results/p58-visual-20261024T100220Z/human-event.json` |
| DMA 取消/重建 | `results/p33-rx-cancel-board-20261021T031013Z/report.json` |
| 完整缓冲采集 | `results/p36-full-rx-board-20261021T032307Z/report.json` |
| 显示回读 | `results/p36-display-readback-20261021T030850Z/report.json` |
| 解调物理指标 | `docs/experiments/EXP-HW-016-cold-start-reproduction.md` |
| 自研 FIR | `fpga/rtl/fixed_fir_iq.v`、`docs/experiments/EXP-P07a-FIXED-FIR.md` |
| FIR 时序 | `docs/experiments/EXP-P07a-TIMING-20261011.md`、`fpga/fir-vivado/README.md` |
| FFT 工程（使用 xfft IP） | `fpga/fft-vivado/`、`fpga/fft-vivado/tb_fft1024.sv` |
| 射频+显示合并 | `docs/experiments/EXP-HW-022-rf-display-integration.md`、`fpga/integration/README.md` |
| 后续工作流程（W0–W7） | `docs/WORKFLOW-NEXT-20261024.md` |
| RF 学习套件 | `deliverables/rf-learning-kit-20261022T130520Z/` |
| 固定控制入口 | `host/board_control.py` |

> 说明：`results/` 目录不纳入版本控制（gitignore），需直接读取文件系统；`TX-SOURCE-STATUS.json` 中的 `p58_current` 为当前权威状态字段。
