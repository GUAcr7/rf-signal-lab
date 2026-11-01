# 从这里恢复项目工作

**2026-10-24最新：passed_controlled_real_RF_AI_and_live_LCD_checkpoint_ready。**

受控真实RF独立测试（int8）：52/54帧；实际ARM完整前端/分类与Python一致。小屏实时AI核验：True。

先读[恢复清单](docs/handoff/resume-p52-20261024.md)、[实验记录](docs/experiments/exp-p52-real-rf-ai.md)和results/p52-active.json。权威字段为TX-SOURCE-STATUS.json的p52_current。

已停止收发、关闭串口并恢复原P48下一次自启动；板仍通电，未关机。AI候选尚未设为开机默认，十分钟AI整机演示未验收。重新通电需重新认板、更新boot身份并用单音校准，不能重放旧命令。

results/被Git忽略，必须直接读文件系统。检查点：`results/p52-checkpoint-20261024T081337072649Z/report.json`。

此前完整入口保存在`START-HERE-BEFORE-P52-20261024T081254Z.md`，旧P51和UART记录为历史，不能替代当前状态。
