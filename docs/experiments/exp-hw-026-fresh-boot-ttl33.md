# HW-026：P36 新启动 TTL33 射频与屏幕合并验证

- 日期：2026-10-21。用户确认已通电接线并要求继续解决问题。
- 本文随实际实验补充；仅下列已指向原始报告的结果有效，准备好的工具不算上板通过。

## 初始身份与本轮改正

本次重新认板见 `results/p32-preflight-20261021T025331Z/report.json`；新板 COM8 boot 为 `3e2ecb94-6929-4744-9d00-5e5f888f56c7`，RF 模式、taint0、缓冲与四路 scan 空闲。旧板 COM9 boot 为 `2c426d12-c7e3-4d41-9bb6-8a08b6b87e3d`，未观察到发射程序。

固件回读见 `results/p35-firmware-readback-20261021T025626Z/report.json`。发现 P35 一次试验脚本对派生文件 `system_wrapper.bin` 的门槛过严：正常 RF 启动会将它替换成厂家 `ad9361.bin`。本轮修正仅允许两个已知厂家哈希（RF 或原始显示 wrapper），固定固件/DTBO 哈希门槛不变，逐次保存派生文件角色；不能允许任意实验位流。

PL 传输改用 gzip 封套，1,037,112 字节而非原始 5,709,252 字节。板端先校验压缩包，再解压并核验原始 native bin 的 SHA256，FPGA 仍只加载原生裸 bin。主机配对输入、gzip roundtrip 和恢复顺序审查见 [P36 只读审查](p36-boot-trial-readonly-review.md)。

修改旧取消测试的报告范围描述为“当前已识别启动”；它可以用于合并 PL，不能仍把实际合并测试标作厂家 RF PL。该工具不独立证明 PL 身份，需关联父试验报告。

## 单次受控试验

实际会话目录：`results/p35-once-merged-20261021T030101Z/`。工具复用 P35 名称，本轮执行归 P36。

输入为已布线 TTL33/PWM2 原生 bin 与配对无 firmware-name 设备节点 overlay。独立文件名、一次启动 hold、恢复启动保护先于配置、无驱动启动检查、一次 PL/一次 overlay；不热卸载、不热重配、不发射。原始 UART 与脚本快照保留在结果目录。

实际只执行一次重启、一次 PL 配置、一次 overlay，得到新 boot `1263532f-8a39-4a37-9217-e290d0025553`。原始启动保护在装载前已经恢复；默认厂家固件未覆盖。PL 进入 operating，overlay 命令返回 0，AD9361、DRM、VDMA、PWM2 均正常初始化。

主试验最终状态保留 `failed_or_state_unconfirmed`：后置检查错误地要求虚拟 framebuffer 恰好 800×480，而实际为 800×960 双缓冲。这个错误发生在成功 probe 之后，不是内核失联，也不能为了得到绿色状态再装载一次。现已修复门槛为虚拟空间至少容纳可见尺寸，真正可见尺寸由后续 ioctl 核对。保留原始失败报告、执行脚本及 UART，补验另立报告。

## 当前同启动实际补验

| 项目 | 实际结果与原始证据 | 范围 |
|---|---|---|
| 显示/计时只读复核 | `results/p36-display-readback-20261021T030850Z/report.json`；fbset ioctl 为可见800×480、虚拟800×960、32bit，stride3200；FCLK0=99,999,999、FCLK1=199,999,998、像素软件率32,999,000 Hz；PWM2 requested/enabled/50µs，PWM0/1未请求，arm_global_timer、uptime进度匹配 | 寄存器因无platform resource文件保守跳过；不是外部像素频率测量。sysfs mode为空的false不等于ioctl几何失败 |
| 有限RX配置 | `results/p35-finite-rx-prep-20261021T030951Z/report.json`；Fs30.72MS/s、BW18MHz、LO2450MHz、manual0dB读回 | 仅RX属性设置，无TX |
| 取消/重建 | `results/p33-rx-cancel-board-20261021T031013Z/report.json`；8轮均通过，每轮重建后2次有效refill；独立boot/taint/scan/buffer及属性末检一致 | 新TTL33同启动实际DMA验证，非长期连续性证明 |
| 16缓冲稀疏采集 | `results/p36-sparse-smoke-20261021T031051Z/report.json` | 复用P27已验证二进制，单一DTR/RTS预设关闭串口句柄；只保存1.5625%，不能称完整流 |
| 修正面板实际绘制 | `results/p36-panel-snapshot-20261021T031301Z/report.json`；analyse-only/draw数值一致，分析约3.44ms、CPU绘图约3.50ms | 文件快照；不是接收/显示端到端延时或FPS；physical_display_verified仍false |
| 可见区字节导出 | `results/p36-fb-snapshot-20261021T031505Z/report.json`；只读fb0，ioctl布局/offset/extent前后一致，导出1,536,000字节，gzip9,116字节 | 还需电脑归档与图像检查；不是物理屏幕照片 |

面板第一次会话 `results/p36-panel-snapshot-20261021T031141Z/report.json` 在 analyse-only 通过后，因检查函数的 `for d` 覆盖了执行目录变量而返回127，实际绘图未运行。保留失败，最小修复是在检查后重新建立目录变量；新会话通过。首次会话仅解绑 framebuffer console（原bind=1），未解绑串口；当前屏幕console保持bind0，普通重启可恢复。不要把这个方法错误归为RF或硬件问题。

以上首次证明这组TTL33/无firmware设备树路径能够同启动初始化并实际接收、向帧缓冲绘制。本轮同时改变了未用LVDS分支和加载路径，不能据此唯一归因旧挂死，更不能宣布旧内核卸载缺陷或CDC全部根治。

## 后续完整数据验收

完整 IQ 的分层标准见 [P36 完整 IQ 合同](p36-full-iq-contract.md)。稀疏 1.5625% 留存不能写作完整 ADC 连续流；返回缓冲全部字节留存与真正无丢样是两个结论。

## 重要新发现：32位时钟率溢出，尚未修复上板

后续只读检查 `results/p36-clockwiz-readback-20261021T031935Z/report.json` 确认 LOCK=1、live DT/绑定/地址译码有效；配置影子寄存器为 `0x200=0x05F43105`、`0x208=0x0007CA03`。前一次031748Z因工具只认platform设备名、没认精确OF资源标签而保守跳过，原始结果保留；最小修正后才读取，不是通过绕过地址门槛读取。

供应旧内核驱动的fixed-factor时钟率最终返回ARM32的unsigned long。输入99,999,999 Hz、M49.5时，中间clock需表示4,949,999,950 Hz；截断mod 2^32后恰为655,032,654，和clk_summary完全吻合。其后ceil(/5)=131,006,531也精确吻合。DRM据此请求33MHz，源码千赫兹计算会生成O3.970，寄存器及软件输出32,999,000均与该链吻合。**软件报告33MHz不能证明硬件像素33MHz，LOCK=1也不能证明输出频率正确。**

硬件寄存器0x208是影子配置，并非物理MMCM频率测量。生成DRP源码还对分数按1/8量化，因此不得将按千分数推算的249.37MHz直接写成实测输出。供应源码不保证与dirty运行内核逐字一致，但此整数链与实读值的精确吻合支持本项诊断。

最小修复候选是在独立Vivado副本选择M16.5/D2/O25，保留100MHz输入和33MHz输出，避免内部fixed-factor率超32位范围；必须验证BD、生成primitive和DRP初值一致，再综合/布线/导出、单次干净启动、重新读寄存器/时钟并验证屏幕。**本轮没有完成该新候选的生成、构建或上板，不能称时钟问题根治。**旧板卡驱动热卸载缺陷、CDC/外部IO及长期并行验收仍开放。

## 完整缓冲及图像实际归档

- `results/p36-full-rx-build-20261021T031400Z/report.json`：25项实际C mock与ARM检查通过；实际部署SHA为`b7db8cbf5502516075386c49c91d9de7f516e582d15964b61b620628df31fcb5`。旧构建只保留历史。
- `results/p36-full-rx-board-20261021T032307Z/report.json`：同boot完成16×65536帧，4,194,304字节全部返回缓冲在板端保存；获取耗时0.035444182秒，独立RF/idle/taint末检通过。原始packed SHA=`8eec20a10ced29d90780b2d2c22c5e207e4ee50ce6722293f740370d6a18df93`。保留high4未定义位，分析须掩低12位再符号扩展。不证明ADC无丢样或已知目标。
- 完整IQ电脑归档 `results/p36-file-archive-20261021T032458Z/report.json` 中断，53块中仅15块本地SHA核验通过；没有最终完整文件/整文件SHA验收，不能标已归档。未发现该回传程序仍运行，原报告保持中断现场。补充只读回传工具的`--resume-from`，先校验本地前缀再在新报告重验板端源，旧记录不改。
- 屏幕可见区字节已完整归档：`results/p36-file-archive-20261021T031834Z/report.json`，raw1,536,000字节两端SHA一致；由真实BGRX布局转换成同目录`screen.png`，已查看频谱、文字和布局。该图是framebuffer回读，不是物理LCD照片，不关闭时钟/物理显示问题。

## 当前状态与恢复边界

用户随后询问进度时，新的只读恢复会话 `results/p36-file-archive-20261021T081445Z/report.json` 未建立COM8 shell，串口未收到回应，已关闭句柄，没有发重启、PL/overlay、RF或TX命令。本次不能确认当前boot/taint/运行状态；不能把早先boot状态冒充实时状态，也不能据无回应唯一判断硬件挂死或断电原因。

恢复时先确认供电/串口身份及boot。若boot已变，RAM完整IQ可能已丢失，禁止重放旧boot回传；15块电脑侧前缀仍保留。重新采集应使用同一个经SHA核验程序并另立报告。若同boot且源SHA/大小仍一致，才用新`--resume-from`完成53块。

下一步依赖顺序：确认当前板态→完成/重做IQ归档→独立构建避免32位率溢出的ClockWiz候选→干净启动装载一次→核对clock tree、配置影子及LOCK（物理频率仍需相应证据）→有限RX、屏幕/触摸和重复启动→长流与已知源连续性→AI和最终独立运行。禁止热卸载RF/PWM，禁止驱动绑定期间重配PL。
