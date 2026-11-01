# 从这里恢复项目工作

**P51半小时稳定性试验进行中（2026-10-23）**：先读[本轮记录](docs/experiments/exp-p51-stability-and-ai-input.md)及最新results/p51-board-*/report.json。COM8由有界试验运行器独占；下一次启动选择暂时暂停以归档，结束必须核验idle并恢复同一P48 profile。下方P50状态为历史，不按它重复启动或假定idle。

---

**当前入口：P50（2026-10-23）新版P48已完成一次受控真正断电后的自主接收/显示验证。** 先读[实验记录](docs/experiments/exp-p50-cold-units.md)、[恢复清单](docs/handoff/resume-p50-20261023.md)和TX-SOURCE-STATUS.json的p50_current。

新boot `a5313ffa-483a-4f9e-b0a4-dbe9a22234fc`，本次自主运行756.3秒/1481次更新，原始I/Q、显存、软件时钟/寄存器、显示单位和防休眠复核通过。超过660秒实体屏幕亮着且更新的人工确认：**True**。

完整profile `/etc/p43-20261023T130008Z`已重新启用，默认P48。当前RX安全停止、串口关闭、taint0、无pending/disabled，板仍通电未关机；下次工作先读身份/boot/进程，不重放旧值。

一次冷启动成功不关闭历史0xFF/质量波动根因。长稳、多次冷启动、无损连续性、校准与独立真实AI仍开放。P47学习包仍可用。

检查点：`results/p50-checkpoint-20261023T134420296054Z/report.json`。results不在Git，直接读文件系统。
