# 构建与实现报告入口

实际工程使用 Vivado 2021.1；与指南推荐工具版本的差异、外部厂商输入和环境准备见 [复现说明](../docs/reproduction.md)。

| 入口 | 用途 |
| --- | --- |
| [preflight.py](preflight.py) | 只读检查 Vivado、完整 ADI HDL 与板厂显示工程是否已提供，不执行构建或上板 |
| [prepare_workspace.py](prepare_workspace.py) | 在一个尚不存在的新目录恢复原工程文件名大小写，不执行历史脚本 |
| [../fpga/fir-vivado/](../fpga/fir-vivado/) | 定点 FIR OOC 综合脚本与约束 |
| [../fpga/fft-vivado/](../fpga/fft-vivado/) | FFT 准备、仿真与实现 TCL 脚本 |
| [../fpga/integration/](../fpga/integration/README.md) | 射频与显示集成、设备树和对应阶段说明 |
| [../fpga/vendor-baseline/](../fpga/vendor-baseline/) | 已提供的部分厂商基线源码与许可 |
| [../results/p07-fir-timing-20261011/](../results/p07-fir-timing-20261011/) | FIR 优化前后时序与资源记录 |
| [../results/p37-safe-route-20261021t084904z/](../results/p37-safe-route-20261021t084904z/) | 集成实现的时序、资源、DRC、CDC 和时钟报告 |

构建脚本中的原机器路径需要按复现说明配置。公开仓库不是完整厂商发行包，也不包含工具安装器、授权文件或预编译板端固件；不能直接把历史位流与其他版本的设备树、启动镜像配用。
