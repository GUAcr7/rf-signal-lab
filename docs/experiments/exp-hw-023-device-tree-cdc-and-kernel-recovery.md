# EXP-HW-023：设备树契约、CDC有限仿真与热卸载异常恢复

日期：2026-10-19 晚，承接 [HW-022](exp-hw-022-rf-display-integration.md)。目录时间为 UTC，现场北京时间为 UTC+8。

**本轮离线设备树与部分数字仿真通过；原厂 RF 已在用户重新上电后恢复。合并固件未生成、未加载，RF 与显示共存仍未验收。** 原厂 RF overlay 热卸载触发了真实内核异常；当前以禁止热卸载、禁止重复配置规避，不能写成内核缺陷已修复。

## 当前状态与结论

| 项目 | 结论与证据范围 |
|---|---|
| 新板恢复 | 用户重新上电后已恢复；随后保护版脚本完整warm reboot通过，当前boot_id=`ebce10b9-e464-4b4c-b586-d4fd8d116e06`，原厂RF attempt1成功、PHY/ADC/DDS齐全、tainted=0 |
| RX 配置 | 已重新读回 RX1 manual/0dB、LO2450MHz、Fs30.72MS/s、BW18MHz、A_BALANCED；没有改变采样率/带宽/端口 |
| 恢复后采样 | 16 DMA 缓冲，只保留1.5625%的稀疏诊断字节；65536字节回传 SHA 一致，缓冲释放。不是连续完整 IQ、已知信号或 AI 验收 |
| 启动保护 | 7961字节，SHA256=`89183f1fe397f8bc20bd0c39544f5d30c37a8f1ca4e440c8cce6841d9b1247f2`；已原子安装、校验并通过一次完整正常重启；没有在绑定驱动的会话直接重新执行配置入口 |
| 合并设备树 | 原生 DTC 编译、libfdt 在电脑应用、240项检查通过；89项 AD9361 `adi,` 属性保持原字节。没有上板 |
| 独立契约核对 | 对实际保存后的 BD 核对30项，4种错误夹具均被检测；不是只比较生成器自己的常量 |
| ADI FIFO 数字仿真 | 原厂 RTL 未改，6种宽度/深度/时钟比例，36005次传输核对通过；含阻塞、回压和协调复位 |
| ADI DMA 仲裁数字仿真 | 原厂 RTL 未改，两个异步时钟组合，共256描述符、10878数据拍，TLAST/EOT及ID回绕核对通过；端点为 AXIS/AXIS |
| Python 检查 | 本轮启动保护15项通过，shell语法与危险实验禁用检查通过；没有重跑全套，864项是前轮历史基线 |
| 最终板端状态 | 两板没有观察到实验收发程序；新板 RX buffer=0、四个scan enable=0；串口句柄已释放。不是物理射频静默测量 |

## 原厂热卸载故障与恢复经过

计划只在不换位流、不改启动包的条件下，试验 RF-only 设备树的4KiB DMA窗口兼容性。前检核对设备身份、原厂 overlay 哈希、空闲缓冲和 RX 参数，并把候选上传到 RAM。

**22:18，第一次移除原厂工作 overlay 的 `rmdir` 返回139。候选尚未应用。** 原始日志显示 SPI/clock 提供者被移除后，内核在 `axiadc_remove+0x60/0x74` 访问地址0x00000008发生 NULL dereference。随后回滚的 configfs 操作超时，串口不能执行命令。因此本次结果为失败，4KiB目标驱动验证仍待做，不能称为“候选回滚成功”。

- [原始失败报告](../../results/p31-rf-driver-test-20261019t141834z/report.json)含完整堆栈、每条命令、真实返回码及回滚超时。
- 原执行程序逐字归档为同目录 `procedure-at-failure.py.txt`，SHA256=`1371333d44e3eae1ff97c1d294a245d322fb8bfa79ba41c8ade209c4faf5f7eb`；旧启动脚本也在该目录备份。
- [串口恢复观察](../../results/p31-oops-observation-20261019t142127z/report.json)：Ctrl-C只回显，未恢复可执行 shell。
- [SysRq恢复尝试](../../results/p31-sysrq-recovery-20261019t142254z/report.json)：UART Break+`s`未被识别，未继续发送`u`/`b`。该工具打印阶段发生GBK编码错误，但原始JSON已保存；不因此把重启写成成功。
- 用户随后仅给新板重新上电。[重新上电证据](../../results/p31-repowered-20261019t142539z/report.json)确认新boot_id、原厂probe成功和tainted=0。
- 恢复日志还有强制断电后的文件系统恢复/FAT未正常卸载提示；本轮未在已挂载文件系统上运行修复。后续维护应正常关机、在卸载状态检查，不把日志提示等同于已证实数据损坏。

### 源码定位的证据与边界

只读解包老师提供的 `D:\AD9361\AD9361\软件资料\Linux\Kernel\src\linux-xlnx-ad-fmcomms3-ebz.tar.gz`，保留压缩包SHA与选中文件SHA，见[源码归档](../../results/p31-vendor-kernel-20261019t143355z/report.json)。原文件没有改动。

该源码Makefile为4.9.0；`drivers/iio/adc/cf_axi_adc_core.c`的914–915行先`put_device(st->dev_spi)`，再通过`st->dev_spi->driver->owner`释放模块引用。错误清理路径890–891行也有同样模式；probe路径在解锁设备后重新访问driver，也需要生命周期审查。SPI driver已解绑时driver可能为NULL，与现场顺序及故障地址相符。

随后继续做了二进制核对，已将**这次直接崩溃点确定为空driver指针读owner**：

- [原厂uImage检查](../../results/p31-kernel-image-20261019t144415z/report.json)：头/数据CRC通过，完整嵌入版本为`4.9.0-rt1-xilinx-g0e07141-dirty`、GCC6.2.1、2020-09-01构建，与运行信息相符。镜像SHA256=`e30c220b0506dfbb1936766881c32027c4f89d17f8596c2b21472b5e818b63f7`，没有加载此文件。
- [故障指令匹配及反汇编](../../results/p31-remove-fault-20261019t144938z/report.json)：现场`Code:`20字节在解压镜像中只有一个精确匹配。故障PC=`c04fd650`，实际指令`e5930008 / ldr r0,[r3,#8]`，现场r3=0，故障地址0x8。
- 前序指令从st+0x2c0读设备、调用`put_device`，再从设备+0x50读driver、从driver+8读owner。[最后只读检查](../../results/p31-end-state-20261019t145151z/report.json)中的运行时kallsyms也确认`axiadc_remove=c04fd5f0`、`put_device=c03a45a4`、`module_put=c01775c0`，与反汇编调用位置对应。

这将直接故障定位从源码猜测推进到了现场寄存器、原厂二进制和运行符号的交叉证据；**仍没有复现精确dirty源树/完整构建配置，也没有修复后的内核实验**。不能只给915行加NULL判断就宣称生命周期和卸载顺序已正确；需要匹配构建、引用配对、失败路径与提供者/消费者顺序一起修复。本轮没有编译或替换内核。

同包 `dma-axi-dmac.c` 读取资源后映射，最高显式寄存器偏移0x438，提供4KiB窗口可容纳这些寄存器的源码依据；这不替代当前目标内核的探测/传输验收。

## 已部署的最小规避措施

1. `board/boot/S99board`仍先开风扇；检查已有任意overlay或已存在RF IIO设备时，在复制位流/写FPGA之前拒绝重复启动。
2. 初始化仅应用一次。PHY/ADC/DDS不完整时明确失败，**全部自动移除/rebind重试已停用**，包括没有IIO名字的失败探测，避免猜测“没就绪就一定可卸载”。这会放弃旧的自动恢复机会，冷启动0xFF需要新一轮启动，不能再宣传三次自动重试。
3. `--check-rf`仍只读且按名字验收。15项针对测试执行真实shell源，包括部分探测、重复启动、位流文件不被改写、失败可见；没有实际重现内核崩溃作为测试。
4. 原版备份在新板`/etc/p31-S99board-before-20261019T143146Z`，不在`/etc/rcS.d/S*`自动执行集合中。新脚本通过RAM传输/板端语法检查/备份哈希/隐藏临时文件/原子替换/执行位/同步及读回校验安装。
5. `experiments/p31_test_rf_overlay.py`已替换为无串口访问、直接退出2的禁用入口，没有force选项。原故障程序只作证据，不作为可执行恢复步骤。

证据：[15项测试](../../results/p31-boot-guard-20261019t142948z/report.json)、[安装与备份](../../results/p31-boot-guard-deploy-20261019t143146z/report.json)、[完整正常重启](../../results/p31-guard-boot-20261019t144337z/report.json)。安装时没有执行start；所有数据先存电脑，再正常sync/reboot，boot_id由49491e56…变为ebce10b9…，新脚本实际执行、一次apply成功、三个RF设备就绪、tainted=0。没有故意制造硬件失败来触发保护，失败分支仍只有主机测试证据；冷启动0xFF根因未解决。

## 离线设备树推进

原厂RF/显示DTBO和基础DTB已从新板读回，板端与电脑SHA一致，见[板端契约采集](../../results/p31-board-contract-20261019t135528z/report.json)。原厂DTB没有被修改。

隔离安装DTC 1.8.1及其原生libfdt，官方MSYS2包和哈希留存在[工具记录](../../results/p31-dtc-tools-20261019t135813z/report.json)，位置`E:\FPGA_Tools\Utilities\dtc-1.8.1-ucrt64`。没有全局替换系统工具。

候选源码为[rf-display-800x480.dts](../../fpga/integration/rf-display-800x480.dts)。相对原厂分别组合的契约，主要调整：

- 两个RF DMA窗口由64KiB纠正到实际4KiB解码，DMA AXI时钟由FCLK1索引16纠正为FCLK0索引15。
- ClockWiz输入与控制口分开描述：输入FCLK0/100MHz，AXI控制FCLK1/200MHz，不能把所有显示相关时钟都视为200MHz。VDMA五路时钟仍为FCLK1。
- 保留视频IRQ In0..3，RF TX/RX In12/13对应GIC SPI56/57；保留GPIO、触摸与800×480配置。
- firmware-name使用新的`rf-display-p31.bin`，当前没有生成或安装这个位流。

[最终240项报告](../../results/p31-overlay-20261019t141549z/report.json)、[30项独立核对和4种负例](../../results/p31-contract-verification-20261019t143056z/report.json)。保留原厂结构告警，不把DTC编译成功说成目标驱动通过。TTC PWM与基础timer资源所有权、旧VDMA clock-name兼容性、TPG后续控制驱动，以及当前内核4KiB DMA兼容性仍需目标验证。

原生`fdtoverlay.exe`第一次出现4096/20480字节短读，保留`p31-overlay-20261019T140237Z`；随后使用同一固定版本的原生libfdt、明确二进制缓冲区执行check/open_into/overlay_apply/pack/check_full，成功完成电脑端应用，不是自写模型替代。之前Windows控制台文本IO路径不作通过依据。

## CDC、复位和时序的有限证据

- [FIFO原生XSim](../../results/p31-fifo-test-20261019t140637z/report.json)：1槽40位、1槽1位、128深64位，各两个非整数时钟比例。每种4次协调复位，复位丢弃的在途数据单独处理；总36005次核对、零不匹配。
- [仲裁器原生XSim](../../results/p31-arbiter-test-20261019t141159z/report.json)：实际`dmac_request_arb`与依赖RTL，ASYNC=1、AXIS/AXIS，长度1..256拍、多轮3位ID回绕、随机/长回压、TLAST/EOT及排空停机。两个案例各128描述符、5439数据拍。
- 两者均保留原厂文件和SHA。它们不模拟模拟亚稳态、不替代布局位置/时钟偏斜，也未覆盖本工程实际FIFO/MM端点、运行中abort/re-enable/resync。**58项CDC Critical没有被清零或豁免。** 当前bench注释已纠正“MM端点另已测试”的不实表述，仅注释变化，实际执行源副本仍在结果目录。
- 未修改`sync_id`组合逻辑、复位和BUFGMUX_CTRL拓扑。要改跨域控制，先补实际端点和abort/resync验收，不能把功能仿真通过用作任意寄存器插入的依据。
- [时序资料提取](../../results/p31-timing-sources-20261019t140648z/report.json)保留AD9361与接口资料及TL070A资料选页。芯片端时序不包含载板走线/可调延时状态；面板精确型号及时序仍缺。没有编造外部输入输出时延，P30的7个input/66个output未约束问题仍在。

仿真中的timescale缺失、强制full覆盖不足和2021.1 Verilog前向localparam解析错误均留档；最终只对实际通过案例作结论。内核源码第一次解包工具错误地假定外层目录，选错Makefile；`p31-vendor-kernel-20261019T143309Z`不可作源码验收依据，最终版本增加必需文件校验，使用143355Z。

反汇编第一次误选旧Windows ARM工具路径，启动时报WinError1392；`p31-remove-fault-20261019T144633Z/failure.json`保留失败说明与已提取字节。随后使用项目已校验的ARM GNU8.3工具，经WSL实际反汇编通过，未修复或替换原工具目录。

## 两次恢复后的数据与最终状态

- [RX参数恢复](../../results/p26-rx-profile-restore-20261019t143009z/report.json)：改写仅manual、0dB、2450MHz三项，其余读回符合已审查配置。
- [新16缓冲自检](../../results/p27-smoke-20261019t143227z/report.json)：2通道、16×65536原始帧，约0.034252336秒；每块保存1024帧，保留率1.5625%，不是完整数据。
- [65536字节回收](../../results/p30-smoke-archive-20261019t143355z/report.json)：SHA256=`b5fc07613e6f5f220b40b3efb726717f3bfa7fa344622027c9a51a7c16fa86e9`。
- [第一次恢复检查](../../results/p31-end-state-20261019t143602z/report.json)为用户重新上电后的49491e56…会话，保留历史作用域。
- 正常重启验证后，再次[恢复RX参数](../../results/p26-rx-profile-restore-20261019t144504z/report.json)并完成[新16缓冲采样](../../results/p27-smoke-20261019t144510z/report.json)，约0.034243920秒。
- 第二次整文件回传在[144633Z报告](../../results/p30-smoke-archive-20261019t144633z/report.json)被严格base64校验拒绝。实际少35个编码字符，不代表采集文件损坏，也没有把残缺数据接受为成功。
- 新增只读小块回传：每块4096字节、单独板端SHA、最多3次重传，最终全文件再核对。此次16块全部首次通过，[回收报告](../../results/p31-sparse-archive-20261019t145054z/report.json)，65536字节SHA256=`00cf87fabf1729aa69ca857f31811e6996a28936b9ccb11ca57feeb47c8e5bdb`，保留率仍1.5625%，仍不是完整连续IQ。
- [最终只读检查](../../results/p31-end-state-20261019t145151z/report.json)：旧板boot_id仍为`6d5cb873-e976-4c91-9d37-3227445de891`，RAM stage仍在`/tmp/p12-source-stage-p30-132637`，inspect通过、未观察到TX程序；新板boot_id为`ebce10b9-e464-4b4c-b586-d4fd8d116e06`，RF模式、接收缓冲/scan关闭、保护脚本哈希正确、tainted=0。

本轮未启动任何TX应用；原厂启动/probe内部校准期间是否存在瞬态物理发射没有测量。源代码、位流原件和启动包未替换；只有上述启动脚本规避措施持久化、RX参数恢复及RAM诊断工具上传。

## 下一步按依赖排序

1. 保持热卸载禁用。先核对运行内核与供应源码/配置/工具链；准备只在新启动、尚无绑定驱动时应用一次候选的方案，失败用下次原厂启动恢复。不能在现有RF工作会话卸载overlay“试试”。
2. 完成4KiB DMA目标驱动探测/传输、ClockWiz驱动绑定、TTC PWM资源和VDMA命名兼容验证；这几项仍是设备树上板门槛。
3. 补实际FIFO/MM端点、abort/resync/独立复位仿真及58项CDC路径分类；核对精确显示屏与载板走线时序，再决定RTL与约束修改。
4. 上述门槛通过后才生成配对位流/设备树，分别验收RF、屏幕、触摸及并行工作；现有`E:\p30c-1019-174235\merged-route.dcp`保持为离线基线。
5. 再推进完整连续采集、已知信号/指标精度、真实数据AI与独立终端整机验收。不得把本次稀疏自检输入AI当作连续波形。

电脑文件已保存；RAM目录断电会丢失。停止实验后先正常关机再断电，保留`results/`和E盘工作副本，Git本身不包含这些结果。

## 用户要求收工后的最终更新

2026-10-19 23:00左右（北京时间），用户要求停止并保存。再次只读确认两板空闲、同步两板文件系统，随后执行普通poweroff；[日志](../../results/session-poweroff-20261019t150029z/report.json)确认两块板均到达`System halted`。未移除工作overlay，没有新增采集或发射实验。电脑继续运行，板卡现可断开电源。

停机前最后只读检查见[145901Z](../../results/p31-end-state-20261019t145901z/report.json)，恢复步骤见[收工说明](../handoff/stop-20261019.md)。当前机器状态以`session_stop`为准，`p31_current`及本记录中的boot_id/参数均保留停机前会话的历史作用域。
