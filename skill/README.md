# 可复用技能包

`verify-fixed-point-fir/` 为正式技能包：12 位有符号 I/Q 输入、18 位 Q17 系数、36 位累加、16 位饱和输出，包含整数黄金参考、RTL、测试台、三抽头/五抽头/十九抽头案例和失效条件。使用入口见该目录的 README.md；SKILL.md 为 AI 助手的可选使用说明，不自动授权硬件操作。

历史验证共 11 项：正例、独立有理数复核、错误通道/饱和标志反例、输入/工具拒绝、含空格路径迁移等；证据位于 `../sim/fir-skill-validation/validation/`。该成果不等于 FPGA 综合/时序/上板通过，也不声称通用 PYNQ 加分。

从开发失败中提炼的缘由、九抽头未覆盖饱和及十九抽头修正过程，见 `../sim/fir-skill-validation/README.md` 和报告。整套验证驱动的目录适配版为 `validate.py`，需要 Python 3.10+ 与 Icarus Verilog；不依赖 NumPy或板卡。
