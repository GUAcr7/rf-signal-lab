# HW-035：修复防休眠后的受控断电验证

日期：2026-10-22（北京时间）。阶段进行中，尚未判定断电验收通过。父阶段P44已经验证一次软件重启、741秒/1451次更新，以及用户十分钟后实体显示仍动态可见；本轮补真正断电后自动显示的验收。

## 接手时状态与保存

本次只读识别发现新板已是新boot `5b1bb2a2-c427-47e3-b79a-972c2768d792`，P43持久wrapper和全部安装文件SHA匹配，RX running，buffer1、scan1100，pending/disabled均无、taint0。证据`results/p43-status-20261022T102023Z/report.json`。没有证据说明它如何重新启动，因此明确记为`existing_new_boot_power_cycle_not_verified`，不冒充人工断电验收。

通过启动日志的同boot、空绑定、单次PL/overlay、首次READY标记固定本轮身份，观察进度继续推进后受控停止。实际运行378.698秒、更新742次，资源释放、RF参数不变、taint0；`results/p43-observed-cycle-20261022T102406Z/report.json`。最后显示32KiB原始前缀及显存回传、独立NumPy复核`results/p42-review-20261022T102459Z/report.json`全部通过。本轮没有把未记录到的启动方式硬归为软件重启或冷启动，也没有宣称该短观察通过十分钟显示验收。

同一套已固定SHA的持久配置已重新选择，`results/p43-enabled-20261022T102622Z/report.json`。主机工具新增“仅观察既有新boot”的独立证据类型，保留人工事件+被动启动UART才可标记受控冷启动的原要求；新增/相关18项门禁测试通过，`results/p45-preparation-tests-20261022.xml`。

## 接下来的验收

先校验保存包与当前新板idle/配置SHA，再正常关机，看到System halted后请用户真正断开新板电源约10秒再接电；旧P201不动。由单个COM8 owner被动记录启动，随后只读识别新的boot与READY。板端接收持续运行超过660秒，用户确认实体屏仍亮且更新，再受控停止并回传IQ/显存、复核时钟与防休眠策略。任何未观察到的步骤保留待验收，不以主机发重启冒充真正断电。

本轮不修改FPGA、设备树或原生接收算法，不热卸ADC/RF/PWM/显示驱动，不在已绑定时重配PL，不启用旧板TX。厂家0xFF根因、实板故障回退、CDC/外部IO时序、ADC连续性、已知源质量及真实AI仍为独立开放项。

## 被动启动捕获的提示符解析修正

受控断电后的被动记录`results/p43-passive-power-on-20261022T103437Z/report.json`捕获18413字符、新内核和P43首次READY，UART发送0字节；原记录root_prompt_observed/startup_ready_observed=False。原始console实际上含自动登录的root提示符，但其前面有VT保存/定位转义，旧正则未识别，因此监听等满600秒；不是板卡未启动。保留原报告不改写，修正后先去掉ANSI控制序列再识别提示符，真实序列回归在4项用例中通过`results/p45-ansi-prompt-tests-20261022.xml`。冷启动归类继续要求用户事件、零发送被动新内核/READY及同一boot，不依赖这个原错误提示符字段。

## 断电准备保存

新板正常关机已确认System halted，记录`results/p45-power-cycle-prepare-20261022T102927Z/report.json`。首个180秒被动记录窗口`results/p43-passive-power-on-20261022T103021Z/report.json`发送0字节、收到0字符；尚无用户电源操作回复，因此这仅表示没有捕获到重新上电，不是启动失败或冷启动通过。主机未重新起流、重启或热装驱动。原始数据已归档，新增相关25项门禁通过`results/p45-final-host-gates-20261022.xml`。当前等待用户只将新板断电约10秒再接电，旧板不动。

## 受控真断电后的结果（本节覆盖前述“进行中”）

正常关机与保存记录见被动捕获报告所引用的poweroff_report。用户直接回复“新板已断电并重新上电”；断电间隔由用户执行，未由仪器测量。被动启动UART记录`results/p43-passive-power-on-20261022T103437Z/report.json`，发送字节0，捕获新内核及P43首次READY，随后实际boot `343afe82-88e6-4a03-a5d4-c09ee6929e36`；主机没有发重启、装PL或启动接收命令。

板端自动接收并绘图，运行724.465秒、更新1419次、RSS高水位2632KiB后受控停止，资源释放、RF参数不变、taint0。主试验`results/p43-cold-cycle-20261022T104726Z/report.json`；原始IQ/显存完整回传、最后显示前缀独立数值核对`results/p42-review-20261022T105059Z/report.json`；受控冷启动同boot时钟寄存器/驱动率验收`results/p43-cold-clock-20261022T105246Z/report.json`。

超过600秒后防休眠策略回读`results/p44-verified-20261022T105257Z/report.json`确认P44文件SHA和选用入口不变、consoleblank0、无Xorg/xinit、PWM2仍enabled；**实体屏超过600秒仍亮且持续更新的用户确认=True**，本字段False时不能把机器证据写成实体显示通过。

持久wrapper已重新启用：`results/p43-enabled-20261022T105320Z/report.json`；最终只读`results/p43-status-20261022T105408Z/report.json`确认RX idle、buffer/scan0、没有pending/disabled，串口关闭。当前板卡仍通电，未再次关机。恢复入口为P45，保存包`results/p45-checkpoint-20261022T105431296545Z/report.json`。本轮没有启动旧P201发射。

结论仅覆盖这一次受控真断电及十分钟以上自动RX/频谱显示。厂家偶发0xFF根因、实际故障回退、更多冷启动与长稳、CDC/外部IO时序、物理PCLK、无损连续性、已知源质量和真实AI未据此关闭。
