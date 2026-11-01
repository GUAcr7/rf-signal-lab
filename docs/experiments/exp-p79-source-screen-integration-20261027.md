# P78 P79 串口屏与旧板信号源联调

日期 2026-10-27。本轮正在进行，不能当作全部屏控射频验收通过。两板原射频同轴及衰减连接由用户确认保持不变；淘晶驰屏只通过 USB-TTL 接电脑，未接 J19。本轮采用电脑中转方案，旧板独立串口和脱离电脑控制仍未验收。

## 已取得的实证

队友交付的两份 Word 原件及提取文本已保存在 `results/p59-p78-screen-preflight-20261027T121300659488Z/`。原件是外部交接证据，未把其操作建议自动当作本项目已完成结论；本地尚未收到可编辑 HMI 和 TFT 文件。

实屏握手型号 TJC4827T143_011C、序列号 D1273501630AD655、8 MB Flash、115200 波特率、page0、t1/t2/t4 读回与交付记录一致。新板和屏幕同为 CH340，原来要求唯一 CH340 的发现逻辑会拒绝连接。新增按已核验 USB 位置选择 RX 候选的可选绑定，并保留实际 Linux 身份和配置 SHA 检查。当前 COM8 为 RX、COM10 为旧板、COM6 为屏，编号不作为设备身份。

真实手指按钮回包累计覆盖 ID 1 至 9，全部只处理 page0 弹起事件。第一轮实屏测试的长状态 `CHECKED NO RF` 被截为 `CHECKED NO`，严格读回检查拒绝了该次测试。改用 APPLIED、NO RF TEST 等短状态后，APPLY、START、STOP 的回显复测通过，用户也确认三个状态正确。保留失败原始记录，不用最终通过覆盖它。

主要证据：

- `results/p59-p78-screen-preflight-20261027T121300659488Z/report.json`
- `results/p59-status-20261027T121508749054Z/report.json`
- `results/p78-screen-link-20261027T121704Z/report.json`：四类选择和加减实际回包；长文字读回失败。
- `results/p78-screen-link-20261027T122101Z/report.json`：APPLY/START/STOP 短文字与回读通过。
- `results/p79-detached-tests-20261027.xml`：102 项相关 Python 检查通过。
- `results/p79-supervisor-mock-20261027T123800Z/report.json`：实际 Linux 子进程和回执测试，使用假 guard，无射频。

## 真实停止试验与兼容问题

旧板当前 boot 为 `944506cc-3982-42c0-ba95-85f32ae16cb7`。波形源重新恢复到本次 RAM，逐项核验 SHA，PHY 配置和冻结接收 AI 未改。第一次 8 秒单音在原生提交后约 2 秒收到停止请求；原生记录显示 `elapsed_seconds=2.1663258 stop_signal=1`，DDS_ZERO_SOURCE_READBACK=PASS、TX_CLEANUP status=0。随后 USB 交互登录会话退出，原程序未取得 wait 回执，因此这次端到端任务仍记为失败。重新登录后，在同一 boot 取回原生日志，独立核对 TX buffer=0、DDS 全零、taint=0。没有把恢复证据改写进原失败报告。

证据为 `results/p79-cancel-trial-20261027T122845Z/report.json`、`results/p59-p79-panel-run-20261027T122845769091Z/report.json` 和 `results/p59-p79-stop-recovery-20261027T123156955521Z/report.json`。

第二次尝试隔离 shell 任务时，旧板 `setsid` 无法把内置 applet `timeout` 当作独立程序执行，原生发射未启动。错误日志为 `setsid: can't execute 'timeout': No such file or directory`。空 native.log/receipt 已独立检查。报告 `results/p59-p79-panel-run-20261027T124050088131Z/report.json` 和 `results/p59-p79-detached-failure-read-20261027T124250446765Z/report.json` 保留。

进一步使用完全不发射的 sleep 后台进程也复现 USB 控制台退回登录界面，见 `results/p59-p79-console-child-check-20261027T124558586549Z/report.json`。这支持定位到交互控制通道的后台任务兼容问题，不能声称已找到内核或硬件根因。

## 当前解决路径与验收门槛

改用旧板同一根 USB 的现有网络接口，通过非交互 SSH 控制任务。先从原 USB 串口读取本次型号、boot 和 usb0 地址，再要求网络返回同型号同 boot，并固定 SSH 公钥指纹；绑定失败或 board 重启则拒绝发射。原 `board_control.py` 的日常串口入口保持不变，屏控任务使用明确独立的网络入口，无静默切换。

`board/source-job.sh` 仅上传 RAM，隔离启动原封不动的已核验 guard；子进程由本地 supervisor 创建和等待，停止请求使用本次唯一目录中的 stop 文件；回执包含 boot、nonce、信号、时长、原生子进程及 reaped/退出码。必须同时取得原生清理日志、严格绑定的回执和最终 IIO/DDS 空闲，才报告停止完成。最终版本通过 `/bin/busybox setsid` 显式隔离，**旧板 BusyBox --list 没有外部 timeout applet**；不依赖不存在的外层 timeout，继续使用原 guard 已验证的单调时钟/watchdog/alarm 期限。主机对等待回执也有期限，超时只能记未确认，不能当作停止成功。

后续依次完成：网络同板绑定及无射频后台测试 → 新接收会话及新背景 → 单音的主动停止和到时结束 → 真正手指控制三类的 APPLY/START/STOP → 完整接收历史核对和收发清理 → 保存恢复记录与检查点。

本文件为过程记录，后续完成结论另在末尾追加，并以最新恢复入口为准。

## USB 网络路径的实测进展

`results/p59-p79-bind-USB-network-20261027T125033129957Z/report.json` 已核对 USB 串口与 192.168.2.1 网络返回同一 P201 型号、同一 boot，并保存 SSH 公钥指纹。原默认串口入口未切换。`results/p59-p79-network-child-check-20261027T125249929626Z/report.json` 通过相同非交互父 shell 下的后台启动、主动终止和原生 wait；没有射频操作，父 shell 身份不变。

最终隔离程序已通过真实停止复测 `results/p79-cancel-trial-20261027T125748Z/report.json`，其子任务 `results/p59-p79-panel-run-20261027T125748574529Z/report.json` 同时证明本次 nonce/boot/child 的有效回执、stop_seen/signal_sent、exit_code=0、child_reaped、原生清理和 DDS 空闲。此次经显式 USB 网络完成，未发生控制台会话中断。

新背景后，15 秒单音到时结束也通过 `results/p79-cancel-trial-20261027T130006Z/report.json` 和 `results/p59-p79-panel-run-20261027T130006562700Z/report.json`；回执无停止请求、退出及清理正常，新板校准 ready。前述两次失败和一次缺少 applet 的拒绝报告均原样保留。

真实手指三类发射及 STOP 联调已开启于 `results/p79-screen-control-20261027T130156Z/report.json`。在本段记录时尚在等待/收集操作，不将这条过程状态当作全部验收完成。相关 Python 检查增加到 106 项，通过记录 `results/p79-network-tests-20261027.xml`；新增网络依赖的安装记录和固定版本分别保存于 `results/p79-paramiko-install-20261027.json`、`requirements-screen-control.txt`。

## 本轮收尾结论

自动协议回归、原生停止/到时清理、完整接收历史和同源 FFT/实显存已通过独立复核：bpsk 16/16 稳定更新接受正确；qpsk 16/16 稳定更新接受正确；qam16 16/16 稳定更新接受正确。本轮不是新的独立 AI 准确率。

人工阶段在 `results/p79-screen-control-20261027T130156Z/report.json` 保存为 partial：BPSK 实发到时完成；后来的 QPSK 操作碰到 420 秒会话截止，故不能把用户反馈转写为已抓到人工 STOP。该阶段完整 RX 已归档 `results/p59-p79-session-archive-20261027T131158174564Z/report.json`。

官方 click 指令已查证并实测，本 HMI 使用 click 不自动回传勾选的键值，记录 `results/p78-screen-link-20261027T131403Z/report.json`。随后无 RF 的 printh 帧回放通过 `results/p78-screen-link-20261027T131729Z/report.json`，自动收发回归明确标为 screen_generated_protocol_replay。没有修改 HMI，也没有把协议回放称为真实手指测试。

自动回归：`results\p79-screen-control-20261027T132221Z\report.json`；完整数据：`results/p59-p79-session-archive-20261027T132602604111Z/report.json`；独立复核：`results/p79-review-20261027T132842Z/report.json`。相关 Python 测试 107 项通过。收尾时两板仍供电，收发停、DDS 零源、所有控制连接释放。最终检查点：`results/p79-final-20261027T133028Z/checkpoint.zip`。
