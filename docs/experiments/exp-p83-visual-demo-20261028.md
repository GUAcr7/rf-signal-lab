# P83 无频谱仪人工功能演示与收尾

日期 2026-10-28。用户选择暂不进行频谱仪对照，要求直接功能演示，并确认接线仍为旧 P201 TX1 → 原衰减连接 → 新 TLZ7xH RX1A，TX2/频谱仪未接入。本轮保留电脑中转，不启用 TX2，不修改持久固件。

## 准备及用户反馈

新接收和背景：`results/p79-prepare-session-20261028T111454Z/report.json`。15 秒参考单音：`results/p79-cancel-trial-20261028T111751Z/report.json`，校准 ready 和原生到时清理通过。参考单音被分类为 UNSUPPORTED_TONE 属于既定拒判行为，不是三类识别故障。

人工快速屏控：`results/p80-screen-control-20261028T111832Z/report.json`，600 秒控制窗口，实际人手输入，无自动协议回放。用户反馈“全部正常，演示完成”。用户收到三类自然结束和一次 RUNNING 中 STOP 的操作指引；原始记录仅收到按钮 2（BPSK）、5（APPLY）、6（START）的一轮完整操作，未收到 QPSK、16QAM 或 STOP 帧。记录用户主观正常反馈，不将其替代缺失的原始按键或声称录制视频文件已获得。

窗口到期后服务正常关闭，状态 `partial_P79_interactive_session`。本轮只验收实际观察到的 BPSK 收发及自动结束，三类完整彩排与中途 STOP 继续引用昨日 P81 已通过证据；不把旧结果冒充本次重复验收。

## 收尾与复核

停止/完整归档：`results/p59-p79-session-archive-20261028T112915991322Z/report.json` 通过，保存 AI/指标完整历史、summary、progress、最终 I/Q 和 fb 原始显存。

原版 P79 全三类 reviewer 要求三类和 STOP 齐全，本轮没有降低该入口要求或用失败的完整判据伪装通过。新增离线 `experiments/p83_review_visual_demo.py` 明确审查实际发生的动作，并输出缺项标志。复核 `results/p83-review-20261028T113049Z/report.json` 通过本轮已有动作：

- BPSK 稳定窗口 16 条，接受 16、正确 16；沿用覆盖率≥70%、条件正确率≥90%、至少5条标准。
- 1429 次显示更新、849.374313 秒；最大间隔 0.857807 秒，来源序号和软件时间递增。
- 模型/boot/校准身份及 AI/指标逐行来源配对一致，失效与停止记录清空数值及类别。
- 最终同源 I/Q 的 FFT/RMS 与显示记录匹配，实际停止显存字形核验通过。
- 原生发射回执、缓冲释放、DDS 零源、进程/上下文清理通过。
- `missing_natural_signals=[qam16,qpsk]`、`raw_STOP_packet_present=false`、`actual_inflight_STOP=false`、`complete_three_class_and_STOP=false`。

这是受控 BPSK 演示复核，不是新独立模型准确率、绝对仪器精度对照或整机脱离电脑验收。1429 次显示更新不代表连续 ADC 无丢样。

P79 复用脚本内部仍有 2026-10-27 固定 RF 接线描述；本轮当前确认由 `results/p83-visual-demo-20261028/report.json` 的独立外层记录提供，不修改原始脚本生成的报告来改写历史。

## 最终状态与恢复

两板收发已停止，TX DDS raw/scale 八项均为零，RX buffer=0，所有控制连接释放。两板仍供电，未执行关机、重启、PL 热加载或持久固件修改。

TX boot `59212a7f-04d9-44b0-b9b7-ddb258aa15ff`，RX boot `5200d9b1-93d6-43c2-8f10-d1236fac60eb`。下一次演示需重新检查当前 boot/源包/本地网络绑定，新建 RX、背景及单音校准，再开放屏控。屏与两板 COM 编号按实物身份重识别，不硬编码套用。

完整三类人工验收父证据保留 `results/p81-active.json`。P82 仅为 TX2 只读库存，双 TX 尚未实现/启用；本轮不继续该开发。下一步按用户是否需要补录另外两类与 STOP、整理比赛交付或继续独立控制来安排，不能自动把尚未收到的视频称为已完成提交。
