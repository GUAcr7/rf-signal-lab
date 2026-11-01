# P35：P34 独立复核与面板程序纠错

日期：2026-10-21（北京时间）。本子任务不操作板卡、串口、界面；P34 原始实验记录、供应文件和原始证据均未改写。后续主任务的实际恢复/上板证据另记。

## 验收结论

**接受工具构建能力与两次单功能驱动探测；不接受“PL 完全正常、CDC 已排除、唯一问题是设备树”的结论。**

- `E:/FPGA_Tools/Work/p34-part-probe-20261020/probe4.log` 第20行实际获得 Synthesis 授权，末尾 `P27_SYNTHESIS_CAPABILITY_PASS`；PWM2 构建日志末尾确有 Bitgen 成功、`write_bitstream Complete!`、100%。因此当前有工具/授权能力，不再以旧安装状态推断不可构建。
- [显示侧原始回读](../../results/p34-bisect1-verify-20261020/transcript.json)只证明 FPGA 状态 operating、DRI、fb0 800×480 和背光设备节点存在；[射频侧原始回读](../../results/p34-bisect2-rf-verify-20261020/transcript.json)只证明 RF 模式、operating、四个 IIO 节点及 PHY/ADC 名字。没有 RX refill、并行流量、稳定时长、实际像素/背光测量或 boot_id 闭环。
- P34 收工记录还写明最后再次串口失联、厂家文件恢复未确认。因此两种单功能树启动成功不能证明并发状态、时钟门控、驱动生命周期或 CDC 没问题。

## 必须修正的项目

以下行号来自本次读取时的 P34 版本；主任务若已追加纠正，旧句仍属于历史结论，不应继续作为现状引用。

| 级别 | 位置与证据 | 影响 | 最小修复与复测 |
|---|---|---|---|
| P1 | `results/p34-deploy-package/README.md` 第11行的 `.bin` 实际以 `00090ff0` 开头，5034572字节、SHA `96c5d8f3...`，是带头 `.bit` 改名；该 README 第85行和状态 JSON 的 rollback 仍建议 `rmdir` 热卸载 | 容易再次部署错误格式并触发已知驱动卸载风险 | 隔离旧包；发布原生 `-bin_file` 输出及完整 SHA；改为已验证的启动保护/重启恢复路径。新包分别检查头部、长度、来源、SHA、overlay 固件名与回滚流程 |
| P1 | `START-HERE.md` 第13/37行，二分文档第67/184/186行把 probe 扩大为“完全正常/唯一 DT 缺陷/CDC排除”；P34 session_close 又明确 responsive=false | 会跳过实际并发与失联原因验证 | 改为“分别单功能 probe 成功，失败条件与根因未闭环”；先恢复/确认当前启动，再按受控单变量顺序记录 clocks、kernel、RX 与显示并行 |
| P1 | `TX-SOURCE-STATUS.json` 第1751行仍将 authoritative_current_field 指向 p32_current，而 P34 session_close 记录无响应、恢复未确认 | 自动恢复会误读几小时前的健康 boot | 增加准确的当前状态字段，历史字段保留作用域；新启动必须读 boot_id/固件哈希/模式，禁止重放旧 boot 脚本 |
| P2 | P34 位流生成文档第112/207行将 DRC 的58 Advisory 当作 CDC | 严重程度与审查对象错配 | PWM2 的 `rf_display_top_drc_routed.rpt` 摘要实际是 AVAL-4=56、REQP-181=2；独立 CDC 报告是另一份结果。两者分别链接，不互相替代，换候选后重跑 CDC |
| P2 | `START-HERE.md` 第61行与二分文档 B4 声称“改成忠实拼接”便是修复路线；而 `p31_build_overlay.py` 第110–113行本已从两份原厂 DTS 经 clean_body 合并，第115–124行才改 DMA 时钟/4KiB资源和 ClockWiz 时钟 | 盲目重做同一实现，或撤销匹配合并硬件的必要差异 | 对最终应用后的树做语义差异表，逐项核验 clocks/reg/IRQ/PWM/fixup/启动顺序；每次明确单变量，不能把拼接形式当根因 |
| P2 | `START-HERE.md` 第19–22行把124字节当通用 `.bit` 头长度 | 不同设计名/元数据会改变封装头，硬截断可损坏后续位流 | 只发布原生 `.bin`，或解析并验证完整 `.bit` 字段长度和 payload。当前样本的124字节偏移已经 SHA 验证，但不能泛化 |
| P2 | 二分文档引用的 `results/p34-retry-verify-20261020/` 不存在；完整19KB启动日志写“本轮抓取”，没有稳定文件链接；两个 verify 没记录 boot_id | 难以复核实际启动顺序及运行位流身份 | 后续试验保存从上电开始的原始串口字节、boot_id、位流/overlay/脚本完整哈希、命令退出码和独立回读。旧缺失证据明确标缺失，不补造 |

## 位流格式与“静默”解释的边界

只读逐字节核对得到：

- 旧包 `rf-display-p32.bin` 为5034572字节，SHA `96c5d8f3a5fb8cd070e94568871c77eec6c69203212c9ed25587c3c1a885b13c`。
- 原生 `E:/FPGA_Tools/Work/p34-binfile-20261020/rf_display_top.bin` 为5034448字节，SHA `34eeb736c9e384a8751a89acbb14cea144870b8155b35a533bdeddbc8bdb6756`。
- 旧包去掉本样本的前124字节后，**全部字节**严格等于上述原生 `.bin`。新生成 `.bit` 的头部元数据不同，整个文件 SHA 不同；同样剥离124字节后 payload 相等。

供应内核归档 `linux-xlnx-ad-fmcomms3-ebz.tar.gz`（SHA `2b11bea5872677e0c444f3c43518ada78814dd90b3fa4d31d1e2bce582bb1a70`）中的 `drivers/fpga/zynq-fpga.c` 第330行仅在前52字节搜索交换后的同步字，第341–346行据此决定是否交换整个缓冲的字节序；第373行使用没有超时的 `wait_for_completion`。这说明带124字节头的文件确实不符合该 loader 的检测范围，也给出“启动线程等待配置完成而静默”的候选机制。

**源码归档不等于运行 dirty 内核的精确版本。没有串口输出既不能单独证明 PS 总线死锁，也不能单独证明设计从未配置。** 不能从同一种静默外观反推唯一硬件原因。

## 面板程序已做的最小修复

源码：[arm_panel.c](../../embedded/arm_panel/arm_panel.c)。新增回归与交叉构建：[p35_arm_panel_check.py](../../experiments/p35_arm_panel_check.py)。

1. FFT 帧数求平均，再按 `N * sum(Hann^2)` 归一化，报告单位为 **count²/FFT bin**，参考为每 bin 1 count²；不是 dBm，也不是每 Hz PSD。原来的8帧求和峰值会比1帧高约9.03dB，不能沿用旧峰值作为新数值基线。零输入标记无峰，频偏为 null，避免伪造 -512bin 峰。
2. `analysis_ms`、`draw_ms`、`iteration_compute_ms` 分开记录。去掉由单次绘制耗时倒数得到的伪 FPS；屏上只显示已测本次分析耗时。文件读取、设备初始化、RF采集、串口输出、scanout/vsync 均不在该计算指标内。
3. `FBIOGET_FSCREENINFO/VSCREENINFO` 确认800×480、32bit已知小端 X/ARGB8888、真实 stride、可见 offset、virtual边界与 smem_len。绘图使用实际行跨度，未知格式拒绝，不能以 mmap 成功代替格式确认。
4. 新增 `--analyse-only`，不打开 `/dev/fb0`，输出逐次 JSON；旧位置参数 CLI 保留。数字参数严格解析，超范围/截断或不完整通道输入明确失败。频谱纵轴明确为相对当前峰值 dB，并纠正原纵轴刻度方向。

## 验证结果与下一步

[最终独立证据](../../results/p35-arm-panel-check-20261020t161014z/report.json)含精确源码/字模/runner快照、编译参数、输入IQ、stdout/stderr和ELF读回。**62项主机回归与结构核对通过**：正负频偏/DC、2/4/8通道、1/2/8帧、NumPy峰值/RMS/功率和、帧数不漂移、零输入、非法参数、短/奇数/不完整通道文件，以及带padding/offset的帧缓冲地址和格式拒绝。前一轮 `160655Z` 也通过，但其零输入人读摘要仍打印旧的虚假频偏；最终轮同时验证 JSON、UI逻辑和人读摘要均不报告零输入峰。旧轮完整保留，最终以 `161014Z` 为准。

ARM8.3交叉编译 `-Wall -Wextra -Werror` 通过，readelf确认ARM32硬浮点与`/lib/ld-linux-armhf.so.3`。新二进制为最终证据目录内 `arm-panel`，27172字节，SHA `39958b75d4d377bcea22a5f153138c58be76291570c80305e883ff658245db77`；源码SHA `4a74dcd045caef4fb503946bfbd75f657bc51d0925f4085af6be9b1fc419d911`。**尚未由本子任务上板执行**，旧 `embedded/arm_panel/arm_panel` 二进制未覆盖。

按依赖继续：先恢复并独立确认启动状态 → 采用正确格式和受控启动/回滚 → 合并候选实际时钟/外部IO/CDC检查 → 单功能有限数据测试 → 同一次启动显示与RX并行 → 用新ARM程序分别执行 analyse-only 数值核对和匹配格式的 framebuffer 绘图。不得用主机62项通过代替板上显示或RF验收。
