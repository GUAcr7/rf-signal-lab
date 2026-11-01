# 可复用Skill：定点I/Q FIR黄金参考与RTL验证

这是2026-10-29从实际项目经验提炼的新交付，不是补造旧实验。另一个队伍可完整复制本目录，用Python 3.10+和Icarus运行examples，无需原工程和板卡。AI使用入口为SKILL.md；使用范围、命令和失败条件详见该文件及references/contract.md。

适用：具有同位宽、舍入、饱和和valid/ready时序契约的独立FIR模块。可替换系数、1..63抽头、I/Q数据及兼容DUT。失败条件包括输入格式/范围错误、工具缺失、超时、编译/仿真失败、数值或饱和标志不一致、握手/复位断言失败。

验证命令示例：python scripts/verify.py --case examples/three-tap.json --output out-three。工具不在PATH时用--tool-root指定根目录。请从本目录执行，或为case/output提供正确路径；脚本自身不依赖执行目录定位assets。不要在ZIP内直接运行。

已验证效果看交付根目录validation/及validation-summary.json。适配不同FIR案例证明的是同类模块复用性，尚未证明跨平台/跨板卡/PYNQ复用。本包不操作RF/串口、不改固件。
