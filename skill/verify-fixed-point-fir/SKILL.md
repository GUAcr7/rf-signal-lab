---
name: verify-fixed-point-fir
description: Verify signed fixed-point I/Q FIR RTL against an exact integer golden reference, including rounding, saturation, backpressure and reset. Use for FIR modules compatible with the supplied 12/18/Q17/36/16-bit interface; not for RF board control or PYNQ deployment.
---

# 定点FIR整数黄金参考与RTL验证

先核对[接口契约](references/contract.md)。兼容模块可直接用脚本；位宽、握手或延迟不同的设计须显式适配模型和TestBench，不能只修改期望输出使其通过。

使用标准库Python 3.10+及Icarus Verilog。不依赖原RF工程、NumPy、板卡、Vivado或固定磁盘路径。

```text
python scripts/verify.py --case examples/three-tap.json --output out-three
python scripts/verify.py --case examples/five-tap.json --output out-five
python scripts/verify.py --case examples/nineteen-tap-saturation.json --output out-saturation
```

工具不在PATH时追加`--tool-root <Icarus安装根目录>`，根目录下应有bin/iverilog与bin/vvp；MSYS2布局可包含lib/ivl。输出目录必须不存在。换DUT用`--dut <模块文件>`；顶层名和接口须仍兼容契约。

核对report.json的all_passed、tool_returncode、源文件/输入SHA、逐样本比较和两种暂停模式。失败时保留报告与日志；工具缺失/超时/编译失败都不能记为通过。数值差异优先查系数顺序、有符号码扩展、尾部补零和舍入；握手失败查valid/ready保持及复位。

交付测试输入、黄金输出、DUT/TB哈希、工具版本、原始stdout和结论。整数参考通过只证明该契约的数字行为；器件时序、资源、上板吞吐另验。若用户只要求复核，不操作板卡。

需要解释成果来源与适用边界时读[来源与限制](references/provenance.md)。负例与迁移验证的实际记录在包外`validation/`，并非预先写死的通过结论。
