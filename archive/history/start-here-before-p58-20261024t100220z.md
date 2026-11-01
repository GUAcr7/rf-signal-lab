# 从这里恢复项目工作

**最新：新板已正常关机，确认 System halted，等待用户仅对新板真正断电约10秒再上电。旧板未关机。**

先读 results/p57-active.json 及其 poweroff_record；原检查点已核验，P57 AI 开机配置仍启用。下方“尚未关机”是此前历史。上电后先认新 boot 与开机日志，不先 reboot 或热加载；应先看到等待校准，不能沿用旧 IF/令牌。

2026-10-24：passed_P57_persistent_AI_warm_boot_calibration_RF_LCD_cold_pending。

先读 [恢复清单](docs/handoff/resume-p57-20261024.md)、[实验记录](docs/experiments/exp-p57-boot-ai-20261024.md)、results/p57-active.json。权威字段：TX-SOURCE-STATUS.json 的 p57_current。

AI 已加入独立的开机配置；两次普通重启通过，第二次本次校准/三类RF/像素复核通过。真正断电项仍待用户动作及新启动证据。收发已停止、串口关闭、P57 下次开机选择启用；此时尚未关机，若后续有 halt 记录应以新状态为准。

15 分钟默认有时限接收，不自动发射。开机先等待本次校准；不复用旧 boot 身份或 IF。results/ 被 Git 忽略，直接读文件系统。

检查点：`results/p57-checkpoint-20261024T095114718202Z/report.json`。
