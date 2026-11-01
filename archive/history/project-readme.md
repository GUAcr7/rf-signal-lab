> 2026-10-19 HW-022更新：[射频与显示合并记录](docs/experiments/exp-hw-022-rf-display-integration.md) 已完成离线完整综合/布线及GPIO/VTC有限仿真；未生成/加载新位流，外部IO时延与CDC/复位、实际屏幕并行仍待验收。下文较早的“尚未合并”等状态只作历史依据。

> 2026-10-19 晚 HW-023更新：[设备树/CDC有限仿真与内核异常恢复](docs/experiments/exp-hw-023-device-tree-cdc-and-kernel-recovery.md)。原厂overlay热卸载触发异常，用户重新上电后接收已恢复；保护脚本已部署，全部自动卸载重试已停用。合并设备树240项与部分数字仿真通过，合并固件仍未上板。当前机器状态见`p31_current`，不是下文历史启动状态。

# 基于 Zynq 的通信信号实时分析与 AI 调制识别系统

2026-10-19 更新：[HW-021](docs/experiments/exp-hw-021-vendor-migration-and-reconnect.md) 已完成新板接收恢复和 RF/显示独立完整综合；原厂源未改、未烧写新位流。合并、接口约束/时序、显示升级功能及冷启动可靠性仍待验收。旧工具阻塞现已解除；下文早期“待授权/找不到器件”为历史状态。

2026-10-18 工具更新：[HW-020](docs/experiments/exp-hw-020-vivado-enterprise-setup.md) 已完成 Enterprise 试用授权安装、Zynq-7000 增量补装和 XC7Z100 精确型号最小综合。到期 2026-12-17；当前电脑可继续。下文授权/器件待办为历史状态，RF/display 合并及其上板仍未完成。

目标平台：璞致 P201 系列，Zynq-7020 + AD9361。以老师确定的三项任务为范围：时域/频域/时变可视化，中心频率/占用带宽/相对功率估计，AI 调制识别。计划周期六周。

## 当前入口与状态

前轮采样基线：[HW-019](docs/experiments/exp-hw-019-memory-diagnostic-and-build-readiness.md)，512 缓冲稀疏诊断；真实 AI、完整无丢样和独立显示共存尚未完成。

> **状态以这两个文件为准**：[START-HERE.md](start-here.md)（开工入口与断电恢复步骤）、[TX-SOURCE-STATUS.json](tx-source-status.json)（机器可读状态）。

2026-10-18 最新审查与修复见 [HW-018](docs/experiments/exp-hw-018-review-and-streaming.md)：旧 P201 发射、新 TLZ7xH-EVM/FMCOMMS3 接收的三调制有限快照通过；修复参考/相位/EVM 与启动脚本检查。四通道 16 缓冲检出 11 处跳跃，只采 RX1 的 16 缓冲未检出非周期跳跃且逐窗已知符号质量通过；仍不能证明长期无丢样。全项目 **840 项 Python 回归通过**。真实 AI、FPGA 数据链和 RF/display 共存待完成。

> 下面的"最新进度"条目是历史记录，**数字与结论可能已过期**，每条都已标注对应的最新记录。

- **最新进度（2026-10-16 晚）**：旧 P201 **已实际执行 3 次限时射频发送**（3 s / 5 s / 5 s，使用 +960 kHz 与 +1.92 MHz 两种单音），板卡日志显示每次均正常收尾（`rf_settings_written=false`，未改任何射频参数）。频谱仪上确实出现信号主峰，主峰形状符合 RRC 成形特征。
  **但精确频率与输出功率尚未验收**：唯一归档的仪器照片（`results/p13-tx-m2b-5s-20261016-1800/analyzer-first-signal.jpg`）上标记停在显示伪影（`2.450000000 GHz / -56.24 dBm`）而非主峰；写有 `2.4509625 GHz / -24.43 dBm` 的那张照片当时未保存。**需补拍一张标记落在主峰上的照片**后才能定稿。详见 [首次发射记录与证据更正](docs/experiments/exp-tx-001.md)。
  当前测试基线：全项目 **667 项 Python 测试通过**（归档 `results/p13-python-regression-20261016T082222172Z/`）、**43 项**模拟 IIO 场景通过（`results/p12-native-mock-20261016T074043903949Z/report.json`）。
  板卡供电硬要求：**5V/1A USB 供电加强线直插电脑 USB 口、不经集线器**，否则 AD9361 读回非法，见 [EXP-HW-004](docs/experiments/exp-hw-004.md)。
  新接收板（TLZ7xH-EVM + FMCOMMS3）尚未接入；屏幕与射频共存未验证。
- 最新进度（2026-10-16 13:16）：已读取新借TLZ7xH-EVM/FMCOMMS3资料，制作原P201有限时信号源候选、三套共15个循环波形、ARM交叉编译和34项模拟IIO验证；当时全项目646项Python测试通过，含DMA/PHY/文件速率一致守卫。当时尚未实际发射，新板屏幕与射频共存未验证。**该条目中的 646、34、"尚未实际发射"均已过期，最新值见上一条。** 详见 [当天记录](docs/experiments/exp-auto-20261016.md) 与 [双板方案](docs/design/two-board-rf-link.md)。
- 最新进度（2026-10-15）：新增中文持续快照监测、有界历史、完整分段归档和校验回放；30 分钟实际 RX 共 14,828 块通过，另有 10 分钟复测。合成 CNN 显示已对接，真实 RX 仍不输出未验收类别。独立 burst／流水线 FPGA FFT 的参考、自检和模块布局布线已完成，流水线仿真含启动约 83.70 MS/s；整体原厂派生时序仍有跨时钟问题，未集成或部署。见 [当天实验记录与证据](docs/experiments/exp-auto-20261015.md)。
- 新界面入口：run-analyzer-monitor.cmd；用法见 [监测与归档回放](docs/lesson-p11-monitor.md)。学习材料：[项目核心步骤](docs/project-learning-guide.md)、[FPGA FFT 模块](docs/lesson-p07-fpga-fft.md)。
- [详细实施与学习指南：P00–P12](docs/implementation-guide.md)：2026-10-15 更新，包含每步学习内容、流程、验收、六周安排和后续 AI 协作提示。
- 历史进度（2026-10-11）：真实I/Q采集/保存/回放与电脑有限监测通过；Vivado2021.1安装/原厂构建和JTAG通过，新FPGA时序仍失败、未烧写。ARM离线FIR、原生IIO有限采集、软件FFT/PSD/ROI、传统基线和已训练115参数CNN已实际执行并回收对照。新独立合成测试CNN FP32 92.59%、INT8 MAC 93.06%；真实RF分类/持续队列/独立屏待验证。最新476项Python测试通过；详见 [本次完整进度与证据](docs/experiments/exp-auto-20261011.md)。
- [六周流程与验收目标](docs/roadmap.md)
- [每次重新开始工作的清单](docs/implementation-guide.md#19-每次重新开始工作的清单)：使用本次实际端口与配置，已完成的安装和烧录不重复。
- 历史进度（2026-09-28）：[P01 原厂接收验收](docs/experiments/exp-p01.md)与 [P02 Python 读取、保存和回放验收](docs/experiments/exp-p02.md)均在当次启动状态下通过。[P03 已知单音验证](docs/experiments/exp-p03.md)完成了 Python 黄金参考、测试和板卡只读预检；实际环回须先核对带 PA 的 TX 输出、RX 输入、衰减器和实物端口，尚未发射。首次启动的 CHIP_ID 错误在一次正常软件重启后消失，但根因未定；下次启动仍应检查接收设备。
- 2026-09-22 已通过 COM9 登录板卡 Linux，并经 OTG USB 网络 ping 通 192.168.2.1（4/4 回复）；这是早期[启动记录](docs/experiments/exp-hw-001.md)，其后的 IIO 接收验收见 P01。
- 历史排查（2026-09-23）：USB 网络已恢复，GUI 已打开；ad9361-phy 与 TX 接口已注册，但 TX 数字时序自检失败使 RX 采样接口未注册，见 [接收通道缺失记录](docs/experiments/exp-hw-003.md)。这是当日状态，若再次异常需依据本次日志判断。此前启动过程见 [IIO 排查记录](docs/experiments/exp-hw-002.md)。
- [采样与余弦波形课程](docs/lesson-02.md)、[实验记录](docs/experiments/exp-002.md)保留为后续学习资料，不作为开始板卡验证的前置要求。
- [平台依据](docs/platform-notes.md)，[工程与验证约定](docs/workflow.md)
- 已有 BPSK 比特到符号映射及测试，本次新增一个采样入门实验。
- 真实受控RF收发/精度、FPGA FFT、真实调制识别和系统实时性能尚未验收；已经实际完成的ARM离线软件及合成模型验证见最新记录。
- 先前的 lesson-00、lesson-01、EXP-000、EXP-001 保留为学习历史；旧 FMQL/NPU 路线由当前计划替代。

教学先讲直观原理再实现，每次只完成一个小实验，不通过提问或考试推进。第一周验证原厂基础收发，不等理论全部学完再接触板卡。

## 运行实验

在本文件所在目录打开 PowerShell，使用已建立的 Python 3.12.14 环境：

```powershell
.\.venv\Scripts\python.exe experiments\level0_sampling.py
.\.venv\Scripts\python.exe -m pytest
```

图片保存在 `results/level0_sampling.png`。正式复现使用工程内解释器，避免编辑器的运行按钮选择另一套 Python。

新电脑复现时：安装兼容 Python，建立 `.venv`，使用新环境的解释器执行 `python -m pip install -r requirements-lock.txt` 和 `python -m pip install -e .`。

## 工程目录

| 目录 | 用途 |
| --- | --- |
| src/rfsig/ | Python 黄金参考模型，作为后续实现的核对标准 |
| experiments/ | 可单独运行的课程实验 |
| tests/ | 自动核验独立理论预期 |
| docs/ | 课程、计划、实验记录、AI 与硬件记录模板 |
| data/ | 数据来源、采集条件和数据集划分说明 |
| results/ | 本机生成的图表与日志，默认不进入 Git |

到对应阶段再增加 fpga/rtl/、fpga/tb/、ai/、arm/、host/，现在不生成整套硬件工程。

## 版本与记录

本地 Git 已初始化，尚无首次提交。原有暂存文件保留，本轮未提交，也未改写作者身份。首次提交前使用本人真实 Git 作者信息并检查待提交差异。固件、模型权重、采集原始数据、虚拟环境不加入仓库。

每个功能遵守工程约定。FPGA 模块必须有 TestBench；模型记录数据集、SNR、划分、准确率与量化结果；硬件记录资源、时序、延迟和吞吐率。
