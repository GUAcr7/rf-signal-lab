# 从这里恢复项目工作

**P49迁移进行中（2026-10-23）**：先读[本轮记录](docs/experiments/exp-p49-persistent-units.md)和results/p43-active.json。COM8已恢复，实读新boot ea7d8bca-132c-4769-a7e0-b326915c2bee，旧应用观察/停止/归档通过。原启动选择暂时暂停，正在安装独立P48 profile并做软件重启验证。不要按下方昨日状态重复操作；未通过最终记录前不能认定P48自启动已完成。

---

**当前硬件应用入口：P48（2026-10-22）频偏单位候选已实板验证，持久迁移待完成。** 先读[实验记录](docs/experiments/exp-p48-display-units.md)、[恢复清单](docs/handoff/resume-p48-20261022.md)及TX-SOURCE-STATUS.json的p48_current。32项原生检查、ARM编译、10秒/20次写屏、原始前缀与显存独立复核、三项单位逐像素核对通过。

**当前最后画面是P48，默认自启动应用仍是P42。** RX idle、资源释放、串口关闭，板仍通电未关机；已恢复原已验收P43 wrapper及P44防休眠。P48完整新profile仅在电脑准备，未安装、未做P48新启动/真断电验收。恢复时重新读boot/进程/DMA，不重放旧身份，不热卸驱动或绑定中装PL。

下一步参数化并测试启动工具后迁移完整P48 profile，做新启动/时钟/单位/原始数据验证。历史0xFF/波动根因、长稳/时序/无损连续性、独立真实AI仍开放。本轮未开启TX，+30kHz峰值来自未知输入，不是已识别目标。

**P47软件学习包仍可使用：** 根目录`run-rf-learning-demo.cmd`；[中文说明](deliverables/rf-learning-kit-20261022t130520z/README.md)；[交付记录](docs/experiments/exp-p47-learning-kit.md)。它是离线学习工具，不改板卡，也不是独立AI测试集。

本轮检查点：`results/p48-checkpoint-20261022T134430334243Z/report.json`。results不在Git，直接读文件系统。旧入口：[历史快照](start-here-before-p48-save-20261022t134430z.md)。
