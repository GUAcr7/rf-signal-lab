# HW-033：持久开机自启动、受控停止与回退候选

**最终结论：两次软件重启及一次用户真实断电后的板端自动启动均通过，持久wrapper已再次启用。当前RX停止/idle、串口关闭，未再次关机。一次成功不代表0xFF根因关闭；以下先记录软件重启阶段，文末记录真实断电证据。**

日期：2026-10-22（北京时间）。P42十分钟程序为父版本，本轮没有更换原生C/FPGA设计，只开发开机选择、首次就绪判断、控制和验收工具。

## 已验收及边界

**同一套持久启动文件经过两次真实软件重启，均由板端在登录前自行初始化合并硬件并启动P42接收/频谱显示；主机登录后只观察、发送受控停止及做归档。** 两轮都核验buffer/scan0、taint0、RF参数一致，原始最后显示前缀与framebuffer回传完整，同boot时钟后验和独立NumPy复核通过。

- 第1轮：boot `df6afb6e-c22e-48d1-8083-d7e5b95c9f22`，运行37.128秒，更新73次，收到信号正常停止，RSS高水位2572KiB；`results/p43-boot-cycle-20261022T030856Z/report.json`，复核`results/p42-review-20261022T031116Z/report.json`。
- 第2轮：boot `5f5d0e65-8da2-4fc2-842d-848978da0b3d`，运行37.142秒，更新73次，收到信号正常停止，RSS高水位2592KiB；`results/p43-boot-cycle-20261022T031333Z/report.json`，复核`results/p42-review-20261022T031538Z/report.json`。

以上两轮是软件重启；后续一次人工断电验证见文末，不混算。归档工具仍校验原guard，因此主机在每轮应用停止且独立idle确认后临时恢复原S99board；归档完成后再次原样装入同一wrapper。**不是两次启动之间完全没有主机改文件**，也没有把主机停止命令冒充脱离电脑整机验收。程序启动确实发生在板端，完整UART有登录前marker；本轮未再次取得实体屏幕动态人工确认。最终回读图已查看，标题/曲线及上下RX STOPPED BY REQUEST可读；回读不等于实物照片。

## 当前持久状态（最后实读）

- 启用报告：`results/p43-enabled-20261022T033907Z/report.json`；独立只读状态：`results/p43-status-20261022T034008Z/report.json`。当前boot `f65eb741-88fc-44c1-9cb7-8fced08ac86a`。
- `/etc/rcS.d/S99board`现为P43 wrapper，SHA `4aa3538e7596fad8598e27ac4f876798a080d34c13b5013aab2435b274e265af`；原始guard在`/etc/p43-20261022T030856Z/original`，SHA `89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2`。没有改仓库原S99board参考文件。
- 安装目录`/etc/p43-20261022T030856Z`含original、monitor、bringup、control、run、boot；哈希在启用报告固定。最终重新启用后没有再重启，当前RX空闲、串口关闭、板卡仍通电；屏幕保留最后快照。**下次新启动会尝试自动初始化及显示，已不再是下方历史P42的“普通重启只走RF-only”。**
- 原生duration=0直到请求停止，外层有86400秒（24小时）终止后备；达到后备期限会停止。不能说已经验证24小时运行，也不能叫任意时长不间断。P42十分钟验收仍作为原生程序的较长实板证据。
- 默认固件/原厂DTBO/BOOT/base DTB未替换，board-mode仍rf；不启动TX、不热卸载ADC/PWM/显示、不在现有驱动下重配PL。新启动只允许一次PL和一次显式overlay。

## 实现与失败路径

1. `p43-persistent-guard.sh.in`先校验original，诊断`--check-rf`只转发只读路径。start验证新boot、/run tmpfs和本boot未尝试marker；相同boot再start会拒绝。选择合并配置前留持久pending目录并sync。
2. `p43_boot_templates.py`严格替换保留P41原有fresh/empty、唯一RF名字、idle、bin/DTBO/hash、软件33MHz时钟和RF参数门槛；source变化无法静默套用。没有删原来的安全门槛。P43不要求已安装S99恢复原guard，而是核验独立original备份，installed wrapper由主机另行SHA固定。
3. monitor与launcher复制到已确认的/run tmpfs，使用固定且本boot必须不存在的`/run/p42-000043`。UI/进度/日志仍由P42控制；只在出现首次running进度后才清pending并sync，意味着确实发生过首次分析/写屏，不是只有进程PID。
4. 如果初始化没到首次进度，pending保留；**下一个新boot**见pending会持久disabled并执行原厂guard，不在失败的同boot里移除overlay或重装PL。disabled也先经本boot重复执行门槛，不能拿它绕过热重配保护。此自动回退已做隔离shell测试，**尚未在实板故意制造失败再验证回退**。哈希损坏等更早失败会直接停止，需要显式恢复，不能声称任何故障都能自愈。
5. `control stop`要求marker为当前boot、PID合法且/proc命令行首项timeout、精确monitor路径匹配，才向它发SIGTERM；随后有界等待退出。主机还必须检查native summary、RF/内核与idle，不凭exit文件单独宣布资源释放。停止命令不卸驱动、不改RF参数。

## 证据与纠错

- `results/p43-preparation-20261022T030536Z/report.json`：13项真实POSIX shell在隔离目录执行，源哈希与输入快照固定，4份生成脚本sh -n通过。包含首次UI后清pending、wrapper持续保留、拒绝PID1并实际SIGTERM停止、旧boot/错hash/已有RF或overlay/非RAM/重复start拒绝、pending/disabled选择factory、probe失败/无首帧不重试。
- 第一轮fixture 5失败/8通过：/run挂载检查的路径常量在测试副本没有映射到临时根目录，错误地拦下了正常场景。失败XML及原test源保留为`results/p43-shell-attempt1-20261022.xml`与`results/p43-shell-attempt1-source.py`；仅修测试路径映射，真实脚本仍要求/run tmpfs。后续preparation增加实际停止/PID拒绝检查并13项通过，不使用早期通过XML代替最终固定源码结果。
- 每轮result目录含完整原始UART、startup-log、program最后两项JSON、精确installed文件和executed.py。hardware-trial.json只是对应新boot初始化依据，时钟LOCK/寄存器仍由独立脚本实读；不能当物理PCLK已测。
- 两轮最后显示32KiB原始IQ均已电脑归档，非整段无损录制。UI覆盖不等于ADC丢样；输入未知、数字功率不是dBm、近DC峰不代表已知目标，没有接入真实AI。

## 下一步

本轮已做一次用户真正断电再接电，详情见下节。继续积累冷启动成功/失败对照、实板故障回退、更长运行及已知源/AI联调；仍保留CDC、外部时序、ADC连续性等开放项，0xFF根因未关闭。

## 后续真实断电验证（本节覆盖上文“冷启动待做”）

用户按关机后断电约10秒再接电的要求回复“新板已断电并重新上电”；间隔未由电脑仪器测量。关机记录`results/p43-power-cycle-prepare-20261022T032530Z/report.json`确认System halted；用户事件`results/p43-human-power-cycle-20261022.json`。被动UART `results/p43-passive-power-on-20261022T032808Z/report.json`收到新内核及P43就绪marker，发送UART字节0；原始console中自登录root shell已出现，旧捕获器仅识别行尾login，所以login_observed=false不代表未启动，原报告不改写。

冷启动boot `f65eb741-88fc-44c1-9cb7-8fced08ac86a`，主机未重启/装PL/起应用。自动运行331.939秒，更新650次后受控停止。`results/p43-cold-cycle-20261022T033344Z/report.json`保留实际计数和操作；时钟寄存器/软件率一致`results/p43-cold-clock-20261022T033710Z/report.json`，原始前缀/显存完整归档及NumPy复核`results/p42-review-20261022T033710Z/report.json`。本次冷启动未出现0xFF、taint0，停止后资源释放；**一次成功不能证明0xFF根因已根治**，也不替代更多冷启动或实板故障回退演练。当前最终wrapper再次启用，RX idle、串口关闭、未再次关机。上文等待断电/旧boot均为历史；当前以本节与p43_current为准。实体动态人工确认另行记录，本记录不凭显存回读冒充实物观察。

## 用户实体屏幕反馈纠正（P44开始）

用户回答冷启动显示检查为“黑屏或画面异常”，进一步明确“屏幕完全黑，没有明显背光”。因此本次实体屏幕显示不通过，整机冷启动验收撤回至待修复；板端自动RX、显存写入/回读、时钟检查仅在各自范围成立，不能推导物理屏正常。原始机器记录及旧检查点保留，当前状态以START-HERE、TX-SOURCE-STATUS.json及后续P44为准。用户观察时刻相对运行/停止未测量。
