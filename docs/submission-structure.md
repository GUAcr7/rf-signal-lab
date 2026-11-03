# 官方提交要求与工程目录

对应队伍提供的《全国大学生嵌入式芯片与系统设计竞赛 2026 选题指南（AMD）》3.3 自主选题赛道，重点为 3.3.3 与 3.3.5，印刷页码 20–22。初级组和高级组的提交内容一致。

## 推荐目录对照

| 官方推荐目录 | 当前入口 | 内容 |
| --- | --- | --- |
| README.md | [项目首页](../README.md)、[复现说明](reproduction.md) | 项目简介、运行检查、环境要求与目录对照 |
| src/ | [源码入口](../src/README.md) | `src/rfsig/` 为 Python 参考模型；RTL、PS 与电脑端程序分别保留在 `fpga/`、`embedded/`、`host/` |
| sim/ | [验证入口](../sim/README.md) | 离线验证、RTL 测试台、正式技能案例与历史验证记录 |
| build/ | [构建入口](../build/README.md) | 外部输入检查、原工程路径恢复、Vivado 构建脚本及综合实现报告索引 |
| board/ | [板端文件](../board/README.md) | 启动与控制脚本、接线和触摸记录；板级实测输出另存 `results/` |
| data/ | [数据入口](../data/README.md) | 真实采样回放、测试输入、模型及参考结果 |
| skill/ | [技能包](../skill/README.md) | 适用场景、使用方法、接口契约、失效条件、案例与已验证效果 |
| report/ | [报告入口](../report/README.md) | 设计报告、中英文海报和开发协作记录 |

指南允许其他组织方式，但要求在 README 中提供目录对照。因此不为套用示意树而移动现有模块，避免破坏源码导入与历史报告路径。

## 工程包与证据

| 指南项目 | 资料位置 |
| --- | --- |
| 设计源码、工程文件 | `src/`、`fpga/`、`embedded/`、`host/`、`deployed-build-source/`、`configs/`；历史源码差异位于 `archive/source-variants/` |
| 仿真或验证结果 | `sim/`、`tests/`、`fpga/tb/`、`results/p07-fir-rtl-20261011t035739182285z/` |
| 综合与实现报告 | `results/p07-fir-timing-20261011/`、`results/p37-safe-route-20261021t084904z/`，含时序、资源、DRC 与 CDC 等记录 |
| 上板工程、运行脚本与实测结果 | `board/`、`embedded/`、`host/`、`experiments/`、`results/`；识别独立验收见 `results/p52-arm-20261024t075009z/` |
| 构建脚本 | `build/`、`fpga/fir-vivado/`、`fpga/fft-vivado/` 及阶段构建脚本；准备步骤见复现说明 |
| 技能包的提炼与验证 | `skill/verify-fixed-point-fir/`、`sim/fir-skill-validation/` 及设计报告 |
| 大模型协作记录 | `report/development-chat/`，含已留存的提示词、模型回答及纠错过程；这是指南明确要求的提交材料 |
| 开源协议及第三方来源 | `license.txt`、`notice.md`、`source_manifest.json` |

## 文件组织与验证范围

目录和文件名使用英文、小写字母、数字、下划线或连字符，扩展名保留小数点；指南明确给出的 `README.md` 与技能加载约定的 `SKILL.md` 保留固定写法。中文用于正文内容。

正式 ZIP 直接打包仓库文件，不再附加另一套原始工程、重复报告、嵌套备份或面向队友的交接文档。历史实验记录属于验证依据，不能用清理备份代替对失败与结果边界的说明。

当前采用 Vivado 2021.1，版本差异已在设计报告与复现说明中披露。公开文件包括已提供的源码、脚本及证据；完整厂商工程、迁移输入和启动镜像的准备条件见 [复现说明](reproduction.md) 与 [第三方说明](../notice.md)。尚无干净环境完整硬件重建的验收记录，不以目录齐全代替复现验收。

信道质量评估为报告中的参数分析和应用设计，未实现自动评分、信道排序和现场诊断程序。视频由队伍单独提交，本工程包不包含未提供的视频文件。
