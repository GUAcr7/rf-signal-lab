# 复现入口与当前边界

## 1. 无板卡的可执行核查

Python 3.11+ 和 NumPy；运行 `python sim/verify_package.py`。检查发布哈希、活跃 Python 文件语法、FIR 整数实现与独立 Fraction 参考、三个正式技能案例及保留的九抽头历史案例、舍入/饱和边界、学习套件四种波形共 16 块的原始 RX12 数据与 NPZ 解码一致性。不会连接串口、发射或修改板卡。

学习回放可执行 `python data/rf-learning-kit/example_read.py`；GUI 额外需要 Matplotlib/Tk。数据标签来自已知发射配置，不是推理结果，不能作独立机器学习测试集。

## 2. 技能包验证

`skill/verify-fixed-point-fir/README.md` 说明单案例入口、接口契约和失效条件。实际 RTL 验证需要 Icarus Verilog 的 iverilog/vvp，工具不随包分发。历史 11 项验证证据位于 `sim/fir-skill-validation/validation/`。本次打包设备未安装 Icarus，因此发布检查没有冒称重新运行 RTL 仿真。

原完整验证驱动仍保存在 `sim/fir-skill-validation/validate.py`，其原相对目录布局在本地完整留档包 `fir-skill/` 中保持原样。公开目录下若要运行整套驱动，使用 `skill/validate.py`（路径适配副本）；单案例脚本可直接使用。

## 3. 原工程路径恢复

```text
python build/prepare_workspace.py --output local/workspace
```

只向一个尚不存在的新目录复制已公开的项目文件，依据来源清单恢复原文件名大小写。用户目录隐去和密码环境变量改动仍保留。此步骤不编译、不连接硬件。历史结果中的绝对路径只是来源记录，不能据此直接操作新机器。

## 4. FPGA/板端重建

实际工程使用 Vivado 2021.1；与指南推荐 2026.1/2025.2 的差异已在报告说明。现有 FIR/FFT 的 Tcl、合并工程准备和构建脚本均保留。先执行只读检查：

```text
python build/preflight.py --vivado <vivado-launcher> --adi-hdl <complete-adi-hdl> --display-project <vendor-display-project>
```

本仓库只含部分厂商源快照。完整 ADI HDL、板厂显示/启动工程、迁移导出、工具与器件支持、原阶段构建输入路径须从各自合法来源补齐并记录版本。历史脚本含原机器的 E:/D: 路径与结果指针，需先按本机目录配置和核对后使用；当前不宣称在新电脑全量构建通过。

上板还需核对当前设备身份、镜像/位流/overlay 配对、同轴衰减链、供电和单一操作者。当前未重新执行任何硬件操作。CDC 与外部 I/O 时序未完全闭合、固定八相位策略尚缺新独立测试等限制见报告。
