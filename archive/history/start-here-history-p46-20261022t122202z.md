# 从这里恢复项目工作

**当前入口：P46（2026-10-22）已知射频源与小屏数值链验收完成。** 先读[实验记录](docs/experiments/exp-hw-036-merged-known-rf-quality.md)、[恢复清单](docs/handoff/resume-p46-20261022.md)和`TX-SOURCE-STATUS.json`的`p46_current`。`results/p46-active.json`是当前机器入口，results不在Git，须直接读文件系统。

单音、BPSK、QPSK、16QAM共16个完整返回缓冲/4MiB原始IQ已归档并逐窗口通过。调制参考EVM约−36.7至−38.6dB，每组范围不到1dB；已知符号检查3012个、0错误。已知单音写屏8秒/16次更新，FFT/RMS/总功率与独立NumPy一致，原始前缀和显存回读已保存。它们是已知源诊断，**不是盲AI、独立BER或无损连续接收验收**。

**当前RX idle、TX限时守卫已正常退出、串口关闭、两板仍通电，未关机。P43持久自动启动与P44防休眠已重新启用。** 下次首先只读认板、boot、配置SHA、进程和buffer/scan；若已running不另开接收。禁止热卸驱动或绑定中装PL，不重放旧boot。安全断电前先正常关机确认System halted。

P45已通过修复后一次真正断电和十分钟以上实体动态确认；本轮P46没有新增实体屏人工确认。历史严重块间波动未在本轮重现，根因仍开放；0xFF、故障回退、更多冷启动/长稳、CDC/外部IO时序、物理PCLK和绝对RF校准也未关闭。下一步优先独立会话/不同种子的真实RF数据与无泄漏盲分类，再接板端显示。

本轮检查点：`results/p46-checkpoint-20261022T121541752883Z/report.json`；原始质量图：`results/p46-analysis-20261022T115205Z/quality.png`。全部旧状态入口已保存在[历史索引](start-here-history-p46-20261022t121541z.md)，仅供追溯，不作为当前操作指令。
