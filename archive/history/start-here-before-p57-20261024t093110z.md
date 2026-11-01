# 从这里恢复项目工作

2026-10-24 最新：passed_runtime_AI_10minute_controlled_demo_checkpoint_ready。

先读 [恢复清单](docs/handoff/resume-p56-20261024.md)、[实验记录](docs/experiments/exp-p56-runtime-ai-20261024.md) 和 results/p56-active.json。权威字段是 TX-SOURCE-STATUS.json 的 p56_current。

已停止收发、关闭串口并恢复原 P48 下一次开机选择；板仍通电，未关机。AI 候选尚未设为开机默认。断电后重新认板并重做背景/单音校准，不复用旧身份或 IF。

本轮是受控三类信号部署回归，独立识别率仍为 P52 INT8 52/54；不宣称通用未知拒识、无丢样或正式 PL FFT 完成。

results/ 被 Git 忽略，直接读文件系统。检查点：`results/p56-checkpoint-20261024T091604478418Z/report.json`。
