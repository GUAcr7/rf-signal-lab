# EXP-P06：恢复连接与 Vivado 2021.1 管理员安装

日期：2026-10-10，Asia/Shanghai。此记录补充 EXP-P06，不替代已有验收。

## 授权和边界

用户确认板卡已连接，并授权继续及管理员权限安装 Vivado。复用已核验的完整离线包，不重复下载。安装目标为 Vivado ML Standard 2021.1、Zynq-7000，根目录 `E:\FPGA_Tools\Xilinx`。本次不升级工程/IP、不烧写固件、不发射射频。

已读取电脑操作技能及其指导：Windows 权限确认框由用户确认；工具不代点 UAC，也不修改执行策略。使用正常 `RunAs` 启动固定用途脚本，不提供任意管理员命令队列。

## 板卡恢复检查：通过

23:38 通过 `ip:192.168.2.1` 实际读取 IIO：型号 `PUZHI PZSDR P201`，`ad9361-phy` 与 `cf-ad9361-lpc` 存在，I/Q 为 `voltage0/voltage1`，有符号 12 位数据、16 位存储、小端。取得 1024 个新复数样本，均为有限整数计数，964 个不同值；保存、回读及 SHA256 核对通过。

配置：采样率 30.72 MS/s，RX LO 2400 MHz，RF 带宽 18 MHz，`slow_attack`，增益回读 71 dB。前后射频配置、BIST/loopback 与 DDS scale 回读一致，接收上下文已释放。未写射频属性、未开启 TX。

证据：[recovery-verification.json](../../results/p06-resume-20261010t153701006116z/recovery-verification.json)、[RECOVERY.md](../../results/p06-resume-20261010t153701006116z/recovery.md) 和同目录 `short-rx/monitor.npz`、`short-rx/report.json`。

这只验证短接收链路；无缝采集、已知目标射频精度、AI 识别、ARM 应用运行仍待验证。SSH 端口可达且服务器为 Dropbear，但严格主机密钥检查尚未建立可信记录；没有写 known_hosts 或试用密码。

## 安装准备与管理员启动：通过

完整安装包及 Windows 解压树复用上一记录，不重复扫描 50 GB 归档。原窗口 PID 2600 位于产品选择页；一次操作尝试后画面未改变，因此改用随包官方批量安装接口。

官方入口与选项静态核对见 [cli-options.json](../../results/p06-admin-install-20261010/cli-options.json)。`ConfigGen` 支持产品/版本/目录参数，生成配置默认写入提升用户的 `.Xilinx/install_config.txt`，`-c` 用于安装时读取配置，不是配置生成输出路径。仅查看该已知配置文件，不访问账号或令牌存储。

23:47:13 `RunAs` 启动管理员 PowerShell PID 37836；worker 的管理员 token 校验已通过、官方 xsetup 签名为 Valid/Xilinx。随后重新核对 PID 2600 的准确路径与产品选择页标题，仅关闭这个尚未安装的旧实例。未修改执行策略或系统 PATH。

固定脚本：`E:\FPGA_Tools\Work\p06-admin-install-20261010\admin-install-worker.ps1`。启动时 SHA256 为 `a20ee76ded1e689e6b593ba5a87ee20674c5010a7559762378a18b2802af97c4`，PowerShell 解析错误 0。代码经独立审查；实际模板还需核对后才允许安装。范围门槛包括产品/版本/目录、配置哈希、模块白名单和禁用附加驱动/交互许可证选项。

启动证据：[uac-launch.json](../../results/p06-admin-install-20261010/uac-launch.json)、脚本副本；实时状态与 CLI 日志位于 E 盘上述工作目录。

## 当前验收

| 项目 | 结果 | 依据 |
| --- | --- | --- |
| 板卡恢复并读取新的 I/Q | 通过 | 新样本、回读、配置前后比较 |
| 现有离线包复用 | 通过 | 前次 SHA256、解压与入口签名记录 |
| 管理员进程启动 | 通过 | RunAs 返回 PID、worker 权限检查通过 |
| 官方组件配置生成 | 通过 | 23:49:35，ConfigGen 退出码 0，实际模板和最终选择已核对 |
| Vivado 安装与版本启动 | 通过，附安装后清理异常 | 官方安装 exit 0；实际 `-version` exit 0、版本 2021.1；详情见下文 |
| 原厂 FPGA 综合/实现产物 | 通过构建；完整时序未通过 | 8 阶段退出 0，bit/XSA/DCP 已保存；PS 时钟覆盖与违规见 10 月 11 日追加记录 |

修改前 EXP-P06 与实施指南已备份到 `results/p06-admin-install-20261010`。未改 Git index；已有 439 项 Python 回归结果为前次结果，本次未重复运行。后续实际进展继续补充此记录。

## 23:51：已核对配置，官方安装命令启动

实际模板明确 `Product=Vivado`、`Edition=Vivado ML Standard`、`Destination=E:/FPGA_Tools/Xilinx`。模板没有独立的 Vivado 核心组件开关；保留完整原模块列表，仅 `Zynq-7000:1`，其他器件、DocNav、Vitis Model Composer 均为 0，不添加虚构模块。

原模板 WinPCap 与 Cable Drivers 均为 0，完整选项名称和禁用值原样保留。保留当前用户开始菜单和桌面快捷方式，将文件关联设为 0；保留安装器的磁盘优化和官方空间检查。生成模板 SHA256 为 `0a5046058641fc9a6afc739160a77c9d2310c4d796669c5cd8740cf8086758f5`，最终配置为 `715bbd63df3a9271648dfb9402ee4d868af6c71db0bb394bf175b29d3aef3205`。

23:51:10 发布固定安装动作及配置哈希，worker 重新核对产品/版本/目录/模块/选项/哈希后于 23:51:11 进入 `installation_command_starting`，已调用官方 `-b Install`。启动时 E 盘 72,721,145,856 bytes 可用；40 GiB 是脚本的保守最低门槛，不是厂商计算的组件需求。实际组件所需空间仍由官方安装程序校验。

状态只说明安装命令已启动，不能作为安装完成、工具可用或原厂工程可构建的依据。现阶段保留日志并等待实际退出码和工具启动验证。

另外修复构建包装脚本的日志与退出码检查：调用前清空旧退出码，日志写入失败立即报错，空退出码不判通过。原厂 HDL/Tcl 源码未修改，包装脚本原版备份在本次结果目录；构建尚未运行。

## 2026-10-11 00:01～00:07：工具安装完成，预检通过

00:01:01 官方安装完成，退出码 0，工具入口为 `E:\FPGA_Tools\Xilinx\Vivado\2021.1\bin\vivado.bat`。00:02 左右实际 `-version` 返回 0，输出 `Vivado v2021.1 (64-bit)`、SW Build 3247384、IP Build 3246043；日志与 JSON 已保存在本次结果目录。安装结束 E 盘约 26.55 GiB 可用。

官方日志同时报告两个安装后任务异常：正斜杠目标路径被旧 Windows 后处理拼接为 `E:\/FPGA_Tools/...`，导致 `xw31.dat → instRecordWt.dat` 复制、`devint/vault` 清理各退出 1。不是名为 FPGA_Tools 的组件解包失败。00:05:51 以正常路径补齐原本应复制的安装标记，源/目标 SHA256 都是 `3e41329622004c84dd5b9a02669aca2c0aa36fe00c4cb177ef695c09196dd425`；未改变统计收集设置。清理未重跑，原目录保留；见 `post-install-marker-repair.json`、`xinstall.log` 与 `installation.log`。不据版本输出宣布全部后处理正常。

首次构建包装调用在规范化路径时发生正则表达式错误，尚未启动 Vivado；已保留 `first-build-startup-failure.json`，改用字面字符串替换。函数中的原生退出码也改为显式全局读取，真实模拟 exit 0 和 exit 7 均正确捕获，见 `native-exit-scope-check.json`。启动/日志异常仍记录失败阶段，记录写入失败时也无条件恢复临时 ADI 环境。

在新副本 `p06-pzp201-20261011a` 上实际预检确认版本与器件可用，但 IP 查询因提前关闭项目报 `No open project`；退出 1 的完整阶段记录保留在 `failed-preflight-000618`。修正为先默认工程冒烟，再创建目标器件的内存工程查询 IP，保留失败现场，再建立新副本 `p06-pzp201-20261011b`；两次新副本均为 138 个文件、全部尺寸/SHA256 匹配，不覆盖原工作区。

00:07:47 新预检退出 0：精确版本 2021.1、目标 `xc7z020clg400-2` 存在；无显式 part 的默认工程可创建，默认器件 `xc7z010iclg225-1L`。所需 processing_system7、axi_interconnect、axi_quad_spi、axi_iic、proc_sys_reset、xlconcat、xlconstant、xlslice、util_vector_logic、fir_compiler 共 10 项已安装；FIR Compiler 为 7.2。只确认目录和工程创建，不等于许可/综合/时序通过。

原厂库包装随后已开始，当前工作日志为 `E:\FPGA_Tools\Work\p06-pzp201-20261011b\build-20261011-000740-5c51ba`。未升级原厂 IP 或写入板卡；全部完成情况以后续退出码和产物为准。

## 00:11：停止环境参数诊断构建，修复后重跑

独立审查和实际库日志发现，当前 PowerShell 7.6.5/.NET 10 对 `SetEnvironmentVariable(name, null)` 的行为保留了空变量。原厂 Tcl 依据“变量是否存在”判断开关，导致空 `REQUIRED_VIVADO_VERSION`、存在的 `ADI_IGNORE_VERSION_CHECK` 意外降级原版本检查，空 `ADI_GHDL_DIR` 指向 `e:/library`。压缩/报告/XPA 等可选开关也存在同类风险。虽然工具版本已严格预检为 2021.1，仍不能将这轮登记为厂家默认基线。

因此在最后一个库 `util_upack2` 包装时，重新核对 PID 35988 的准确 exe 和本次日志路径后仅终止该诊断进程。前五个包装阶段退出 0，最后阶段因主控停止退出 -1；没有进入原厂系统工程综合/实现。所有日志、阶段记录与 `diagnostic-build-stopped.json` 保留；未清理或覆盖工作区。

入口改为通过环境 provider 真正删除可选覆盖项，明确设置 `REQUIRED_VIVADO_VERSION=2021.1`；恢复时区分原本存在和不存在。预检新增子进程内 Tcl 的“可选参数必须不存在、版本参数准确”检查，避免只相信主机赋值语句。新的 `p06-pzp201-20261011c` 再次独立核对 138 个源码哈希后重跑，源代码仍未修改。

## 2026-10-11 00:54 完成原厂构建；11:52 后复核实际产物

正式干净副本 C 的工具预检、六个 ADI 库包装、原厂系统工程共 8 阶段全部退出 0。原系统综合、布局布线和位流生成完成；bit 为 2,339,252 bytes，XSA 为 851,553 bytes，routed DCP 为 15,517,179 bytes。XSA 的 ZIP CRC 通过，其中内嵌位流与独立 bit 的 SHA256 相同。完整产物/日志/报告/来源指纹已保存到 `results/p06-vendor-build-20261011`，汇总见 `audit.json`。没有加载新位流、替换 BOOT 或烧写 flash/SD。

原厂留存的 138 文件仍全部符合原归档 SHA256；工作区的自动生成 `library/axi_ad9361/bd/bd.tcl` 在 IP 包装时被原脚本重生成，仅 LF 变为 CRLF，规范化换行后文字相同。两份字节及审查结果分开保留，不再声称构建后所有工作文件字节都未变化。

实际放置资源：LUT 11,924/53,200（22.41%），FF 20,791/106,400（19.54%），DSP 72/220（32.73%），BRAM 2/140（1.43%）；29,110 个可布线网络全部完成、路由错误 0。Synthesis/Implementation 许可实际取得，FIR IP 综合与位流生成已运行，不再只是 IP 目录可见。

**完整时序不能验收。** 原约束下 WNS +7.729 ns、WHS +0.043 ns，但只有 `rx_clk`；有 7,909 个无时钟 pin、20,228 个未约束内部端点、16 个无输入延迟和20个无输出延迟。原 `system_project.tcl` 明确禁用了生成的 PS7 XDC，该 XDC 本应定义 FCLK0 100 MHz、FCLK1 200 MHz，因此不是安装器漏装时钟 IP。

在原 routed DCP 的独立内存诊断中，仅补入这两个原配置证明的时钟与原 XDC jitter，没有增加 false path/异步组或覆盖源文件/产物。无时钟/未约束内部端点降为 0，但 100 MHz 域出现 setup −14.695 ns、hold −0.170 ns；最差 setup 是复位网，数据路径 24.118 ns、其中路由 23.634 ns。200 MHz 域 +3.846/+0.159 ns，RX +7.729/+0.043 ns。CDC 报告有待审查的 Critical/Warning，外部 I/O 约束也仍不完整。诊断汇总、前后检查、跨时钟报告保存于 `clock-audit/`；这是分析，不是已完成修正/重新实现/上板验收。

## 12:03：现有固件短接收复核通过

再次取得新的 1024 点 I/Q，954 个不同复数样本，有限整数格式、NPZ SHA256、保存/回读及上下文释放均通过；配置前后未变（AGC 增益允许自主变化）。PHY 30.72 MS/s、LO 2400 MHz、RF BW 18 MHz、slow_attack 71 dB；BIST/loopback/DDS scale 均为 0。本次未写 RF/TX 属性。见 `results/p06-postbuild-rx-20261011/recovery-verification.json` 和 `short-rx/`。

这验证的是**板卡原有固件**继续可接收，不是新 bit 已运行，也不证明无缝连续数据、已知目标或绝对功率。

## 12:04～12:09：补齐 Digilent 支持，JTAG 身份核对通过

第一次 JTAG 枚举目标数 0，同时 hw_server 报缺少 `dpcomm.dll/djtg.dll`；安装 Vivado 时这部分附加支持原为未选。用户已有管理员安装与继续工作的授权，遂使用官方 `install_drivers.cmd` 已有参数，仅安装 Digilent，禁用 PCUSB 和 SmartLynq。固定 worker 检查管理员 token、官方入口 SHA256、安装器 SHA256 与 Valid/Digilent 签名，没有执行策略/安全设置更改或任意管理员命令队列。正常 RunAs 于12:06:06启动，12:06:15官方安装退出0，Adept Runtime 2.18.2。日志保留 `Driver installation: 40000102` 原文，单凭该编号不推断驱动含义；以后续实际枚举为依据。

复测发现唯一目标 `Digilent/210203859289A`。随后严格匹配这个已枚举的串号，仅打开 JTAG 目标读取身份，得到 `arm_dap_0` 和 `xc7z020_1`，PART 分别为 arm_dap 与 xc7z020，退出0；未编程、复位、halt CPU、访问地址空间或刷新 probes。不能从 IDCODE 推断封装/速度等级。证据分别在 `results/p06-digilent-install-20261011`、`p06-jtag-discovery-before-drivers-20261011`、`p06-jtag-discovery-after-drivers-20261011`、`p06-jtag-chip-identity-20261011`。

## P07a 的独立推进

实际综合发现原 FIR 的100 MHz内部估计失败（−5.153 ns），增加一拍保存最后乘加，再作舍入/饱和；18组72,356输出与默认系数1086输出复测通过，新内部综合估计+1.866/+0.246 ns，LUT731/FF1631/DSP2/BRAM0。未接原厂数据通路、实现或上板。周期从65拍/输入变为66拍/输入，详细记录见 [FIR时序修正](exp-p07a-timing-20261011.md)。

## 12:19～12:22：补齐 PS 时钟的独立实现实验

从原厂 `system_top_opt.dcp` 建立全新派生实验，仅补入前述原配置证明的 FCLK0/FCLK1 时钟和 jitter，重新 `place_design → phys_opt_design → route_design`。不改原厂 HDL、原检查点、现有固件，不新增 false path 或异步时钟组；没有生成 bit/XSA 或访问板卡。工具退出0不等于时序验收。

实际 29,122 个可布线网络全部完成、路由错误0；LUT11,937、FF20,791、DSP72、BRAM2。无时钟 pin 和未约束内部端点均为0；外部输入/输出缺少延迟约束仍为16/20。

全局 WNS −4.397 ns、WHS +0.052 ns，setup 未通过、hold 无违规。100 MHz 内部 WNS −1.308 ns，较原 routed DCP 补时钟诊断的 −14.695 ns 改善；最差内部路径仍为复位到 AD9361 控制寄存器，10.368 ns 数据延迟中9.884 ns来自路由。200 MHz内部 WNS +3.754 ns、RX内部 +5.544 ns。全局最差路径是 RX→FCLK0；时钟交互报告仍列出两方向 `No Common Clock`/部分不安全例外，不能为获得正余量而直接屏蔽。

结论：**时钟覆盖与重新实现实验已完成；完整时序/CDC/I/O验收未通过。** 后续需审查高扇出复位和跨域设计、完整外部接口约束与实际时钟配置，再作有依据的修正。证据完整保留于 [派生实现](../../results/p06-ps-clock-implementation-20261011/run-record.json)及其 `reports/`，不是可直接替换当前 BOOT 的版本。

## 12:20：PHY 与 ADC 采样率只读核对

实际 `ad9361-phy` 接收通道和 `cf-ad9361-lpc` 四个扫描通道均报告30,720,000 Hz。后者列出的可选值为30,720,000和3,840,000 Hz；本次没有切换、启动新buffer或写任何属性。当前采样元数据的30.72 MS/s获得了接收设备读数的额外支持；仍不能据可选列表证明某条硬件FIR正在启用或无缝持续采样。

脚本 [p06_read_sampling_attributes.py](../../experiments/p06_read_sampling_attributes.py)，证据 [sampling-attributes](../../results/p06-sampling-attributes-20261011.json)。

## 12:34～12:35：ARM 编译工具与可传输测试包完成

官方Arm GNU-A8.3包断点续传、MD5核对及隔离解包通过，复用已有Ubuntu-24.04/WSL。首次解包180秒超时的现场保留，新目录延长时限后完成；没有使用部分工具链、安装Vitis或更改PATH。三个C程序实际交叉编译通过，为Cortex-A9 ARMv7小端EABI5 hard-float，只依赖libc/GLIBC_2.4，尚未在板端运行。

准备的18组ARM离线测试包包含程序、输入、参考CSV和校验清单，计划含重置重放144,712个输出。82文件校验、ZIP CRC和Shell语法通过，程序未在ARM上执行；板端登录、实际libc和临时执行目录仍需核实。完整来源、失败/修正与验收边界见 [ARM编译实验](exp-p06-arm-cross-20261011.md)。
