# P85 重新接线后的演示恢复（2026-10-28）

用户要求：两板已经通电，恢复小屏操控的真实射频功能演示。沿用已确认的旧 P201 TX1 → 原衰减连接 → 新板 RX1A，不启用 TX2，不接频谱仪。

## 初始故障与修复

- 固定入口 `results/p59-status-20261028T132827527961Z/report.json` 在认板前拒绝：原来绑定的新板 USB 位置 `1-9` 已变化。不是据此认定板卡损坏。
- 实际枚举为旧板 PlutoSDR COM5 / `1-9.1:x.3`，CH340 COM9 / `1-4` 与 COM11 / `1-9.3:x.3`。不按串口号码或猜测区分后两个设备。
- 新增 `experiments/p85_topology_preflight.py`：逐个 CH340 仅查询 TJC `connect`；必须唯一匹配已验收的完整型号、序列号、Flash。剩余候选再经过原控制器的 Linux 身份、完整射频状态和持久接收配置 SHA 核对。未改变 RF/PL/启动固件。
- 实测 `results/p59-p78-screen-preflight-20261028T133432201529Z/report.json` 通过：新板 COM9、小屏 COM11。原电脑绑定配置已备份在该结果目录 `board-connections.before.json`，仅在检查全部成功后更新电脑的 USB 位置与证据 SHA。
- 旧板 boot `5b50bfb2-9570-453a-a078-358d9c49c9d1`；新板 boot `d28f72a7-99d3-4b1d-b7e7-42413272fcfd`。新板自主接收在运行；旧板 TX 缓冲关闭、DDS scale 全零，raw 为启动默认值 1，下一步先固定零源再恢复源包。

## 前轮数据边界

两板 boot 均与 P84 不同。P84 主机按键、任务日志及实屏照片已经保存，但上轮完整 RX 归档因旧板 USB 缺失未完成，板内 RAM 历史现在不可恢复。不得把这轮新数据补作上轮证据，不修改 P81/P83 冻结验收。

## 本轮执行与待验收

按固定顺序：零源 → 恢复并核 SHA 的 RAM 源包 → 同 USB 网络身份绑定 → 新接收会话/背景 → 限时单音参考 → 实屏人工控制。每步须通过才进入下一步。逐步原始报告保存在 `results/`，不将“已就绪”写成三类/STOP 验收完成。

人工演示目标：BPSK、QPSK、16QAM 各一次完整自然结束，另一次在 RUNNING 中实际按 STOP；按原始按键、原生停止回执和接收历史确认实际覆盖。服务结束后归档完整 RX，实际覆盖不足则如实记录。

## 本轮已就绪（UTC 13:40）

- 零源通过：`results/p59-source-off-20261028T133542693350Z/report.json`。
- 源包恢复与 SHA 通过：`results/p59-prepare-source-20261028T133631789254Z/report.json`。
- 串口与 USB 网络同板同 boot 绑定通过：`results/p59-p79-bind-USB-network-20261028T133722436379Z/report.json`。
- 新接收会话和背景通过：`results/p79-prepare-session-20261028T133756Z/report.json`。
- 15 秒参考单音、自然到时零源及校准就绪通过：`results/p79-cancel-trial-20261028T133931Z/report.json`，内层 `results/p59-p80-panel-run-20261028T133931823318Z/report.json`。
- 人工服务已输出实际 READY：`results/p80-screen-control-20261028T134008Z/report.json`，运行会话 `49982`，720 秒窗口，默认每次发射 15 秒。不得并发认板/串口控制任务。
- 当前属于“已准备，等待人工”，三类切换、动态显示和 STOP 尚需本轮按键与接收数据确认。服务完成或到时后须继续归档，不以已就绪代替本轮验收。
