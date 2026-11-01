# P35：P34交付纠错、真实接收补验与TTL33候选

日期：2026-10-21，北京时间。承接10月20日晚P33、P34工作。原始串口/构建日志未改写。

## 当前结论

工具授权及位流生成能力已经具备；P34确有两种厂家设备树分别完成驱动初始化的进展。但“位流完全正常、唯一缺陷在设备树、CDC已经排除”没有充分证据，本轮撤回这些完成结论。合并加载失联的根因仍待定位。

本轮补验已证明：**当前P32 PWM2合并PL、厂家RF设备树、同一启动下，有限RX取消/恢复和16缓冲读取通过。** 这不是RF与显示并行验收，也不是无丢样或已知目标的接收验收。

## 已修复与证据

1. **恢复默认磁盘固件**：[原子恢复记录](../../results/p35-restore-vendor-files-20261020t160202z/report.json)。恢复前，三个默认固件文件都是实验P32 raw；`.vb`备份完整SHA已核验。逐个临时复制、核验、原子替换并sync，恢复厂家`ad9361.bin`、`display.bin`、`system_wrapper.bin`。厂家两个DTBO也核验一致。**没有重启、没有卸载驱动、没有改变当前加载的P32 PL**；下一次普通启动为厂家RF模式。
2. **停用有缺陷的旧部署包**：[格式核对与封存](../../results/p35-package-format-audit-20261020t160521z/report.json)。原包`.bin`实际上是5034572字节`.bit`容器；解析其变长字段得到offset124，payload逐字节等于Vivado原生裸`.bin`5034448字节、SHA`34eeb736c9e384a8751a89acbb14cea144870b8155b35a533bdeddbc8bdb6756`。旧二进制保留作为证据，README替换为停用说明，旧部署脚本入口立即退出3，撤回热卸载回滚步骤。正确格式副本仍仅供调查，不是新TTL33位流。
3. **不再硬编码124字节切头**：新增`src/rfsig/bitstream_format.py`，核对完整容器字段、payload长度及该Zynq loader的前52字节同步字范围。6个边界测试通过。首次负例测试误把本来就是0的字节替换成0，没有改变夹具而失败；随后修正为真正损坏头部的负例，未修改解析器来迎合测试。
4. **实际RX恢复补验**：[8轮取消/重建](../../results/p33-rx-cancel-board-20261020t160708z/report.json)，每轮取消后旧buffer立即返回负值，重建后两次refill有效，RF设置保持、独立回读buffer/scan关闭、taint0。此工具在P33创建，所以结果名前缀仍为P33；本次作用域是P35的新启动。
5. **实际RX有限采集**：[16缓冲接收记录](../../results/p27-smoke-20261020t160826z/report.json)。每个65536 IQ帧，检查RX1 I/Q布局，保留每块前缀中的稀疏样本，总保留率1.5625%。不能称完整连续IQ。没有启动任何TX应用。
6. **单独记录RX参数修改**：[准备记录](../../results/p35-finite-rx-prep-20261020t160650z/report.json)。由2400MHz/slow_attack改为项目有限试验配置2450MHz/manual/0dB，Fs30.72MS/s、BW18MHz不变。取消测试本身没有RF属性写入。无TX设置或发送。

## 独立审查与后续实现

- [P34证据边界及面板程序修复](p35-p34-independent-audit.md)：纠正DRC58个Advisory与独立CDC报告混淆；修复帧数求和导致峰值漂移、把绘制时间当整帧FPS，以及未检查framebuffer布局的问题。新ARM程序仍需板端复测，不能沿用P34的2.34ms/帧结论。
- [设备树语义审查与新候选](p35-overlay-audit.md)：P32与厂家两树联合后的差异只有8项必要调整，原实现本来就从厂家树合并；盲目重拼不能解释失联。新`rf-display-p35-explicit.dts`移除整个firmware-only region片段，要求先显式加载匹配PL，再应用设备节点。电脑原生FDT应用后只删除firmware-name，其余890属性保持。**尚未上板，尚未证明解决失联。**
- [TTL时钟审查](p33-external-timing-review.md)：当前实物是RGB TTL接口；旧辅助LVDS PLL在33MHz运行模式下不满足输入范围。新`E:/p33-ttl-114312`删除未用LVDS/辅助并行输出，初始像素33MHz、PWM通道2，保留RF/PS/触摸/DRP。新构建正在进行，禁止复用P30/P34的148.5MHz时序结论。
- [CDC候选与起流边界](p33-cdc-specific-review.md)：sync_id源端注册候选仅在独立副本做受限数字对照，未并入TTL工程。即时起流overflow、快采样TX underflow夹具/接口疑点保留，不能用加3周期等待关闭。58条旧CDC没有因此被豁免。

## 当前板卡作用域

新板COM8，boot=`8033ec3f-0588-4e7a-8572-e440c547cf43`。当前加载的是P34试验的P32 PWM2合并PL，厂家RF树，无显示节点；磁盘默认固件已恢复厂家原件。旧板COM9，boot=`182e235d-a1d2-4964-856c-feb7ecf5873f`，最近检查无TX应用。不能把磁盘恢复写成“当前PL也恢复厂家”；必须重启后重新确认。

## 下一步与门槛

1. 完成TTL33实际综合/布线与时钟/DRC/CDC复核；保持未约束外部IO的准确限制，不用零时延或整体false path消告警。
2. 发布与该DCP配对、格式/哈希可追溯的原生裸bin；配对显式加载DTS。
3. 使用已验证的一次新启动hold，先确认无RF/显示驱动和overlay、恢复启动保护已在位，再显式加载PL并单次应用设备节点。分别保存每步日志/退出码/boot_id；失败不热卸载或热重试。
4. 先有限RX、图案/真实像素时钟、PWM2背光、触摸与系统计时，再并行接收显示。此后才做完整IQ、真实AI、信号质量及整机验收。

冷启动0xFF及旧内核热卸载缺陷仍开放。当前证据无需用户再补资料即可继续电脑侧与受控工程验证；实际屏/射频最坏时序验收仍缺裸屏和板级时延资料。

## 00:29阶段收尾：用户要求先汇总

- TTL33新工程已经完成，不再是“正在构建”。[原生布线与独立摘要](../../results/p35-ttl-route-20261020t161703z/post-summary.json)：WNS+0.490ns、WHS+0.054ns，内部setup/hold/pulse-width失败端点0、路由错误0；实际像素33MHz。仍保留58条Critical CDC、7输入/29输出外部时延缺项，不能宣称全时序或CDC通过。
- [新裸位流导出](../../results/p35-ttl-bin-20261020t162454z/report.json)成功。原生bin5709252字节、SHA`9af156ead2ab43564cdbdce3f0cad780d58cdf27aab437ba62a38fa29a1fb347`；逐字节核对与解析`.bit` payload一致，配对BD和DCP可追溯。**新位流尚未配置到FPGA。**
- 新版ARM分析程序已在当前新板执行已知正负频偏、零输入与1/8帧比较，[板端结果](../../results/p35-panel-board-20261020t161445z/report.json)通过。此为无屏分析，不是新版framebuffer绘图验收。62项主机回归/结构检查及17项Python目标测试分别通过，不把它们合计成硬件测试数量。
- 实际RX的65536字节稀疏原始样本已[按块及整文件SHA下载归档](../../results/p31-sparse-archive-20261020t162105z/report.json)，仍明确总保留率1.5625%、lossless=false。
- [CDC12旧布线锥体复核](p35-cdc12-routed-cone.md)确认两个时钟名来自同一物理MUX、raddr经过两级同步，关闭的是资料缺口；没有豁免2条CDC12，更未关闭全部CDC。
- 新启动脚本已[静态核验](../../results/p35-once-static-20261020t162443z/report.json)。随后开始上传新文件，用户要求先总结，[试验记录](../../results/p35-once-merged-20261020t162656z/report.json)在上传未完成时中止，**重启0次、PL配置0次、overlay应用0次、尚未安装一次hold**。
- 已停止本任务上传进程、只中止其拥有的base64解码器并恢复串口echo；[独立结束检查](../../results/p35-interrupt-close-20261020t162845z/report.json)确认boot未变、taint0、RF三设备就绪、buffer/scan关闭、原启动guard不变。没有后台任务会继续自动重启。部分RAM上传文件仅是未完成临时件，不得当作有效位流使用。

下一次先重新读boot_id与当前状态，再用新的时间戳重启这次上传和受控新启动试验；不能把未完成上传标成上板成功。默认厂家文件恢复已经完成，当前运行PL仍是P34留下的P32合并PL+厂家RF树。
