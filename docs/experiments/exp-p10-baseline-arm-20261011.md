# P10：冻结传统基线在 P201 ARM 上执行

日期：2026-10-11。使用已冻结的P09传统基线，不重新训练，不使用测试集调整模型。将73个FP64常数（45个模型参数、28个标准化参数）导入C；导出216个匿名float32 I/Q测试帧。输入为维度1024×2的小端float32，不能直接输入板端int16原始计数文件。

电脑C先与Python的14个特征、3个logit和类别比较，再交叉编译ARM Cortex-A9硬浮点。传输包及全部文件哈希在板上核验，实际执行216帧并回收输出。

## 实际结果

- 216帧分类逐项与冻结的Python结果相同，测试215/216=99.5370%，27条独立合成母波形。
- 特征最大绝对误差3.019806626980426e-14，logit最大误差7.203126983768016e-13；预先容差特征abs/rel1e-10、logitabs1e-7。
- 5次预热、100次计时：完整特征提取+线性头平均1.31849771ms，p50=1.314078ms，p95=1.338318ms，最大1.490058ms；峰值RSS1116 KiB。排除文件IO，输入交替微扰防止重复常量被编译器优化掉。
- 模型未量化，未接入真实接收，不推导无缝30.72 MS/s实时分类能力。每1024点仅33.33us，分类应另定选帧/抽取和刷新频率。

## 证据

准备：results/p10-baseline-arm-20261011T054505Z，包 SHA256 40b662409fc29a0b9710e464fdbe65fb31dd78074f4bcc3f73a47bbdbd187be6。

实际执行：results/p10-baseline-board-run-20261011-135055/report.json 与串口记录。回收：results/p10-baseline-readback-20261011-135200/outputs 与 verification.json；回收包 SHA256 89b4234eb44b25e54dcbdda6cba498ee49daf83a991bfb95f13eda4434f5a4a5。

源码 embedded/modulation_baseline/baseline_infer.c；准备/独立检查 experiments/p10_prepare_baseline_arm.py、p10_verify_baseline_arm.py。

同批测试的电脑/ARM浮点对照、真实ARM执行、耗时/RSS记录：**通过**。CNN部署、量化比较、真实RF准确率、采集队列及独立显示：**待验证**。
