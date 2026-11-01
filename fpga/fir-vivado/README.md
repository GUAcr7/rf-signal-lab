# P07a 独立 FIR 综合准备

当前状态（2026-10-11）：实际综合、时序问题修正及重新仿真已完成；修改后的内部 setup/hold 综合估计为 +1.866/+0.246 ns。详见 [实验记录](../../docs/experiments/exp-p07a-timing-20261011.md)。入口固定 **Vivado 2021.1 / xc7z020clg400-2 / 63 抽头 / 100 MHz（10 ns）**。入口本身不修改 RTL、不接入原厂工程、不布局布线、不生成位流、不访问板卡。

当前 RTL 的 I/Q 为有符号 12 位，系数为 18 位 Q17，累加器为 36 位，偶数舍入后饱和到 16 位并分别给出标志。复位同步、低有效。原默认系数 `fpga/ip/fir63_q17.hex` 的路径和字节保持不变；系数在综合时初始化为 ROM，未推断成可运行时替换的系数接口。因此资源估计针对这一组固定系数，不代表全部仿真系数或可重载 FIR。

`expected-contract.json` 固定 RTL、TB 和系数的 SHA256，并引用正式 18 组/72,356 输出比对及 1086 输出默认系数资格报告。启动前重新核验这些文件与报告指纹关联；若源码变化，应先重新完成相应资格检查，再显式更新本任务清单，不能直接绕过。

只检查现有来源，不运行工具、不写工作区：

```powershell
& '.\fpga\fir-vivado\run-fir-synthesis.ps1' -CheckOnly
```

原厂 HDL 构建结束、释放资源后，从项目根目录手动运行：

```powershell
& '.\fpga\fir-vivado\run-fir-synthesis.ps1' `
  -VivadoBat 'E:\FPGA_Tools\Xilinx\Vivado\2021.1\bin\vivado.bat' `
  -WorkParent 'E:\FPGA_Tools\Work'
```

入口建立全新 `p07-fir-ooc-时间-随机后缀` 短目录，复制并核验 RTL、系数和任务脚本，保留 `source-manifest.json`、`vivado.log`、`vivado.jou`、`console.txt`、`run-record.json`。失败现场保留；每次重跑创建另一个目录。可选 ADI 环境变量通过环境 provider 真正删除，精确版本设为 `2021.1`，结束后恢复原存在/空值状态。原生退出码使用 `global:LASTEXITCODE` 捕获，日志写入失败也会记录并报错。单个 Vivado 子进程限制为一个计算线程，不保存全局设置。

`reports/` 预期保存：

- `utilization.rpt`、`utilization_hierarchical.rpt`：器件综合后的 LUT、FF、DSP、BRAM；`run-record.json` 摘录官方表格四项 Used 行，原表为依据。
- `timing_summary.rpt`、`internal_setup.rpt`、`internal_hold.rpt`：100 MHz 下的综合估计，包括独立内部时钟到时钟路径。
- `check_timing.rpt`、`clocks.rpt`、`unconstrained_io.rpt`：时钟与约束范围，检查未约束路径。
- `synth.dcp`、`internal_metrics.tsv`：综合检查点与内部 setup/hold 裕量。黑盒、无寄存器/内部路径、LUT/FF 为零、数据输出未驱动/接常量时直接报错，避免得到无意义的零资源/空时序结论。DSP/BRAM 为零本身可以合理。

只对 `clk` 建立 10 ns 时钟。I/O 延迟、外部驱动/负载、引脚、板级时钟质量、ADC/DMA 和复位/握手外部时序没有建模，也未添加 false path；I/O 未约束提示必须按报告范围解释。综合后的正裕量只表示综合估计，不等于布局布线时序收敛或板端性能；负裕量也会原样记录，不自动修改 RTL。`timing_closed`、`placed`、`routed`、`board_accessed` 均保持 false。

当前架构无暂停时每 66 拍接收一对 I/Q；100 MHz 下按周期计算为约 1.515 MS/s。这是结构预期，不能当作布局布线已达成时钟、实测吞吐，或 30.72 MS/s 接收链路能力。首次综合的 −5.153 ns 失败与修改后的报告均保留在 `results/p07-fir-timing-20261011`，综合来源清单已明确更新为重新通过的仿真资格报告。`static-check.json` 是最初准备时的历史指纹，不是修改后的来源依据；当前核对见该结果目录 `current-source-check.json`。
