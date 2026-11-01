# P48：小屏频偏单位改进与实板候选验证

日期：2026-10-22（北京时间）。继续用户同意的小任务，将显示的FFT频点编号换成直观的频偏和采样参数。本轮未开启旧板TX、未改变射频属性、PL、设备树、驱动或电源，不热卸载，不重启。

## 开始状态与实现

只读检查`results/p43-status-20261022T132457Z/report.json`：新板boot `343afe82-88e6-4a03-a5d4-c09ee6929e36`，taint0、RX buffer/scan0、无接收进程、持久wrapper选中且无pending/disabled。沿用P37合并硬件及P44防休眠设置。

在独立目录embedded/arm_panel_p48、embedded/arm_live_panel_p48保留修改版，旧P42/P46代码和已验收二进制不改。采集和生命周期引擎仍P42，JSON显式增加display_revision=p48、实际采样率、FFT间隔和频偏Hz；不把绘图改进声称新采集算法。

采样率只在AD9361读回并验证后传入显示。1024点FFT、30.72MS/s意味着30kHz/格，+33格应显示+990.0kHz，−33格为−990.0kHz；零输入显示none，未知采样率不猜Hz。界面加入MHz横轴、采样率MS/s及FFT间隔kHz，保留RMS、数字功率口径与no AI。

## 检查与原始证据

构建`results/p48-build-20261022T132941Z/report.json`：32项主机C原生模拟检查通过，覆盖原P42资源释放/取消/错误/有界日志及10组正负、零、边界、未知/不同采样率格式检查；ARM ELF32/hard-float/运行库兼容检查通过。候选ELF SHA `07a35338c6f87950e15126eefccc1d940f4e7fec5dafa4ba1b51247f1ad28b76`，55276字节。

主试验`results/p48-suite-20261022T133549Z/report.json`，短时原生接收/写屏10.009897秒、20次更新，结束后资源释放、RF属性不变、taint0。只保留最后实际显示的8192个RX1复数点/32768字节前缀，不是全流录制。

原始前缀和1536000字节显存均回传：`results/p42-review-20261022T133638Z/report.json`。独立NumPy对FFT峰值、RMS、总功率检查通过。`results/p48-unit-review-20261022T133717Z/report.json`用字体位图逐像素核对显示值：peak offset `+30.0 kHz`、sample rate `30.720 MS/s`、FFT spacing `30.0 kHz`；全部一致。显存图`results/p39-offline-review-20261022T133716638076Z/screen.png`已人工检查布局，属于回读图，不是实体小屏照片；本轮未新增实体可见性确认。

本轮没有已知源发射，因此+30kHz峰值只是当前未知输入/噪声的频谱结果，不能称作已识别目标，不能与P46已知单音的+990kHz直接当同条件频偏漂移。此改动不增加AI、EVM、绝对RF频率校准或带宽识别能力。

## 当前状态与持久化边界

为使用严格归档工具，试验期间只暂时将下一次S99board选择切回原guard，未执行original start、未改变当前运行硬件。结束后恢复已通过冷启动的P43 wrapper，`results/p43-enabled-20261022T133718Z/report.json`；只读终态`results/p43-status-20261022T133737Z/report.json`确认RX idle、无pending/disabled、串口关闭。板仍通电，未关机。

**当前最后画面是P48，但下次默认开机应用仍是P42；P48持久迁移尚未完成。** 不覆盖旧已验收profile的monitor。新完整启动候选包`results/p48-profile-20261022T134048Z/report.json`（提议目录`/etc/p43-20261022T134048Z`）仅在电脑准备，含monitor/bringup/boot/control/run/original及全部SHA，4份shell语法检查通过；原P43硬件初始化和13项shell门禁源码保持不变。该包未上传、未切换，没有P48新启动验收。

下一步先扩展并测试启动工具，显式接受P48构建和当前boot，移除旧P42构建路径硬编码；以新目录安装完整profile，做两个相同profile的新启动、原始IQ/显存/时钟及单位复核后再启用。准备包绑定的是本次boot；若下次boot已变，先重新认板并重新渲染，不能盲重放。P48真正断电与实屏确认单独保留待验收，不复用P45来冒充。

保存包`results/p48-checkpoint-20261022T134430334243Z/report.json`逐项SHA/ZIP CRC检查；P47离线学习包和一键入口继续可用。历史0xFF、波动根因、长稳/时序/连续性及独立真实AI仍开放。
