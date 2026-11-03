# 仿真与验证入口

无需连接板卡的基本检查，在仓库根目录执行：

```text
python sim/verify_package.py
```

需要 Python 3.11+ 与 NumPy。检查文件清单、Python 语法、FIR 的独立有理数参考和 RX12/NPZ 采样一致性。结果存档为 `publication-validation.json`，该检查不进行 RTL 仿真、综合或上板操作。

| 路径 | 内容 |
| --- | --- |
| [fir-skill-validation/](fir-skill-validation/) | 技能包历史验证驱动、正反案例及 11 项检查的原始证据 |
| [../skill/](../skill/README.md) | 当前技能包入口及复用方法 |
| [../fpga/tb/](../fpga/tb/) | RTL 测试台 |
| [../tests/](../tests/) | Python 算法测试 |
| [../experiments/](../experiments/) | 实验与阶段验收脚本 |
| [../results/](../results/) | 仿真、综合、实现与上板结果，按原阶段和时间归档 |

RTL 技能包完整验证需 Icarus Verilog；工具、命令与验证边界见 [复现说明](../docs/reproduction.md)。测试目录和日志完整保留不表示本次重新执行了上板实验。
