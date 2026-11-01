# HW-027：P37 修复32位时钟率溢出

- 日期：2026-10-21。用户再次确认通电接线，授权继续修复。
- 前置问题和证据见 [HW-026](exp-hw-026-fresh-boot-ttl33.md)。本记录随实际结果补充，准备/构建不等于上板通过。

## 重新认板

`results/p32-preflight-20261021T082123Z/report.json`：旧板COM9 boot=`41a13b8a-9886-4eeb-b825-6e0023432788`，未观察到TX；新板COM8 boot=`58d8ed5c-2d12-49e1-a221-3ca78a6aca75`，RF模式、guard匹配、taint0，串口响应。厂家RF初始化出现`Unsupported PRODUCT_ID 0xFF`，PHY/ADC/DDS不齐全。保留冷启动失败，不能当成接收通过；未热卸载或重配PL。

本轮另存 `results/p35-firmware-readback-20261021T082634Z/report.json`，核对厂家固件与启动文件；旧boot的RAM IQ不再按旧身份回传。电脑15块前缀保留为历史不完整证据。

## 最小硬件候选

原ClockWiz先表示100MHz×49.5的fixed-factor中间率，超出ARM32 unsigned long；后续除5之前已经截断。保留100MHz输入、33MHz输出及其余设计，只在独立副本使用安装IP的`OVERRIDE_MMCM`接口设置M16.5/D2/O25：中间率1.65GHz、VCO825MHz，都在需要的表示范围内。

`results/p37-safe-clock-prepare-20261021T082321Z/report.json`已实际通过Vivado BD验证及生成：

- 独立目录`E:/p37-clock-082321`，旧P35源文件哈希前后相同。
- 唯一改动组件`clk_wiz_0`，端口、连接、接口及地址映射一致。
- 新BD SHA=`093dfc4823508884a9877e22f4b4f2ad3c0310e2fe6f5f949ce4a0cdc8a147ab`。
- 实际生成的MMCME2_ADV参数为16.5/2/25，不只依据GUI或脚本设置值。
- RF、PWM2、TTL路径保留，无LVDS分支，未改旧内核和原始工程。

准备阶段要求综合/布线和原生bin导出按原时序/CDC报告合同执行，另外检查实现后的MMCM参数。最终构建结果见下节，58项旧CDC及外部IO延迟缺项保留，不加豁免、不把未测范围写成通过。

本地主机回归 `results/p37-clock-contract-20261021T083804Z/report.json` 精确重现旧实读溢出链，验证新内部率在signed32内，并检查实际生成DRP复位影子为`0x05F41002`及`0x00000019`，与primitive匹配。它不是上板测试。

第一轮综合 `results/p37-safe-synth-20261021T082809Z/report.json` 因独立副本重新生成未改动的视频TPG HLS而主动停止本次进程树，原失败日志保留；没有时序失败或板端动作。随后只复制旧项目同一视频组件的缓存，6个文件逐一SHA一致，见 `results/p37-video-cache-copy-20261021T084321Z/report.json`。新一轮 `results/p37-safe-synth-20261021T084321Z/report.json` 要求Vivado原生`cache_has_match`确认cache-ID=`e80800addbb7fa01`才继续；修改后的ClockWiz仍使用新生成/综合结果。复用缓存不能替代新整机布线、时序、MMCM参数检查。

## 本轮实际构建

- 综合 `results/p37-safe-synth-20261021T084321Z/report.json` 通过。综合前布线的保持负裕量保留在post-summary，不当作最终时序；最终依据下项。
- 布线 `results/p37-safe-route-20261021T084904Z/report.json` 及其 `post-summary.json`：WNS=+0.352ns、WHS=+0.036ns，setup/hold/pulse失败点均0，内部无时钟/无约束端点0；外部输入7/输出29缺延迟仍开放。CDC Critical仍58，未加豁免；不要与bitgen的58项DRC Advisories混淆。
- 实现后的MMCM参数16.5/2/25原生核验通过。`results/p37-safe-bin-20261021T085630Z/report.json` 原生bin导出、sync及bit容器payload逐字比较通过，并钉住DRP初始影子源码哈希。
- 同目录 `overlay-report.json` 复用逐字相同、无firmware-name的既有DTBO；只重绑P37 BD来源。依据是所有设备、输入/输出请求频率、连接、地址及接口均不变，差异只在ClockWiz内部乘除参数；旧P35证据不覆盖/不改。
- 已给旧P35已知溢出候选增加停用说明，加载工具也拒绝无安全时钟证明的旧候选，防止错误回放。

上板前身份保护在 `results/p35-once-merged-20261021T085808Z/report.json` 拦截到boot已从58d8…变为c2a4…，该会话重启/PL/overlay计数均0，失败原件保留。重新只读认板 `results/p32-preflight-20261021T090015Z/report.json` 确认boot=`c2a471fa-0764-4775-acd6-bfb31d1f5efd`，厂家RF三设备恢复、taint0、buffer/scan空闲。不是本工具发出的重启；具体外部原因未验证，不归因。

当前这一启动已经RF_READY，因此正式P37试验使用严格默认门槛，不需要新加的厂家PRODUCT_ID_FF例外。该例外仅允许记录明确旧厂家冷启动0xFF后进入新的空hold启动，不能放宽配置后的RF设备门槛。

## 实际上板及关键时钟验收

正式会话 `results/p35-once-merged-20261021T090121Z/report.json` 通过：1次普通重启到空hold、先恢复guard、1次原生PL配置、1次无firmware设备节点应用；新boot=`92bd78be-43f1-48c0-b390-b6841cb82111`。RF三设备、DRM/fb0、800×960双缓冲/32bit及系统计时源正常。默认厂家文件、BOOT及模式不改，未TX。

加载的P37 native bin为4,911,716字节，SHA=`1b0fac1aec86e4efeb003f9ea8d1a98d0e339e649633e31034d59e0990064405`。gzip封套解压后另核对原始SHA，再配置；不是给.bit改后缀。

`results/p36-clockwiz-readback-20261021T090546Z/report.json` 通过live DT/资源/driver/时钟门槛后实际只读寄存器：LOCK1，feedback=`0x05F41002`、output0=`0x00000019`，解码M16.5/D2/O25。注册mul=1,649,999,983 Hz、mul_div=824,999,992 Hz，未截断；软件pixel32,999,000 Hz与配置推算32,999,999.67 Hz在旧驱动舍入范围内一致。

独立文件验收 `results/p37-clock-accept-20261021T090640Z/report.json` 检查同boot、加载来源、一次性计数、guard恢复、寄存器与上述时钟树，结论为**本固定配置/本次启动的ARM32溢出修复及driver/寄存器一致性通过**。这不是外部PCLK仪器测量，也不等于所有冷启动、CDC、持续采样或物理画面均通过。

RX配置 `results/p35-finite-rx-prep-20261021T090641Z/report.json` 已读回30.72MS/s、18MHz、2450MHz、manual0dB，随后继续有限RX和绘图复测。

## 同启动有限接收与绘图复测

- `results/p33-rx-cancel-board-20261021T090718Z/report.json`：8轮取消/重建、每轮重建后2次有效refill，独立最终boot/taint/scan/buffer/RF属性一致。
- `results/p36-sparse-smoke-20261021T090842Z/report.json`：16缓冲稀疏诊断通过，保持1.5625%留存的准确语义。
- `results/p36-panel-snapshot-20261021T091016Z/report.json`：同一冻结稀疏IQ的analyse-only/实际绘图指标一致，fb ioctl布局门槛通过。它仍是快照，不是持续流/物理LCD验收。另一次主机调用误填不存在的smoke目录090826Z，被文件前置检查拒绝，未开串口；实际使用上述090842Z报告重做。
- 随后用户在本对话明确回复：“能看到，画面稳定”，对应询问为新板实体LCD是否显示“RF SIGNAL LAB”标题、绿色频谱曲线且稳定。这是本配置的人工实体可见性确认，独立于帧缓冲回读；不是照片、外部PCLK测量或任意持续时长保证。补充记录见 `results/p37-human-panel-confirmation-20261021T092425Z/report.json`，原090640Z机器验收报告不追改。

## 完整返回缓冲留存与电脑归档

- `results/p36-full-rx-board-20261021T091156Z/report.json`：同boot接收16×65,536帧，每帧RX1的I/Q各16bit容器，严格校验`le:S12/16>>0`。共1,048,576帧、4,194,304字节，16次有效refill的全部返回字节保存，取消线程已join、buffer/context释放，独立buffer/scan全0、taint0，RF属性前后一致。未启动TX、内环或测试信号；输入目标未知。
- `results/p36-file-archive-20261021T091318Z/report.json`：53/53块归档成功；传输前后boot、guard、原始压缩源大小/SHA及RX空闲均核对。整包gzip CRC、压缩SHA及原始SHA一致；电脑完整文件为该目录`iq-packed.bin`。原始SHA=`41f3cd24573aa5c8e1428e2ecacf859e6bca28c8446b94b675f224bbce977f6f`。
- 16块帧数除以读回采样率为约34.13ms；实际采集软件计时35.31ms。这两个值均不能建立连续ADC时间轴。没有ADC序号/overrun独立证据，`hardware_gaps=unknown`、`lossless_proven=false`，不得将“完整返回缓冲留存”改写为“连续无丢样”。旧boot的15/53块不完整归档没有被补成此次数据，也不覆盖原件。
- `results/p37-archive-review-20261021T092318Z/report.json` 独立在电脑重核压缩包及原始字节、元数据块偏移、16块布局，按低12bit掩码再符号扩展解码，不能把未定义高4bit当符号位。解码范围-36至33 counts，仅做数字统计，不推断目标、dBm、调制或EVM。`tests/test_p37_archive_review.py` 穷举65,536种容器字验证全部padding模式的解码，1 passed；对应运行记录见人工确认目录`decode-test.txt`。

## 屏幕回读及最终只读复核

- `results/p36-fb-snapshot-20261021T092022Z/report.json`：以只读mmap回读当前可见800×480、32bit，虚拟800×960双缓冲，前后几何一致。1,536,000可见字节，非原子快照，不作为物理扫描证明。
- `results/p36-file-archive-20261021T092121Z/report.json`：该屏幕数据1/1块完整归档。电脑按实际BGRA/BGRX通道位域生成 `results/p37-archive-review-20261021T092318Z/screen.png`，已人工查看标题/频谱/数字均正常，底部明确标注Saved IQ、非实时RF/dBm。实体可见性另由上述用户回复支持。
- `results/p36-display-readback-20261021T092145Z/report.json`：同boot/taint0、FCLK/软件pixel约33MHz、PWM2请求/使能/50µs、PWM0/1未被请求、计时源/uptime前进正常；serial已关闭。`fb0/mode` sysfs返回空字符串，故该单项布尔值false，不能写成所有checks全true；`fbset`与帧缓冲ioctl实际确认800×480、虚拟800×960。该保守读取器未建立直接寄存器门槛所以跳过MMIO；关键ClockWiz寄存器证据仍采用前述090546Z独立门控读取，不补造本次读取。

## 当前边界及后续依赖

本轮关闭的是**固定配置下的ARM32时钟率溢出及当前实体LCD不确定性**；没有宣称整个项目根治。仍开放：厂家冷启动偶发PRODUCT_ID 0xFF；58项CDC与外部7输入/29输出延迟缺项；长时间RF/绘图并行与真实连续性；已知激励下解调/EVM波动；真实AI；开机自动独立显示应用。上轮冻结或失联不能仅凭这次成功认定所有根因已消失。

当前新板保持P37合并PL、RF空闲、实体屏幕显示冻结快照；未要求断电，不关机。guard和厂家默认磁盘固件未替换，mode仍rf。**普通重启/断电上电会恢复厂家RF启动路径，不会自动恢复此合并PL及快照应用。** 电脑已有完整IQ/屏幕证据，RAM临时文件仍会丢失；下次按[恢复清单](../handoff/resume-p37-20261021.md)重新认板后继续，禁止沿用旧boot或热卸载/热重配。

## 上板验收门槛

必须使用一次新的hold启动，先恢复原guard、确认无RF/显示驱动和overlay，才装匹配原生bin并应用设备节点一次。厂家冷启动0xFF只能作为本次干净启动实验的前置失败保留，禁止热卸载尝试恢复。

预期运行时：FCLK0约100MHz、FCLK1约200MHz；mul约1.65GHz、mul_div约825MHz；影子M16.5/D2/O25且无输出分数，LOCK1。按字段推算与软件率需一致在已声明舍入范围内。寄存器/软件一致仍不是示波器测得的外部PCLK。

上述本启动有限RX、取消/重建、完整返回缓冲归档、绘图和人工实体可见性已完成；下一次启动仍须复测。重复启动及持续并行另列范围。不自动启动旧板TX。
