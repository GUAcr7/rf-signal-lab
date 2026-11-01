# EXP-P06：原厂 FPGA 工程与 ARM 实现条件（进行中）

- 日期：2026-10-03，Asia/Shanghai。
- 当前状态（2026-10-11）：**Vivado2021.1安装/原厂构建/JTAG身份通过，派生FPGA时序失败、未烧写；ARM GCC8.3、Hello、18组离线FIR144712输出、未训练算子探针、原生IIO真实有限接收、软件FFT及训练后CNN FP32/INT8实际执行/独立回读已通过。持续链路/真实RF分类/新固件采样待验收。**见 [最新进度](exp-auto-20261011.md)、[原生接收](exp-p06-native-rx-20261011.md)、[CNN ARM](exp-p10-cnn-20261011.md)、[时序问题](exp-p06-fanout-20261011.md)。
- 2026-10-03 首次只读核验时没有启动 GUI、安装工具、解包覆盖固件、升级 IP 或烧写板卡；后续工具准备进展按文末日期记录。

## 查到的原厂材料

归档为 `D:\FPGA natch\plutosdr-fw.tar`，大小 12,338,708,480 字节。只读遍历确认 `plutosdr-fw/hdl/projects/pzp201/` 有 `pzp201.xpr`、`system_top.v`、`system_constr.xdc`、`system_project.tcl`、`system_bd.tcl` 与历史构建日志。

共享脚本也实际存在：`hdl/projects/scripts/adi_env.tcl`、`adi_project_xilinx.tcl`；不能把第一次读错为 `hdl/scripts/adi_env.tcl` 的路径当成归档缺文件。

项目 Tcl 写 `set p_device "xc7z020clg400-2"`，XPR 与历史构建日志指向 **Vivado 2021.1**。历史日志来自 Linux `/home/ubuntu/plutosdr-fw/hdl/projects/pzp201`，不是今天在 Windows 新完成的构建。没有证据证明这个归档的产物逐字节匹配当前板卡 BOOT.bin。

[只读归档清单与摘录](../../results/p06-archive-inventory-20261003t102953950816z.json)包含读到的源码条目、版本行、字节数及摘录哈希。

## 本机工具检查

未在以下已检查位置找到 Vivado：当前命令路径、常见卸载登记、C:/AMD、C:/Xilinx、D:/AMD、D:/Xilinx、C:/Program Files、D:/Program Files、D:/Dev 中匹配的目录；桌面及开始菜单匹配名称的快捷方式；原厂配套工具目录内匹配的文件名。

上述检查不是全盘扫描。2026-10-03 用户通过软件界面确认“未找到 Vivado”，因此进入安装准备。安装/登录/工具授权界面由用户完成。

## 安装准备核验（2026-10-03）

- 本机系统：Windows 11 家庭版，64 位，版本 10.0.26200；约 15.7 GiB 内存。
- 当次磁盘空间检查：C 盘约 45.6 GiB、D 盘约 39.8 GiB、E 盘约 173.0 GiB 可用。组件选择后的实际空间需求须以安装器为准。
- 已创建下载目录 `E:\FPGA_Tools\Downloads`；尚未下载、运行安装器，也没有改动系统配置或板卡。
- 官方 2021.1 下载页提供 Windows Self Extracting Web Installer，EXE 约 226.04 MB。这只是在线安装器，后续所选组件还需要下载和安装空间。
- **Windows 11 家庭版不在 Vivado 2021.1 官方支持的操作系统列表内**。可以先查看原版本安装器能否正常启动，但不能据此承诺安装、构建或驱动兼容；若出现系统不支持或启动失败，保存原始提示，再评估官方列出的系统环境。暂不升级原厂工程/IP，不改装现有 Windows。

官方依据：[2021.1 下载页](https://www.amd.com/en/support/downloads/adaptive-socs-and-fpgas/development-tools/2021-1.html)、[2021.1 支持的操作系统](https://docs.amd.com/r/2021.1-English/ug973-vivado-release-notes-install-license/Supported-Operating-Systems)。

## 2026-10-03 的历史操作建议（已由文末新证据修正）

1. 打开上述官方 2021.1 下载页，在 Vivado ML Edition – 2021.1 下选择 Windows Self Extracting Web Installer（EXE，约 226.04 MB）。当前准备完整设计工具，不选择独立 Lab Edition。
2. 自行登录或注册官方账号，将安装器保存至 `E:\FPGA_Tools\Downloads`。用户已反馈账号注册后需要等待审核回复；当前记为“下载受账号审核限制”，未核验审核原因或预计完成时间，不视为软件/板卡故障。
3. 运行安装器，停在产品选择页面，返回截图；若先出现操作系统兼容性提示或错误，则返回该提示。收到实际界面后再确定组件和安装路径。

验收状态：版本依据与本机安装准备检查通过；Vivado 下载、安装、启动及工程构建均待验证。

匹配工具确认后，AI 可继续准备独立工作副本、查全源文件/IP/路径，执行可复现的命令构建。真实重建仍需新日志、许可/IP 核验、资源时序报告与可恢复的上板接收证据。原工程器件配置还须与实际芯片完整标识核对。

ARM 路线仍待检查架构、库、内存、持久化方式、最小 C 程序和极小模型推理；不能因为桌面参考可运行就记为 ARM 部署通过。

## 2026-10-09 后续恢复检查

等待工具期间，[P05c 离线 FIR 浮点参考](exp-p05c-fir.md)已通过，最新全工程回归 367 项通过，没有接入真实 RX 或修改固件。

09:49 再次只读检查本机：命令路径无 vivado，`E:\FPGA_Tools\Downloads` 目录存在但无文件，没有 vivado/xsetup 进程；见[工具状态快照](../../results/p05c-host-tool-state-20261009.json)。本次不是全盘安装检测，没有检查账号审核结果，也没有启动浏览器或安装器。下一步由用户提供当前下载/安装页面（已安装则提供实际路径），依据实际状态继续；账号仍待审核时可改为 ARM 兼容性检查，不重复 P05 已完成的实验。

## 2026-10-09 15:30：在线安装器停用，改为完整离线包

用户已反馈官方账号登录成功，并自行下载、运行 `Xilinx_Unified_2021.1_0610_2318_Win64.exe`。最新截图显示 **Web Installer Client Obsolete**：该版本在线安装器已过时，提示改用已下载归档或官网完整镜像。因此当前故障指向旧在线下载客户端；没有密码错误的证据，不再重复注册账号或在旧客户端重试下载。

只读核验：安装器在 `E:\FPGA_Tools` 与电脑 Downloads 中存在，E 盘文件为 237,020,792 字节，SHA256 为 `f3545eb7baa287d3383a175172f4bf88c10a014ff41ab76cd4d3f5e79620d802`，与已有 `.digests` 文件对应 SHA256 一致；Windows Authenticode 签名状态为 Valid，签名组织 Xilinx, Inc。没有执行 PGP 摘要签名验证，也未由 AI 操作安装界面。证据及修改前文档见[此次状态记录](../../results/p06-installer-obsolete-20261009-1533/verification.json)。

官网 2021.1 主版本下仍列出 **AMD Unified Installer 2021.1 SFD**，TAR/GZIP、51.87 GB，官方链接中的文件名为 `Xilinx_Unified_2021.1_0610_2318.tar.gz`。这才是下一步完整离线安装包；2021.1.1 更新包和独立 Lab Edition 不作为此次完整设计工具替代。官方完整包安装说明为解压后运行 Windows 的 `xsetup.exe`，见 [UG973 2021.1](https://www.xilinx.com/support/documents/sw_manuals/xilinx2021_1/ug973-vivado-release-notes-install-license.pdf)。

当次空间实测：C 44.91 GiB、D 36.98 GiB、E 172.72 GiB 可用。E 盘可容纳此次下载；完整解压加所选组件安装的峰值空间仍待按归档与安装器实际需求核验，不能据此承诺全部安装足够。

下一组由用户操作：

1. 关闭旧在线安装器，回到上述官方 2021.1 下载页。
2. 在 Vivado ML Edition – 2021.1 下选择 AMD Unified Installer 2021.1 SFD，保留文件名，保存到 `E:\FPGA_Tools\Downloads`。
3. 下载完成后让 AI 核验文件完整性、可用解压工具和空间，再安排解压及安装器产品选择。暂不重复旧客户端的 Download Image，也不升级原厂工程/IP。

当前验收：旧在线安装器文件一致性与签名检查通过；客户端停用原因有用户截图证据。完整离线包下载、解压、Vivado 安装/启动、工程重建均待验证。板卡、固件与算法代码未修改，既有 367 项代码回归结果不受此次文档更新影响。

## 2026-10-10：完整离线安装包校验与解压通过

用户确认下载完成并授权 AI 继续操作。实际完整包位于 `E:\FPGA_Tools\Xilinx_Unified_2021.1_0610_2318.tar.gz`，为 55,695,579,850 字节。SHA256 为 `aa20a1b2e65b7f4da77cfe27896cc510641df5a17540232ffe0636f6b7f935c4`，与此次从 AMD 官方 HTTPS 地址取得的 `.digests` 中 SHA256 完全一致。未执行 PGP 签名验证。

归档只读审计确认没有不安全路径、Windows 名称冲突或重复条目。解压至 `E:\FPGA_Tools\Installers\Vivado2021.1`，直接流式解压，没有额外生成约 53 GiB 的中间 `.tar` 文件；原始安装包保留。16,064 个普通文件共 56,945,458,446 字节、1,366 个目录全部解压完成，独立再次核对文件类型、尺寸和目录，缺失或不一致均为 0。214 个仅用于 Linux 的链接未创建；当前目录用于 Windows 安装，不能当作完整恢复的 Linux 安装树。

Windows 安装入口为 `E:\FPGA_Tools\Installers\Vivado2021.1\Xilinx_Unified_2021.1_0610_2318\xsetup.exe`，441,776 字节，Authenticode 签名状态 Valid，签名组织 Xilinx。解压后 E 盘剩余约 67.78 GiB；是否足够安装仍需按实际组件选择和安装器计算核对。

证据目录：[p06-install-prep-20261010](../../results/p06-install-prep-20261010/)。其中 `download-verification.json` 记录下载哈希，`official-archive.digests` 为官方摘要，`archive-inventory.json` 与 `extraction.json` 保存归档/解压清单；修改前文档备份也在该目录。

15:39 启动上述 `xsetup.exe`；初始化约两分钟后，15:41:36 已确认 Java PID 2600 的窗口标题为 `Xilinx Unified 2021.1 Installer - Welcome`，Responding=True，且当日新安装日志已生成。随后直接读取安装器画面，确认欢迎页与 `A Newer Version Is Available` 提示框存在；提示可升级 2026.1，也可按 Continue 继续 2021.1。**离线安装器启动通过；Vivado 本体安装、启动和工程重建仍待验证。** 未重复启动或终止进程。

控制工具尝试点击 Continue、按 Tab 并重新激活窗口后，界面与按钮焦点未发生可确认的变化；具体原因尚未核验，不把操作调用返回视为按钮执行成功。保留当前窗口，交由用户点击 Continue，再点击欢迎页 Next 并反馈下一页。当前尚未选择产品、组件、安装目录或执行安装，也未接受软件许可协议。此时没有实际工具操作被自动审批拒绝。

欢迎页与提示框截图为证据目录的 `installer-welcome-0.jpg`、`installer-welcome-1.jpg`；`installer-ui-state.json` 保存可见窗口状态与输入尝试结果，`installer-entry-verification.json` 保存安装入口签名及剩余空间复核。

计划选择 Vivado ML Standard、Zynq-7000 器件支持，最终软件安装根目录 `E:\FPGA_Tools\Xilinx`。这是已核对器件需求后的计划，不表示安装界面已经选择或安装成功。下一步核对实际安装页面、组件与磁盘需求；不升级工程/IP、不烧写板卡、不改变已有驱动。
## 2026-10-10：原厂 HDL 干净源码与短工作区准备通过

在安装器推进期间，按用户授权独立准备原厂 FPGA 工程；本次没有启动 Vivado、执行综合/实现、升级 IP、访问或烧写板卡，也没有改动原归档及 Git index。

原归档 `D:\FPGA natch\plutosdr-fw.tar` 为 12,338,708,480 bytes，首次保存完整 SHA256 来源指纹：`461ce40cc8915303e6c9044ff3216ec77f174d49c85d71044fd6a4929ae11d8e`。哈希前后大小和修改时间一致；没有官方摘要/签名或与当前 BOOT.bin 相同的证据。

只读元数据遍历得到归档 304,499 条目；HDL 部分有 3,092 普通文件和 749 目录，无链接。按 pzp201 Makefile、递归 Xilinx 库依赖及显式 Tcl 输入路径选取 138 必要源码/约束/系数/共享脚本/许可文件，共 960,841 bytes，逐文件 SHA256 保存到 `fpga/vendor-baseline/source-manifest.json`。116 条 Makefile 文件依赖和 140 条已观察到的显式 Tcl 输入引用已纳入副本，所检查的必要文件缺失 0；未提取旧 XPR、构建缓存和产物、Git 元数据、Linux/Buildroot/U-Boot 或烧写脚本。

留存源码位于 `fpga/vendor-baseline/source/plutosdr-fw/hdl`；另建立全新 `E:\FPGA_Tools\Work\p06-pzp201\hdl` 短工作区，138 文件的大小和 SHA256 全部与留存副本一致。归档已有一个生成文件映射到长项目路径可达 267 字符，短工作区为 158 字符，因此实际构建使用短路径。

工具要求仍为 Vivado 2021.1、`xc7z020clg400-2`；六个 ADI 库的打包顺序为 `axi_ad9361`、`util_cdc`、`util_axis_fifo`、`axi_dmac`、`util_pack/util_cpack2`、`util_pack/util_upack2`，之后运行原 `projects/pzp201/system_project.tcl`。已备好 Windows 绝对工具路径、逐阶段独立日志和短工作区入口 `fpga/vendor-baseline/build-vendor-baseline.ps1`。22 个原厂 Tcl/TTcl 的语法完整性检查通过，准备入口的 PowerShell 解析错误 0；这些静态检查不表示 Vivado 命令或构建通过。

原厂 BD 已有 Xilinx FIR 插值/抽取，倍率 8、原 COE 系数；不能将其混记为 P05c 的 63 抽头参考或项目新增 FFT。P07 的模块接入位置、实际时钟/采样率、格式及 PS 软件变化仍需结合原样构建和后续实物核验确定。

此次局部验收为**原厂源码/来源记录与干净短工作区准备通过**。Vivado 安装/启动、IP 目录/许可、综合/实现、时序/资源、匹配实物器件以及恢复接收均待验证；P06 整阶段仍未完成。证据见 `results/p06-source-prep-20261010` 与 `fpga/vendor-baseline/README.md`。

## 2026-10-10：当前安装权限与 ARM 条件补充

用户后来已将现有安装器推进到 `Select Product to Install` 页，并授权 AI 自主继续。工具尝试选择 Vivado 后画面仍保持 Vitis 选中，未将调用返回当成选择成功。主机最新只读快照仍显示 Java PID 2600、相同产品选择标题；见 [host-state.json](../../results/autonomous-20261010/host-state.json)。没有执行产品安装、接受 EULA 或升级 IP。

另核实了随包官方批量入口：`bin/setup-boot-loader.bat` 52–56 行把 `--help/-b/--batch` 设置为批量模式，`bin/xsetup.bat` 调用 CLI。实际只执行 `bin/xsetup.bat --help`，退出码 **1**，提示 `Administrative permissions are not available. Please restart command line shell as Administrator`；当前 Windows 执行 token 的管理员检查为 False。因此本机普通权限 CLI 未能进入配置/安装，不反复重启安装器，也不绕过管理员权限。随包语言资源还明确不允许两个安装/卸载实例同时运行；以后正式批量安装前须正常结束当前 GUI。批量配置入口为 `xsetup -b ConfigGen`，具体组件键、磁盘需求和许可仍需在实际配置生成后核对，未声称已生成配置。

命令行入口的实际观察摘要见 [batch-entry-check.json](../../results/p06-install-prep-20261010/batch-entry-check.json)。它记录退出码、错误原文、管理员角色以及随包脚本和单实例限制；不是安装成功日志。

ARM 条件完成了**本地固件镜像和原厂归档审计**，详细 [ARM-AUDIT.md](../../results/p06-arm-audit-20261010/arm-audit.md)，正式镜像报告为同目录 `firmware-report.json`：

- 本地 `uramdisk.image.gz` 的 U-Boot 头/数据 CRC、尺寸、gzip/newc 结构检查通过；来源 SHA256 为 `45b0db2d66de88dac14742682ac414c13e69a949805f49608903a57b550a8d56`。
- 抽查 ELF 为 ARM32、小端、EABI5 hardfloat，解释器 `/lib/ld-linux-armhf.so.3`；镜像有 glibc2.28、libiio0.24、iiod/读取工具、Dropbear/scp。
- **正式全部条目检查确认有 `libgcc_s.so.1` 和 `libstdc++.so.6.0.25`**，更正最初快速条目筛选中“C++ 运行库可能缺失”的不完整判断。
- 镜像条目中未发现 Python/NumPy 或推理框架；这不证明当前实际运行板卡相同。未读取任何私钥/凭据内容，敏感条目从清单排除。
- 原厂构建配置声明 GCC8/hardfloat；部分工具链接指向 `/opt/SDK/2019.1`，没有完整独立 GCC 本体的现有证据。现有 sysroot 还需与实际板端匹配。

2021.1 SFD 清单虽有 Windows ARM Linux GCC10.2 文件，独立选择性读取 SDK payload 报内容加密不受支持，**已停止，未尝试解密**。部分新目录 `E:\FPGA_Tools\ARM-GNU-2021.1` 明确标为不可用，不加入 PATH、不运行其中文件；失败日志及 8 个 payload 哈希已保存 `toolchain-extraction.json`。没有把失败提取算成安装成功。

官方 Arm Linux 宿主 GCC8.3/glibc2.28 的候选 URL 与公开 MD5 已只读核验可访问；尚未下载、启动 WSL、验证编译器或生成 ARM 程序。具体路线见审计报告。标准 ADALM-Pluto v0.35 sysroot 不能仅凭版本号就认定匹配定制 P201。

当前主机快照没有 192.168.2.* 接口或已知板卡 RNDIS/ADI 网卡；之前本轮只读 SSH 连接超时、IIO Context 创建失败，均没有取得板端状态或新样本。这里只能判断**当前连通待恢复**，不能据此宣布板卡硬件故障。后续恢复物理连接后再读取实际板端架构/库/内存/挂载/IIO，编译并运行极小 C/推理示例。P06 整阶段仍未验收。


## 2026-10-10 23:51：板卡恢复与管理员安装推进

用户已确认接回板卡并授权管理员安装。新的 RX-only 检查确认 P201、IIO 控制/接收设备及 I/Q 通道，取得 1024 个新样本并保存回读通过，前后 RF/BIST/DDS 配置未改变。官方离线安装包直接复用；正常 RunAs 提权成功，精确关闭尚未安装的旧产品选择窗口。

实际 ConfigGen 已退出 0，核对后选择 Vivado ML Standard 2021.1，仅 Zynq-7000，目标 `E:\FPGA_Tools\Xilinx`；附加驱动关闭。官方批量安装命令于 23:51 启动；安装完成、工具启动及原厂构建仍待实际证据。详见 [本次完整实验记录](exp-p06-install-20261010.md)，不将历史“普通 token 无管理员权限”和“板卡未接回”继续作为当前状态。

