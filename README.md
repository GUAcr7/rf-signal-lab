# RF Signal Lab

基于 Zynq-7000 与 AD9361 的射频信号分析及轻量化调制识别系统。参赛方向：2026 FPGA 创新设计赛道，AMD 自主选题初级组（组别由提交者确认）。本仓库由 2026-10-28/29 的资料快照整理，整理日为 2026-11-01。

发送板为璞致 P201 / XC7Z020，接收板为创龙 TLZ7xH-EVM / XC7Z100，均配 AD9361。当前 PL 承担射频数字接口、DMA 和显示通路；数字前端、FFT、ROI 参数与 CNN 在接收板 ARM 运行。电脑承担触屏控制中转、校准和归档。运行范围为同轴衰减链中的受控三类调制。

## 快速阅读

- [设计报告 PDF](report/design_report.pdf) 与 [可编辑 Word](report/design_report.docx)
- [提交要求对照与缺项](docs/submission-checklist.md)
- [复现入口与限制](docs/reproduction.md)
- [第三方归属与许可边界](notice.md)
- [FIR 技能包](skill/README.md)
- [大模型协作记录说明](report/development-chat/README.md)

## 可核验的结果

原冻结 INT8 流程在 54 帧独立受控真实射频测试中正确 52 帧，96.30%；受设备、频点、符号率、接线与增益条件限制。后来固定八相位平均改变了推理流程，其演示回归不作为新的独立测试成绩。板端算法链约 22.46–22.55 ms/块，计时不包含采集、文件 I/O、绘图与显示刷新，不是端到端时延。

自研定点 FIR 已完成独立整数参考、RTL 仿真和 OOC 综合优化，尚未接入部署中的 ADC→DMA 通路；不能写成已经完成 PL 算法加速。FIR 技能包含三类案例、正反例与失效条件，属于普通可复用技能包，未验证通用 PYNQ Skill。数字功率尚未标定为 dBm，ADC 块间缺口未知，整机仍需电脑控制中转。

## 不连接板卡的检查

使用 Python 3.11+，在虚拟环境安装 NumPy 后执行：

```text
python sim/verify_package.py
```

该入口只检查发布文件哈希、Python 语法、独立有理数 FIR 对照及四类真实 RF 学习数据的 RX12/NPZ 一致性。它不发射、不连接串口、不加载位流。原工程的 pytest 依赖见 `requirements-lock.txt`，完整历史测试记录与此次发布检查分别保留，不能相互替代。

## 目录对照

指南推荐结构可按下表在本仓库定位；保留原工程模块边界，避免移动代码后破坏相对导入。

| 指南目录 | 本仓库位置 |
| --- | --- |
| src/ 设计源码 | src/rfsig/、embedded/、host/、fpga/rtl/、configs/ |
| sim/ 验证 | sim/、tests/、fpga/tb/、experiments/、results/ 中的精选记录 |
| build/ 构建与报告 | build/、fpga/fft-vivado/、fpga/fir-vivado/、fpga/integration/、fpga/vendor-baseline/、results/ |
| board/ 上板与实测 | board/、embedded/、host/、results/ |
| data/ 测试与参考 | data/rf-learning-kit/、data/measured-data/、results/ 中的归档输入与模型 |
| skill/ 技能包 | skill/verify-fixed-point-fir/；验证证据见 sim/fir-skill-validation/ |
| report/ 报告与协作 | report/design_report.docx、report/design_report.pdf、report/development-chat/ |

`archive/source-variants/` 保存不同于当前源码的历史代码内容；不是额外的当前部署入口。`archive/history/`、旧实验说明中的“最新状态”均对应其记录日期，阅读时以阶段和验收范围判断。

## 路径、完整性与许可

公开路径采用英文小写、数字、下划线或连字符以及常规扩展名。`README.md`、`SKILL.md` 使用指南和技能加载器约定的名称。历史文件名的大小写通过 `source_manifest.json` 记录，构建前可用 `build/prepare_workspace.py` 在新目录恢复原项目路径；代码中的历史路径未盲目批量替换。

`package_manifest.json` 是本次发布文件的哈希清单；`source_manifest.json` 记录输入 ZIP 哈希、来源成员及路径映射。公开副本隐去了原 Windows 用户目录，历史板卡登录脚本改用 `RFSIG_BOARD_PASSWORD` 环境变量，见 `publication_changes.json`。这些改动不改变实测数字和 RF 数组。学习套件清单已按发布副本重新计算；原 ADC 字节保持不变。

原创贡献采用 [MIT](license.txt)，ADI/AMD/厂商内容保留原条款，详见 [NOTICE](notice.md)。不分发工具安装器、许可证或未经确认可公开分发的预编译位流/板端二进制。

本仓库覆盖已提供的代码快照和精选证据，不包含原包明确省略的完整厂商工程、全部大体积采样、全部迁移构建输入与演示视频。目前尚未完成干净环境全量硬件重建，不能将这个仓库称为一键烧录包。已提供内容的完整本地留档 ZIP 与公开仓库副本分别交付。
