# 从这里恢复项目工作

**P50新版真断电启动观察进行中，接收仍运行。** 当前boot a5313ffa-483a-4f9e-b0a4-dbe9a22234fc；先读results/p50-watch-20261023T132702Z/report.json及results/p50-active.json。COM8由观察工具独占。下方已关机/idle描述均为此前历史，不能重放。


**最新状态：新板已正常关机，等待人工真正断电再上电做P50冷启动验证。** 记录`results/p50-power-cycle-prepare-20261023T132211Z/report.json`已确认System halted；旧P201板未操作。P43持久wrapper及P44显示策略仍启用，最后boot只是停机前历史。接电后先按当前恢复说明只读认板/新boot/首次进度；不先重启、不热重装。下方“板仍通电/未关机”是此前历史状态。

**当前入口：P49（2026-10-23）P48显示已迁移为默认自启动，两个软件重启验收通过。** 先读[实验记录](docs/experiments/exp-p49-persistent-units.md)、[恢复清单](docs/handoff/resume-p49-20261023.md)、TX-SOURCE-STATUS.json的p49_current。

完整profile `/etc/p43-20261023T130008Z`；旧P42目录未覆盖。两次启动分别独立核对时钟、原始I/Q、显存和kHz/MS/s单位。用户确认新版实体屏幕内容正常。**新版真正断电及动态画面十分钟验收仍待完成**。

最后boot `1d26653d-8f3e-4d51-a8a1-3e4d59fd0bc6`，RX idle、资源释放、串口关闭、无pending/disabled，P48 wrapper重新选中。板仍通电，未执行关机。再次工作先认板/读boot与进程，不重放旧身份。

回归首次93项中92通过、1项主机时序断言失败，单独复测通过；两份原始XML均保留，不称首次全绿。历史0xFF/质量波动根因、长稳、连续性与独立真实AI仍开放。

P47离线学习包入口仍是run-rf-learning-demo.cmd。本轮检查点：`results/p49-checkpoint-20261023T131143646042Z/report.json`；results不在Git，直接读取。
