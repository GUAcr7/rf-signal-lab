# P80 发送屏按钮响应优化

日期 2026-10-27。先测 P79 原始日志：屏幕自身回显为毫秒级，APPLY/START 的等待来自重复整机诊断、每次串口唤醒固定等候，以及逐项远程命令。

## 修改及保留的检查

新 `PromptConsole` 遇到完整 root 提示即结束等待，仍核实际 Linux 身份。RX 的完整身份、boot 前后、RF、DMA/扫描、七份配置文件 SHA、启动脚本 SHA、进程完整 argv、校准/进度及原来的 160 行内核日志合成一次只读快照，使用 NUL 字段边界与 gzip/base64 传输。缺字段、重复字段、boot 改变、SHA/RF/内核错误与截断均拒绝。临时 shell helper 仅在 RAM，使用前核实际 SHA。

同一动作内部复用由本进程独占的连接，动作结束或异常必关闭；APPLY 和 START 之间不缓存授权。每次完整 inspect 仍重新读取全部检查值。进度以两个实际读取证明推进，等待与其他读取重叠，没有取消进度检查。原 guard、限时、停止/清理回执、波形 SHA、接收 AI 和 P76 固件均保持不变。

初次只读试验误用了 P201 的 uudecode 上传器；新板没有该命令，检查在发送内容前拒绝，RF=0。失败报告 `results/p80-snapshot-compare-20261027T134421Z/report.json` 保留；改用既有 TLZ7xH base64 上传器。后续只读旧/新完整字段比较通过。为减少短命子进程，字段由逐项 base64 改为 NUL 定界后整体压缩，仍保留显式完成字段和严格字段集合。

## 实测结果

本次与 P79 相同协议回放流程，各有 4 次 APPLY、4 次 START 和 1 次发射中 STOP。下列为收到协议帧至实屏目标状态读回的中位数，不包含人手按压时间，也不代表 ADC 时间。

- check: 9.814 s → 3.480 s（4 次）
- start: 18.470 s → 5.291 s（4 次）
- stop: 6.413 s → 2.585 s（1 次）

首次连接的 helper 部署和完整启动检查在进入 IDLE 前完成，以上不把该初始化说成按键耗时。时延标准在 RF 回归前写于 `results/p80-plan-20261027.json`，没有事后放宽。

三类实际 RF 稳定窗口均通过原有覆盖率≥70%、条件正确率≥90%要求；完整 AI/指标历史、同源 FFT/RMS、停止显存、DMA/DDS 归零及资源释放均通过。输入明确为实屏 printh 协议回放，不是新的全人工彩排或独立 AI 准确率。

对照：`results/p80-snapshot-compare-20261027T135103Z/report.json`；时延复核：`results/p80-latency-review-20261027T140407Z/report.json`；RF 复核：`results/p79-review-20261027T140355Z/report.json`；完整数据：`results/p59-p79-session-archive-20261027T140104645600Z/report.json`。相关 Python 测试 120 项通过。

人工入口已加 `--fast-control`，原路径保留，去掉该参数即可回退。收尾时两板收发停止、数字零源、控制连接释放，仍供电未关机。没有持久板卡启动修改。
