# 设计源码入口

本目录中的 `rfsig/` 为 Python 算法参考与数据处理模块。工程按运行平台保留以下源码路径，目录对应关系与根目录 README 一致：

| 路径 | 用途 |
| --- | --- |
| [rfsig/](rfsig/) | 数字信号处理、定点参考与分析模块 |
| [fpga/rtl/](../fpga/rtl/) | FPGA 逻辑源码 |
| [fpga/constraints/](../fpga/constraints/) | 时序与管脚约束 |
| [embedded/](../embedded/) | ARM、板端推理、显示与控制代码，分阶段保留版本 |
| [deployed-build-source/](../deployed-build-source/) | 已归档部署构建所使用的源码 |
| [host/](../host/) | 电脑端控制、采集接口与回放程序 |
| [configs/](../configs/) | 算法与运行配置 |
| [archive/source-variants/](../archive/source-variants/) | 仅见于历史快照的源码差异，供追溯 |

当前实现与实测口径以设计报告为准，不能把不同阶段源码的效果合并报告。运行准备与原文件名大小写恢复见 [复现说明](../docs/reproduction.md)。
