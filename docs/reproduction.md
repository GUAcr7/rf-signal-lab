# Zynq 的信号AI识别系统 复现说明

## 离线数据与算法检查

环境要求为 Python 3.11+ 和 NumPy。在仓库根目录执行：

```text
python sim/verify_package.py
```

检查内容包括文件哈希、Python 文件语法、FIR 与独立 Fraction 有理数参考的对照、三个正式技能案例与保留的九抽头历史案例、舍入和饱和边界，以及四种波形共 16 块 RX12 数据与 NPZ 解码的一致性。该入口不访问串口或射频设备。

学习数据读取示例：

```text
python data/rf-learning-kit/example_read.py
```

图形界面额外依赖 Matplotlib 和 Tk。学习套件的标签来自已知发射配置，适合回放与程序调试，不作为独立机器学习测试集。

## FIR 技能包验证

单案例用法、接口契约和失效条件见 `skill/verify-fixed-point-fir/README.md`。RTL 仿真依赖 Icarus Verilog 的 `iverilog` 和 `vvp`。完整验证入口为：

```text
python skill/validate.py --tool-root <icarus-root> --output <new-output-directory>
```

输出目录必须尚不存在。历史 11 项验证记录位于 `sim/fir-skill-validation/validation/`，涵盖正例、有理数复核、错误通道和饱和标志反例、无效输入及缺失工具拒绝。`sim/verify_package.py` 的数值检查与这套 RTL 验证分别运行。

`sim/fir-skill-validation/validate.py` 保留原验证驱动，`skill/validate.py` 适配当前目录布局。

## 原工程路径恢复

```text
python build/prepare_workspace.py --output local/workspace
```

该命令依据来源清单向一个尚不存在的新目录复制项目文件，并恢复原文件名大小写；不执行构建或硬件操作。环境信息隐去和密码环境变量设置仍保留。历史日志中的绝对路径用于追溯，运行脚本前需配置本机路径。

## FPGA 与板端重建

实际工具版本为 Vivado 2021.1，与指南推荐 2026.1/2025.2 的差异在设计报告中说明。FIR、FFT、合并工程和厂商基线的构建脚本分别位于 `fpga/` 和 `experiments/`。

先检查外部输入：

```text
python build/preflight.py --vivado <vivado-launcher> --adi-hdl <complete-adi-hdl> --display-project <vendor-display-project>
```

仓库包含部分厂商源代码。完整 ADI HDL、板厂显示与启动工程、迁移导出、工具及器件支持需从相应来源取得并固定版本。历史构建脚本中的 E:/D: 路径和结果指针需对应本机目录配置。目前尚无干净环境下完整重建的验收记录。

上板前需核对设备身份、镜像/位流/overlay 对应关系、同轴衰减链和供电。当前 CDC 与外部 I/O 时序未完全闭合，固定八相位策略尚缺新的独立测试；各项限制及已有板级验收范围见设计报告。
