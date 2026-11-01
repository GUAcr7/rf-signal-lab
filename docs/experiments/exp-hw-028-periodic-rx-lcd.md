# HW-028：板端周期采集与频谱更新

日期：2026-10-21。用户要求继续推进，延续P37固定安全时钟配置；本轮不重启、不重配PL、不改RF属性、不启动TX、不改启动文件。

## 结论及验收范围

从冻结历史IQ绘图推进到**板端自己重复接收新IQ、分析并更新帧缓冲**。8轮短测、64轮约66.54秒试验均完成；每轮完整保存一个返回缓冲，随后释放接收资源再绘图。最后一轮原始字节与屏幕回读数据已归档电脑，独立NumPy核对峰值、位置、RMS及频谱总功率通过。

这是周期快照监测，不是持续无缝采集。没有独立ADC计数器、overrun或连续时间轴证据，`continuous_RX=false`、`lossless_proven=false`；外部目标未知、功率未校准为dBm、无AI。64轮CPU写屏已验证，未另向用户确认本轮实体LCD动画或测量刷新率；P37人工实体可见性确认仍仅属于原先的静态画面。

## 重新认板与复用条件

`results/p32-preflight-20261021T093313Z/report.json`：新板COM8 boot=`92bd78be-43f1-48c0-b390-b6841cb82111`，taint0、RF_READY、guard匹配、RF模式、buffer/4个scan全0；旧板COM9 boot=`41a13b8a-9886-4eeb-b825-6e0023432788`，未观察到TX。沿用本boot的P37位流及 `results/p37-clock-accept-20261021T090640Z/report.json`，不把旧boot验收移用于其他启动。

## 实现与离线验证

- 新C程序 `embedded/arm_rx_panel_p38/arm_rx_panel_p38.c` 通过编译时包含复用P36完整返回缓冲接收器及P35数值/几何校验过的renderer，两个原始C文件未修改。一个有限进程内，每轮重建接收上下文，接收1×65,536帧/262,144原始字节，join并释放RX后，低12bit掩码和符号扩展，再分析该缓冲前8,192个连续帧、8个1024点FFT并写屏。
- UI显示`RX snapshot 当前/总数`、当前固定LO/Fs；结束改为`RX STOPPED | last snapshot`，失败/取消结束用停止标记。首轮采集失败前不覆盖旧画面。输出每轮独立IQ、原始元数据和RF前后读值，保留错误退出，不热重试。
- 参数最多64轮、间隔100..5000ms；C在轮次间限制90秒，单次接收沿用15秒取消和3.5秒join门槛。它不声称所有内核setup调用都有硬实时上界。板端执行器本轮只允许间隔100..1000ms；独立launcher在85秒发送TERM、22秒后必要时KILL；电脑每5秒只读进度，连接断开也不会无限循环。
- `results/p38-build-20261021T093743Z/report.json`：实际C mock回归12 passed，ARM32 little-endian/Cortex-A9/硬浮点/动态解释器和GLIBC兼容检查通过。原生bin46,700字节，SHA=`6dc2d4f79d9baab8711c30e7fde7b1df5b09bc3d6136a94ef7fa3019523368ef`。输入源码/头文件/fixture SHA均钉住。
- 模拟测试包含：三轮独立数据文件/NumPy数值核对，version/config/format/layout错误、真实信号处理器取消，非法轮次/间隔和已存在目录拒绝。`tests/test_p38_runner_gate.py`另外4 passed，证据 `results/p38-build-20261021T093743Z/all-runner-gates.xml`：fb console门槛、有限数据路径、同boot/已结束/已空闲的截图父证据门槛。

## 本轮实际板端结果

1. `results/p38-board-20261021T094240Z/report.json`：8轮、轮间请求250ms，总软件elapsed2.1941秒；全部采集/绘图记录通过，同boot/taint0，RF读值前后一致、buffer/scan全0。该次为前台有界短测试。
2. `results/p38-board-20261021T094451Z/report.json`：独立launcher下64轮、轮间请求1000ms，全部完成，总软件elapsed66.54094秒；64份不同raw SHA、64份完整单缓冲元数据和绘图记录。每轮65,536帧，64轮合计4,194,304帧/16MiB原始返回字节，分属不同接收会话，不能拼成连续ADC时间轴。原始报告保存每轮字段；未把相异SHA当作无丢样证据。
3. 64轮分析平均3.374ms（范围3.310..3.704ms）、CPU绘图平均2.991ms（2.920..3.871ms）；仅是对应计算段，不能作为实际LCD刷新FPS、接收吞吐或端到端延迟。最后一轮FFT bin偏移1、bin功率21.4658375 dB re 1 count²、RMS11.1955005872 counts；未知输入下不推断已知目标。
4. 两次实际试验后均独立读取同boot、taint0、RF属性未变、buffer0/scan全0、无竞争进程/关键内核异常，串口关闭。原厂启动保护及默认固件不改。

## 原始证据与独立复核

- 64轮电脑报告含全部元数据与SHA；64个完整raw文件位于板端RAM `/tmp/p35-p38-094451/data/cycle-000..063/iq-packed.bin`。本轮只将最后一轮raw完整回传电脑，其余63个仅板端RAM保存，断电会丢。短测8轮也仅RAM原始数据，不冒充全部电脑归档。
- `results/p38-last-archive-20261021T094725Z/report.json`：RX空闲后压缩最后一轮，源SHA前后匹配；压缩108,732字节，原始262,144字节。`results/p36-file-archive-20261021T094920Z/report.json`：4/4块、整包gzip CRC/压缩SHA/原始SHA全部通过，原始SHA=`9a80ddb29b692f09f41cd2819858f7bf9dc72b7c03fb6f200108fd2a34322266`。
- `results/p36-fb-snapshot-20261021T094959Z/report.json`：明确以本次64轮报告为父证据，在已结束且空闲后只读回读可见800×480/BGRA-or-BGRX；`results/p36-file-archive-20261021T095055Z/report.json`保存全部1,536,000原始可见字节。
- `results/p38-offline-review-20261021T095207Z/report.json`：电脑独立NumPy对最后缓冲前8,192帧核对。peak21.46583792945 dB、offset1、RMS11.19550058722、sum251.9533414264，与板端C输出在预先使用的容差内一致。生成的 `screen.png` 已查看，标题/64/64/频谱/数值/停止标记清楚。它是framebuffer回读图，不是实体照片。

## 失败与纠正，保留原件

- `results/p38-build-20261021T093639Z/report.json`：11 passed/1 failed，因沿用的P36取消fixture要到第4次refill才触发，而新monitor每会话只有1次。新增P38 fixture在第1次refill确实发SIGTERM并等待取消；不是删掉取消测试或把成功当失败。旧C接收器未改，随后12项通过。
- `results/p38-board-20261021T093942Z/report.json`：本执行器误把console名称的`(M)`前缀当后缀，保守门槛拒绝；未上传/采集。按实际逐console名称/绑定字段解析并补负例。
- `results/p38-board-20261021T094047Z/report.json`：使用`/tmp/p38-*`不满足已复用上传器的`/tmp/p35-*`白名单，被拒绝；只创建空RAM目录，未开始采集。改用独立`/tmp/p35-p38-*`，不放宽上传路径白名单。
- 首次回传P38最后缓冲，原P36回传器不认新增的cycle子目录，在参数解析阶段拒绝、未打开串口。新增精确的P38固定目录/000..063文件路径规则并补遍历、注入、越界负例；所有身份、源SHA、大小、idle及分块/gzip核验门槛保留。

## 交接与剩余工作

当前仍是原P37合并固件，屏幕保留本次64轮最后画面并明确标注已停止，接收应用和launcher均结束，串口关闭。临时程序/记录仅RAM，不改开机启动；普通重启仍恢复厂家RF路径，不能自动恢复合并显示。

下一步：受控重复启动/厂家0xFF定位；更长有界周期监测和取消/异常恢复；将周期监测推进为有明确定义丢帧策略的持续接收/最新帧显示，提供独立连续性证据；已知激励下解调/EVM质量；可回退的开机自动合并启动；真实AI。58项CDC、7输入/29输出外部延迟缺项、外部PCLK测量和长期稳定性仍未关闭。不得把本轮约一分钟试验当作全部挂死根因或整机验收通过。


## 停工归档补充（2026-10-21）

按用户要求保存全部工作，已将上文当时只在RAM的64轮及短测8轮原始数据完整归档电脑，逐轮SHA和偏移核验全部通过。原有“仅最后一轮归档”描述保留为当时状态；以[停工记录](../handoff/stop-p38-20261021.md)和p38_current为最新保存状态。未新增功能验收、未关机。
64轮归档：`C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab\results\p36-file-archive-20261021T100701Z\report.json`；8轮归档：`C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab\results\p36-file-archive-20261021T102329Z\report.json`。清单：`C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab\results\p38-stop-20261021T102648Z\cycles-64.json`及`C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab\results\p38-stop-20261021T102648Z\cycles-8.json`。
16MiB数据首次gzip回读超过30秒，失败原件保留；随后独立确认gzip已结束、CRC/压缩与原始SHA及64个源文件一致，再完整回传核验。不是重新采样或修改原始记录。
