# 从这里恢复项目工作

**P48小屏频偏单位候选验证进行中。** 先读results/p48-active.json及其报告；COM8由suite按阶段独占。阶段完成必须核实startup_selection_rearmed；不按下方旧状态重复启动。候选仅改显示应用，不改PL/驱动/射频参数或发射。P47学习包仍可直接使用。

---


**当前软件入口：P47（2026-10-22）真实数据包与一键离线回放已交付。** 先读[实验记录](docs/experiments/exp-p47-learning-kit.md)、[恢复清单](docs/handoff/resume-p47-20261022.md)和TX-SOURCE-STATUS.json的p47_current。当前电脑双击`run-rf-learning-demo.cmd`；队员分享包`results/p47-kit-20261022T130520Z/rf-learning-kit.zip`，先解压再按中文README运行。

包含单音/BPSK/QPSK/16QAM共16个原始DMA块、4MiB原始打包IQ及逐点一致的NPZ、参数/标签/索引/校验/读取示例。离线界面可选信号/采集块，播放波形、频谱、瀑布图并导出。8项控制器/完整性检查、全部DMA有限回放、异地解压运行、实际Tk计时播放/暂停/保存通过。没有运行AI，数据仅用于学习/调试，不能冒充独立训练/测试集。

**硬件最后实读仍以P46为准，本轮没有连接或重查板卡。** 继续硬件前先读[P46恢复清单](docs/handoff/resume-p46-20261022.md)和p46_current，重新识别实际boot、wrapper/进程/DMA。不照搬上次通电状态，不热卸驱动或绑定中装PL。

P46真实已知源质量/单音写屏及P45受控冷启动实体显示结论保留；AI、更多独立会话/长稳及历史异常根因仍开放。小屏单位改进本轮未部署。results被gitignore排除，须直接读文件系统。

上一入口原文：[历史快照](start-here-before-p47-20261022t131103z.md)。当前交付回执：`results/p47-delivery-20261022T131103543090Z/report.json`。
