# 固定电脑控制入口（P59）

2026-10-25 P65更新：当前默认连接已按用户选择改为USB串口（本机COM10），先按USB标识再核验P201 Linux与型号，不写死端口编号。见[连接配置](../configs/board-connections.json)及[P65实验](experiments/exp-p65-com10-control-20261025.md)。COM9无需作为Linux软件调试前提；这不等同硬件JTAG验证。旧FTDI连接可用`--tx-transport ftdi`单次选择，USB可显式用`--tx-transport usb-console`，缺少所选设备时不会静默切换。

USB串口模式的`prepare-source`直接经已核验的Linux终端传输到RAM并核SHA，无需配置电脑网卡地址；FTDI模式保留原HTTP传输。自然到时结束也须原生清理证明、DMA/扫描归零及本次AI状态一致才视为干净停止。

2026-10-25已完成当前双板上的短流程实测。入口为项目根目录`run-board-control.cmd`，实现位于`host/board_control.py`。它是电脑端调试/演示入口，旧板触摸屏控制仍待接入。

## 日常使用

双击`run-board-control.cmd`进入状态、接收启停、数字零源、波形恢复和背景校准菜单。所有命令从项目根目录执行，每次都会生成独立的`results/p59-*`报告和串口原始日志。

| 命令 | 实际作用 |
|---|---|
| `run-board-control.cmd status` | 根据USB身份查找两块板，再读Linux身份、boot、RF、DMA、程序和校准状态 |
| `run-board-control.cmd stop` | 停止经身份核对的当前接收会话；已经干净停止时重复调用不会重启 |
| `run-board-control.cmd source-off` | TX空闲且DDS各scale为0时，将DDS raw归零并读回；不是绝对射频静默证明 |
| `run-board-control.cmd prepare-source` | 通过既有USB网络恢复冻结的256峰值源包至旧板RAM，核验每个文件及板端guard；不会发射 |
| `run-board-control.cmd start` | 沿用当前运行会话，或在干净停止后保留旧RAM目录并新建一次RX；新会话清除旧校准 |
| `run-board-control.cmd calibrate` | 确认旧板源关闭后，用新令牌采背景，进入WAIT_PILOT；该命令本身尚未完成单音校准 |

完整短流程使用：

```cmd
run-board-control.cmd demo --rf-link-reviewed
```

`--rf-link-reviewed`只用于已经核对的旧P201 TX1→新板RX1A有线链路。接入新功分器/频谱仪或更换连接后，先按新接法核对端口和两支路电平，再使用该参数。

流程依次执行：停止旧RX→数字零源→恢复并校验波形→新RX→新背景校准→15秒参考单音→BPSK/QPSK/16QAM各12秒→停止并确认收发空闲。它是短时部署回归，不能当作新增十分钟验收或新的独立AI成绩。

分步发送命令：

```cmd
run-board-control.cmd send --signal tone --seconds 15 --rf-link-reviewed
run-board-control.cmd send --signal bpsk --seconds 12 --rf-link-reviewed
run-board-control.cmd send --signal qpsk --seconds 12 --rf-link-reviewed
run-board-control.cmd send --signal qam16 --seconds 12 --rf-link-reviewed
```

发送前必须完成当前boot的源包恢复、当前RX会话的背景/单音校准。单音要求WAIT_PILOT状态；调制波形要求校准ready。单音为5～60秒，调制波形为8～60秒（需留出稳定评分窗口），沿用现有板端guard，不提供无限时发送。

## 状态与恢复

- `RUNNING`代表当前boot、所属timeout进程、DMA以及实际进度都一致。保留的ai.json或exit文件不会被当成正在接收。
- `STOPPED`还要求DMA及四路scan都为0、退出正常、AI结果已清除。状态不一致会拒绝重新开始，不盲目杀进程或复位。
- `start`保留之前的整个RAM会话目录为`/run/p59-prior-时间戳`，不删除旧数据。每次新RX使用原P56已验收二进制，默认最多15分钟，并要求新校准。
- 旧板RAM源包缓存绑定本次boot和源报告哈希。重新上电后重新运行`prepare-source`；完整`demo`已经包括这一步。
- 完整流程遇到错误会保存失败报告，并尝试通过已核对的控制入口停止接收；板端发射自身仍有期限。出现未确认状态时先读失败报告，不同时启动旧实验脚本。
- 新入口在电脑上有互斥锁；原实验脚本不认识该锁，使用入口期间不要启动其他占串口的任务或SecureCRT会话。

## 当前适用范围

支持当前已验证的源包：Fs30.72MS/s、Rs240ksym/s、数字偏移+960kHz、峰值分量256、TX gain -10dB、LO2450MHz、TX1；新板RX为手动0dB及原18MHz配置。当前入口只核对PHY参数，不任意改频率、增益或采样率。

新入口不重启、不加载PL、不卸载驱动、不修改持久启动文件；RX重新开始只启动同一已验收程序。已确认的P57下次开机配置仍保留。本轮重新开始属于主机发起的新会话，不能冒称新的冷启动测试。

目前还依赖电脑及既有P58冻结配置文件。脱离电脑操作、触屏参数设置、旧板文件持久化和板间控制通道是后续W1工作。

## 证据

- [本轮实验记录](experiments/exp-p59-fixed-control-20261025.md)。
- [完整短流程](../results/p59-demo-20261025t025236599641z/report.json)。
- [完整判别日志及字节归档复核](../results/p59-archive-20261025t025904857628z/report.json)。
- [最新恢复说明](handoff/resume-p59-20261025.md)。
