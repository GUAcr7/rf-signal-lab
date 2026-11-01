# P06 原厂 HDL 构建准备

当前状态（2026-10-11）：Vivado 2021.1 已安装，原厂完整构建执行并生成 bit/XSA/DCP，8 阶段均退出 0；但原脚本关闭 PS 时钟约束，补入诊断后100 MHz域时序违规。随后独立补时钟重新布局布线，100 MHz域WNS改善到−1.308 ns，全局WNS仍−4.397 ns，CDC/I/O尚未完整验收，**不作为恢复固件烧写**。原始产物见 `results/p06-vendor-build-20261011`，派生实验见 `results/p06-ps-clock-implementation-20261011`，详见 [安装与构建记录](../../docs/experiments/exp-p06-install-20261010.md)。留存源码保持归档原始字节，工作区内原 IP 包装自动重生成的 bd.tcl 换行变化另行记录。工具和原工程未升级版本。

## 来源与完整性

- 原归档：`D:\FPGA natch\plutosdr-fw.tar`，12,338,708,480 bytes。
- 归档 SHA256：`461ce40cc8915303e6c9044ff3216ec77f174d49c85d71044fd6a4929ae11d8e`。这是本地来源指纹，未取得厂商签名或官方归档摘要，也未证明与当前板卡 BOOT.bin 相同。
- 选出的源码/约束/系数/共享脚本/许可文件：138 文件、960,841 bytes；原始字节未修改，每文件 SHA256 在 `source-manifest.json`。
- `source/plutosdr-fw/hdl` 为留存副本；没有提取旧 XPR、综合实现产物、Linux/Buildroot/U-Boot、Git 元数据或烧写脚本。
- 全新短工作区：`E:\FPGA_Tools\Work\p06-pzp201\hdl`；138 文件均与留存副本哈希一致，详见 `short-workspace-manifest.json`。
- 116 条直接 Makefile 文件依赖与 140 条已观察到的显式 Tcl 输入引用已纳入副本，所检查的必要文件缺失为 0。动态 Tcl/Vivado 解析仍须实际构建核验。

## 最小构建入口

原厂 project Makefile 的范围是先打包 ADI 核，再在 `hdl/projects/pzp201` 执行 `vivado -mode batch -source system_project.tcl`。根级 plutosdr-fw Makefile 还包含 ARM/Linux/固件打包与烧写目标，此次不使用。

`build-vendor-baseline.ps1` 用 Windows 原生方式按该 Makefile 的递归依赖顺序调用**未修改的原 Tcl**，无需修改厂商源码来适配 shell。安装好工具后，从 PowerShell 执行：

```powershell
& 'C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab\fpga\vendor-baseline\build-vendor-baseline.ps1' `
  -VivadoBat 'E:\FPGA_Tools\Xilinx\Vivado\2021.1\bin\vivado.bat' `
  -HdlRoot 'E:\FPGA_Tools\Work\p06-pzp201\hdl' `
  -OocJobs 1
```

此入口已在 `E:\FPGA_Tools\Work\p06-pzp201-20261011c\hdl` 正式执行；首次失败/诊断现场 A/B 另行保留，不算通过构建。它要求启动前工作区源码哈希一致且没有额外文件；再构建仍需使用结果目录中的 `prepare-short-workspace.py` 创建另一全新短目录，不能清理、覆盖或直接重跑已生成产物的 C 目录。

步骤与预期：

1. 严格核对 Vivado **2021.1**、器件 **xc7z020clg400-2** 及所需 Xilinx IP 目录。目录可见不等于许可和综合通过。
2. 顺序运行 `axi_ad9361` → `util_cdc` → `util_axis_fifo` → `axi_dmac` → `util_pack/util_cpack2` → `util_pack/util_upack2` 的原 `*_ip.tcl`，各自产生 `component.xml`。
3. 在 `hdl/projects/pzp201` 运行原 `system_project.tcl`。原脚本创建项目、生成 BD、综合、实现和位流；时序不满足时应报错并产生 `system_top_bad_timing.xsa`。
4. 成功时预期存在 `projects/pzp201/pzp201.sdk/system_top.xsa`、`projects/pzp201/pzp201.runs/impl_1/system_top.bit`，同时保留 `timing_synth.log`、`timing_impl.log` 与所有原 Vivado 日志。

各调用的日志、journal、终端输出和阶段退出码保存到短工作区同级的全新 `build-时间-随机后缀` 目录。`ADI_MAX_OOC_JOBS=1` 仅限制并行任务以适配当前内存；其余受记录脚本控制的 ADI 环境覆盖项恢复原默认，严格版本检查保持启用。所需许可、实际资源和时序以及接收恢复仍待新构建/后续上板证据。

## 已知边界

- 长留存路径不直接用于构建：归档已有一个生成文件映射到该路径为 **267 字符**；短工作区对应路径为 **158 字符**。
- pzp201 Tcl 的器件配置须在上板前与实物芯片完整标识核对；现有归档历史日志为 Linux Vivado 2021.1，不能代替本机结果。
- 原 `system_bd.tcl` 已含 `fir_compiler` 插值/抽取，倍率 8，使用原 `library/util_fir_int/coefile_int.coe`。这不是 P05c 的 63 抽头参考系数，也没有项目新增 FFT。P07 必须另行确定实际输入位置、数据格式、采样率、时钟域和软件配套。
- `.gitmodules` 中 HDL 分支标签写 `hdl_2018_r1`，实际脚本严格要求 2021.1；该标签不能证明当前源树提交版本。此次以完整归档及逐文件哈希固定来源，不下载或替换上游版本。
- 本机 Vivado 2021.1 实际启动、FIR IP 综合、Synthesis/Implementation 许可与位流生成已通过；这不等于完整时序或所有功能都已在 Windows/板端验收。

## 当前诊断入口

`reimplement-ps-clocks.tcl` 在原厂优化后DCP的派生实验中补同样两路PS时钟并重新布局布线，保存报告和派生DCP。2026-10-11实际退出0，但setup未通过；不输出bit/XSA、不操作板卡，也没有用新时序例外隐藏违规。已有输出目录会被拒绝，原始工程和检查点保留。

`audit-routed-clocks.tcl` 只在已有 DCP 的内存副本中补入原 PS 配置/生成 XDC 证明的100/200 MHz时钟与 jitter，报告前后时钟覆盖、时序和CDC；不修改源树、写新位流或访问硬件。本次无时钟/未约束内部端点降为0，但100 MHz域 setup/hold为−14.695/−0.170 ns；外部I/O及CDC仍待审查。不能把诊断当成修正后实现通过。

`discover-jtag.tcl` 只枚举下载线；`read-jtag-identity.tcl`严格匹配本次唯一线缆再读芯片身份。Digilent支持补装后已实测找到xc7z020与ARM DAP，未编程/复位/访问寄存器，封装速度等级仍须实物资料核对。脚本固定的目标串号不得当成其他板卡通用值。

证据与可复现准备脚本位于 `outputs/rf-signal-lab/results/p06-source-prep-20261010`；其他实验文档仅提供追加草稿，由主控合入。
