# Zynq 的信号AI识别系统

英文名称：Zynq AI Signal Recognition System。参赛方向：2026 FPGA 创新设计赛道 AMD 自主选题初级组。

芯芯向荣队，中国矿业大学。成员：广泽放、黄冠、刘昌帅。

面向工厂和演出现场的选信道与通信排障需求，作品将信号检测、频谱观测、参数分析和 BPSK/QPSK/16QAM 三类调制识别结合起来。设计报告先说明使用场景，再给出技术实现和实测结果，并提出利用已有参数开展信道质量分析的方法。

当前实物已完成双板受控收发、频谱与 ROI 参数估计、板端识别和显示。信道质量评估属于报告中的参数分析与应用设计，自动评分、选信道排序和现场故障诊断程序尚未实现，也没有工厂或演出现场的验证数据。

发送板采用璞致 P201 / XC7Z020，接收板采用创龙 TLZ7xH-EVM / XC7Z100，均配 AD9361 射频前端。PL 承担射频数字接口、DMA 和显示通路，接收板 ARM 完成前端、FFT、ROI 参数与 CNN 推理。电脑负责发送控制屏中转、校准和归档。已有射频验证采用固定配置的同轴衰减链。

## 评审阅读入口

- 设计报告：[PDF](report/design_report.pdf) / [Word](report/design_report.docx)
- [中英文海报，两页 PPTX](report/poster_zh_en.pptx)
- [现场英文匿名打印版，一页 PPTX](report/poster_en_print.pptx)
- [应用设计与实现范围](docs/application-design.md)
- [复现方法与环境要求](docs/reproduction.md)
- [FIR 验证技能包](skill/README.md)
- [开发协作记录](report/development-chat/README.md)
- [第三方来源与许可证](notice.md)

报告、海报与本仓库使用同一作品名称和测试口径。验证数据和原始日志位于 `results/`，技能包的历史验证记录位于 `sim/fir-skill-validation/validation/`。演示视频已由队伍制作并另行提交，本仓库不提供视频文件或未经核实的播放链接。

## 主要结果

| 项目 | 结果与测试范围 |
| --- | --- |
| 独立识别测试 | 原冻结 INT8 流程正确 52/54 帧，准确率 96.30%；条件限于固定设备、频点、符号率、接线与增益 |
| 板端算法链 | 约 22.46–22.55 ms/块；不包含采集、文件 I/O、绘图与显示刷新 |
| 定点 FIR | 完成整数黄金参考、RTL 仿真和 OOC 综合优化；尚未接入部署中的 ADC→DMA 通路 |
| 可复用技能包 | 三类正式案例、正反例和接口契约，历史独立验证共 11 项 |

后续固定八相位平均改变了推理流程，其演示回归与原冻结流程的独立测试分别报告。数字功率尚未标定为 dBm，ADC 块间缺口未知。当前整机仍依赖电脑进行控制中转；FIR 技能包属于普通可复用验证流程，尚未验证通用 PYNQ Skill。

## 离线检查

使用 Python 3.11+，在虚拟环境安装 NumPy 后执行：

```text
python sim/verify_package.py
```

该检查覆盖文件完整性、Python 语法、FIR 与独立有理数参考的对照，以及四类 RF 学习数据的 RX12/NPZ 一致性。检查过程无需板卡，不访问串口或加载位流。完整 Python 测试的依赖见 `requirements-lock.txt`。离线检查、RTL 仿真、FPGA 综合实现和上板验收各有独立范围。

## 工程目录

| 指南目录 | 本仓库对应内容 |
| --- | --- |
| src/ 设计源码 | src/rfsig/、embedded/、host/、fpga/rtl/、configs/ |
| sim/ 验证 | sim/、tests/、fpga/tb/、experiments/、results/ |
| build/ 构建与报告 | build/、fpga/fft-vivado/、fpga/fir-vivado/、fpga/integration/、fpga/vendor-baseline/、results/ |
| board/ 上板与实测 | board/、embedded/、host/、results/ |
| data/ 测试与参考 | data/rf-learning-kit/、data/measured-data/、results/ 中的输入与模型 |
| skill/ 技能包 | skill/verify-fixed-point-fir/；验证记录见 sim/fir-skill-validation/ |
| report/ 设计报告与海报 | report/design_report.docx、report/design_report.pdf、report/poster_zh_en.pptx、report/development-chat/ |

`archive/source-variants/` 保存历史源码差异，`archive/history/` 保存阶段记录。历史记录中的状态对应其记录日期，当前结果以设计报告及相应验收证据为准。

## 复现状态与许可

实际 FPGA 工程使用 Vivado 2021.1。仓库保留构建脚本、部分厂商源代码、仿真与实现记录；完整厂商工程、迁移构建输入和启动镜像需按版本关系配置。目前尚无干净环境下完整硬件重建的验收记录，依赖和准备步骤见 [复现说明](docs/reproduction.md)。CDC 与外部 I/O 时序等开放事项在报告中列明。

`package_manifest.json` 用于文件完整性校验，`source_manifest.json` 记录来源和路径映射。文件路径采用英文命名，`README.md`、`SKILL.md` 保留约定名称；`build/prepare_workspace.py` 可在新目录恢复原工程文件名大小写。环境信息隐去和路径适配记录见 `publication_changes.json`。原始 ADC 字节和实测数值保持原样。

原创贡献采用 [MIT](license.txt)。ADI、AMD 及板卡厂商内容适用各自的许可条款，见 [第三方说明](notice.md)。工具安装器、许可证及预编译位流、板端二进制不随本仓库分发。
