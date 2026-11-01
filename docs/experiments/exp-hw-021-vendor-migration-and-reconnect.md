# EXP-HW-021：重连恢复与 RF/显示独立原厂工程迁移

- 日期：2026-10-19；截止 17:21:33 +0800。
- 结论：**两份 XC7Z100 独立工程已在 Vivado 2021.1 完成综合；没有完成合并、布局布线时序验收或新位流上板。**
- 本轮未发射射频。保留 D 盘原件、失败尝试和前轮真实 RF 证据；没有修改信号处理/AI 算法或自研 RTL。
- 被测版本为现有未提交工作区；各阶段归档实际 Tcl/脚本哈希、原厂源清单与编译日志，不用一个不含这些未提交文件的 HEAD 冒充被测提交。

## 板卡重新连接后的实测

1. 枚举并按 Linux 身份确认旧 COM9=PZSDR P201、新 COM8=TLZ7xH-EVM。旧板已重启回到 getty，先用已记录的默认账号登录；仅见 banner 的早期识别启发式曾返回 false，之后实际 uname/命令返回码确认登录成功。重连证据在 `results/p29-reconnect-20261019T081632Z/` 与 `results/p29-board-status-20261019T081712Z/`。
2. 新板 `/etc/board-mode=rf`，但只有 XADC。完整启动日志显示 AD9361 在 **真实 attempt 1/2/3 都读出 PRODUCT_ID 0xFF，最终退出失败**。因此前轮未覆盖的实际重试/耗尽分支今天确实发生；它没有自动恢复成功。证据：`results/p29-rf-startup-diagnosis-20261019T081802Z/report.json`。
3. 保存位流/overlay/启动脚本信息后，只重绑定一次原厂 `pl` overlay，未换位流、未重启。即时检查过早曾返回未就绪；后续日志与独立检查确认 PHY、ADC、DDS 均出现。**只能判定这次开机后可恢复，不能宣布冷启动问题已修复。** 证据：`results/p29-rf-rebind-20261019T081902Z/` 与 `results/p29-rf-rebind-check-20261019T081930Z/`。
4. 备份运行属性后，仅恢复此前已验证的 RX `manual / 0 dB / LO 2450 MHz`，读回 Fs 30.72 MS/s、BW 18 MHz、A_BALANCED。没有写 TX 或改变采样率。证据：`results/p26-rx-profile-restore-20261019T082645Z/report.json`。
5. 复用已验证的 ARM 原生程序，16 DMA 缓冲接收/释放通过，搬运 1,048,576 帧，保存 16,384 帧，约 0.03424 s；**只保留 1.5625% 稀疏诊断样本，来源未知，不是新已知源链路/AI/无丢样验收**。电脑回收到 65,536 B，SHA256 `43425ba31b13b72b6be61fa9ff765a6f78c873a67ba8330ddc2a073039392873` 与板端一致。
6. 最后再次确认两板身份、旧板无活动 TX、新板 RF 三设备检查通过。串口已释放。旧 TX 临时包本轮未恢复；不能直接运行昨日 `/tmp` 路径。风扇 gpio914 读 0 是既有读回限制，不能据此断定停转。

启动日志还存在 EXT4/FAT 非正常卸载恢复信息；未对已挂载文件系统运行修复工具。关机继续按既有 sync/正常关机流程，诊断字节现已存电脑。

## 迁移实施与纠错

- 独立 E 盘目录：`E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z`。只提取新板显示工程子目录及 ADI 源码，不修改 D 盘包。
- RF `system_bd.tcl` 的 2017.4 版本声明在副本改为 2021.1 后，仍必须实际生成 IP、验证 BD 和完整综合，不能把更改版本号当兼容证明。
- 初次 ADI 封装失败：旧 helper 按绝对路径重排已被 packager 登记为相对路径的 XDC。适配为按规范路径复用文件并用存储名称重排；保留 XDC 原内容和 SCOPED_TO_REF。随后 **11 个 IP 全部封装通过**。
- 独立源核验覆盖 1235 个初始文件记录。D 盘原件/压缩包哈希不变，RF 副本 HDL/XDC 与原件相同；显示手写源核验 57 项，无改动。11 项 XDC/TTCL 引用全部存在，无同 fileset 重复项，AD9361 的 5 个 XDC 作用域保留。IP 元数据/生成目录允许按工具重建，逐项变化有存档。
- 显示首轮错误地升级互连内部 xbar/auto_pc，验证拒绝；改为只从顶层 IP 升级。v2 BD 验证通过后门禁退出 32，保留 22 项关键元数据差异供审查。最终 v3 只允许已检查的精确差异，PS7/外设窗口不漂移，结构验收通过。
- 一次显示打开遇到安装目录 Tcl 读取错误，原始失败保留；RF 综合结束后单独重试成功。根因未证实，后续重任务串行执行，不据此修改安装文件。
- 显示第一轮综合遇到明确的 Windows 长路径错误 `IMPL 213-66`，导致后续找不到 TPG 模块；没有删掉 TPG 或改功能。完整复制到短路径 `E:/p29d-1019`，源文件哈希一致，只重置失败 TPG 和顶层运行后重试。原始失败在 `results/p29-display-synth-20261019T084313Z/`，复制清单在 `results/p29-short-display-20261019T085219Z/`。
- 短路径重试进一步暴露 `core_revision 2610191655` 超出 32 位有符号整数的 Y2K22 故障。按 AMD AR76960，从官方文档附件 API 下载 3988 B 补丁 ZIP，记录下载 URL/哈希并检查内容；用工具自带 Python 安装，读回确认 Vivado 与 Vitis_HLS 两处补丁文件均与下载字节一致，原 `automg.tcl` 哈希不变。**未修改系统时间、许可证、工程算法或工具原脚本**；只添加官方补丁与安装日志。补丁后新进程实际重试综合，不能仅凭安装脚本退出 0 判定成功。
- 显示升级包含 Clocking Wizard 5.4→6.0、VTC 6.1→6.2、TPG 7.0→8.1；**8 项 VTC 默认参数及新增端口的功能影响尚未上板/仿真核验**，已记录门禁标识。

## 完整综合结果与验收边界

| 独立工程 | LUT | 寄存器 | BRAM Tile | DSP | 综合 WNS/ns | 综合 WHS/ns |
|---|---:|---:|---:|---:|---:|---:|
| rf | 10581 | 19790 | 4 | 60 | +1.294 | -0.095 |
| display | 11037 | 15623 | 8.5 | 9 | +1.200 | -0.095 |

这是独立原厂工程，不包含项目 FFT/AI/合并链路。资源不能直接相加作为合并后的实测数。

- RF 综合：no_clock=0、unconstrained_internal_endpoints=0，但 **7 个输入、10 个输出缺接口时延约束**；综合 WHS 为负，不能称为时序通过。个别 IP 的 OOC 日志有时钟分组查询警告，主工程综合退出 0 不会消除这些记录。
- 保持时间以布局布线后结果为准；本轮没有用放宽周期或删除约束使报告变绿。`audit` 保存 DRC、CDC、IO、时钟与时钟交互报告；这些报告是后续修复输入，不等于所有检查通过。
- 显示的具体约束/CDC/DRC 数量见原始审查报告与机器报告。最终 DCP 已随 [交付记录](../../results/p29-delivery-20261019t092133z/report.json) 存电脑；DCP 不是可烧写位流。
- RF CDC 汇总有 **59 条 Critical、1775 条 Warning**；显示补充时钟后仍有 2 条 CDC Warning。它们是结构工具发现项，不自动等同于实际硬件失效；但未逐项审查设计意图与已有例外前不能豁免或称 CDC 通过。DRC 基线 RF 为 17 条 Warning/56 条 Advisory，显示为 40 条 Warning/2 条 Advisory，没有把报告生成退出 0 写成零问题。
- 本轮未创建新的自研 RTL 功能模块，适用验证是原厂设计的迁移/完整综合/报告审查。将来新增/合并自研 RTL 仍需项目规定的自检 TestBench；本轮不冒称模块功能仿真通过。
- 上轮 **864 passed** 保持为历史回归；本轮未改算法，未重跑或虚报新的全回归数量。

## 已修复的显示二分频时钟模型

检查发现原厂 `parity_flag` 翻转触发器的输出被用作 LVDS 时钟，但缺派生时钟声明。先对原厂未改 RTL 与原生 UNISIM BUFG 模型运行自检：**35 个完整二分频周期、3 次异步复位、74 个有效输入周期通过**；范围仅为时钟/复位，不包含完整 RGB 映射与面板电气。

新增 `fpga/constraints/display_lvds_half_clock.xdc` 与 `fpga/tb/tb_display_half_clock.sv`，把约束加入短路径工程副本并完整重综合。实际像素时钟周期 **6.734 ns**，派生时钟 **13.468 ns**；没有改主时钟周期或删除路径。**no_clock 21→0，unconstrained_internal_endpoints 65→0**。

补充后的综合 WNS=+1.200 ns，WHS=-1.221 ns；56 个输出仍缺外部时延。保持时间变差反映原先漏检的路径被纳入分析，不能回删约束掩盖它。`display-clock-reviewed.dcp` 保留新结果，原 `display-synth.dcp` 保留修补前基线，尚未布局布线/上板。

## 合并规划与未完成工作

[合并核对表](../design/rf-display-integration-20261019.md) 已给出地址/DDR 端口/时钟/PS 配置依赖。静态检查共有 108 项双方显式 PS 参数值不同，显式引脚分配直接重复为 0；缺省字段、隐式差分负脚、IO bank 电压仍须另查。

两套资料中预编译 `fsbl.elf` 和 `BOOT.BIN` 分别逐字节相同；源码包根 `ps7_init.c` 已提取供审查，但没有据此认定它就是预编译 ELF 的构建输入，也尚未识别当前实际启动分区内的 BOOT 字节。此结果支持保留已工作的启动链，不能支持从 RF 的通用 PS 配置重新生成启动包。

另对新板 10 个 SLCR 字做了只读采集，没有写寄存器。与两份 IP 生成的 PS-init 掩码比较：显示匹配 **5/10**，RF 匹配 **2/9**（另一字未写，不能判匹配）。显示 4 个 FCLK 控制字匹配，但若干 MIO 不匹配；Linux 可在启动后修改这些寄存器，不能从这个局部对照推导完整启动初始化。RF 使用 SPI1，触摸使用 SPI0；EMIO[0] 与 RF[46:32]/[47:48] 的规划已核对源码，合并仍需验证驱动位号和新顶层。

优先顺序：①以实际新板启动配置核对 PS7、MIO 电气、串口、64 位 RF EMIO、FCLK；②确认显示 IP 升级行为与约束；③在第三份副本合并 RF/显示并校验地址、中断、时钟/复位、CDC；④实现与时序/IO 验收；⑤保留原厂回滚路径后分别验证接收、屏幕、并行运行。

冷启动 0xFF 根因、长期完整无丢样、真实 AI 数据/模型与整机延迟/吞吐仍未完成。旧真实三调制有限快照证据继续保留；今天的接收烟测不能替代它或扩展结论。

## 原始证据与复现

- rf_synthesis：[原始报告](../../results/p29-rf-synth-20261019t083419z/report.json)。
- display_synthesis：[原始报告](../../results/p29-display-synth-20261019t090335z/report.json)。
- display_upgrade：[原始报告](../../results/p29-display-upgrade-20261019t084235z/report.json)。
- adi_package：[原始报告](../../results/p29-package-20261019t082556z/report.json)。
- sources：[原始报告](../../results/p29-source-verification-20261019t092044z/report.json)。
- compiled_audit：[原始报告](../../results/p29-audit-20261019t091015z/report.json)。
- rx_readback：[原始报告](../../results/p29-smoke-archive-20261019t084543z/report.json)。
- integration：[原始报告](../../results/p29-integration-audit-20261019t084053z/report.json)。
- hls_vendor_patch：[原始报告](../../results/p29-hls-patch-install-20261019t090333z/report.json)。
- boot_package_comparison：[原始报告](../../results/p29-ps-boot-baseline-20261019t085558z/report.json)。
- display_clock_refinement：[原始报告](../../results/p29-display-clock-20261019t091430z/report.json)。
- display_clock_self_check：[原始报告](../../results/p29-display-clock-test-20261019t091238z/report.json)。
- PS_readback：[原始报告](../../results/p29-ps-readback-20261019t090944z/report.json)。
- PS_generated_comparison：[原始报告](../../results/p29-ps-generated-comparison-20261019t091727z/report.json)。

复现顺序：`p29_prepare_build.py` → `p29_patch_adi.py` → `p29_run_vivado.py package` → `rf` → `p29_prepare_migration.py` → `display-upgrade` → `rf-synth`。显示使用短路径候选与已核验官方 HLS 补丁再运行 `display-synth` → `audit`；当前短路径恢复指针在 `results/p29-active-build.json`，不要覆盖它后直接在长路径重跑。重型 Vivado 阶段依次运行；不在 D 盘原件运行 `-force` 创建。`p29_verify_sources.py` 与 `p29_integration_audit.py` 为只读离线核验。安装补丁脚本拒绝覆盖已有补丁，已经安装后不重复安装。

时钟补充复现：`p29_display_clock_test.py` → `p29_prepare_clock_refinement.py` → `p29_run_vivado.py display-clock`；约束已经加入后不重复 add/reset，先查当前工程。普通显示重综合无需重置已成功的 TPG。若要重现修补前基线，使用已归档 DCP 或未加本轮 XDC 的副本，不冒用当前工程输出。

本轮入口备份：`results/p29-before-20261019T092133Z/`。`results/` 被 Git 忽略，备份项目时必须包含它及 E 盘工作源，不能只依赖 git diff。

工具依据：[AMD upgrade_bd_cells](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/upgrade_bd_cells)、[AMD Y2K22 官方修复](https://docs.amd.com/r/en-US/76960/Solution)、[ADI 2021_r1 IP 约束源](https://github.com/analogdevicesinc/hdl/blob/hdl_2021_r1/library/axi_ad9361/axi_ad9361_constr.xdc)。没有照抄其他载板的引脚或凭空填写板级时延。
