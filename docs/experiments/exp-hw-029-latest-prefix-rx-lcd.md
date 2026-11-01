# HW-029：单接收缓冲、最新数据频谱与实体LCD动态确认

日期：2026-10-21（北京时间）。本轮由用户授权继续推进；先处理COM8连接问题，受控新启动恢复P37合并配置，再推进板端监测软件。没有启动TX，没有改默认厂家固件或BOOT，没有设置自动启动。

## 验收结论

从P38每轮重建接收上下文推进到P39一个会话只创建一个RX上下文和一个65,536帧缓冲：工作线程反复refill，界面按500ms请求节奏消费最新8,192帧前缀，FFT和绘图不阻塞接收线程。两分钟硬件试验完成235次分析/写屏，结束后独立读取同boot、taint0、RF参数未变、buffer/scan全0；SIGTERM取消另有实板记录。用户先答“只能看到停止画面，没观察到更新”，后来明确回复“这次可以看到运动的画面了”，因此补充实体动态画面确认；没有据此宣称实际LCD FPS、全部数字变化或全程无闪烁已人工测量。

这是有界单缓冲监测，不是整流无损记录：每次refill仅将前8,192/65,536帧放进一个最新值信箱，界面未消费的旧前缀允许被覆盖。每会话只保留最后实际显示的32,768原始字节，均已电脑归档和独立NumPy复算。其余refill内容没有保存，UI覆盖计数不是ADC丢样计数，无硬件ADC序号/overrun证明，lossless=false、ADC gaps unknown。未知RF输入，不把DC附近峰当作已知目标，不输出校准dBm或AI类别。

## 启动与连接证据

- `results/p32-preflight-20261021T134617Z/report.json`及`...T134838Z/report.json`：CH340的COM8开口前报Windows设备错误，COM9仍可读。用户重插后仍失败，换USB接口后恢复；没有重装驱动、没有把连接恢复当作固件修复或认定唯一线材根因。
- `results/p32-preflight-20261021T135359Z/report.json`：新厂家启动036b1129-6524-443f-8b07-f724341ff1fd，RF_READY、taint0、idle。
- `results/p35-once-merged-20261021T135711Z/report.json`：一次hold新启动，boot=3c107af6-dcab-4ab0-8269-7f0f3a050390；恢复原guard后确认空绑定，单次装P37安全位流及配对显式overlay，RF+fb0通过。新增可选复用已验证板端产物，前后读SHA，不复用旧boot/保护状态。此次PL上传0字节但确实执行1次PL配置；不把“免重复上传”写成“免配置”。
- `results/p36-clockwiz-readback-20261021T135909Z/report.json`和`results/p37-clock-accept-20261021T140135Z/report.json`：LOCK1，M16.5/D2/O25，软件率与寄存器一致；不是仪器实测PCLK。
- `results/p35-finite-rx-prep-20261021T140136Z/report.json`：有限RX测试配置读回；`results/p33-rx-cancel-board-20261021T140459Z/report.json`：8轮取消/重建；`results/p36-sparse-smoke-20261021T140545Z/report.json`及`results/p36-panel-snapshot-20261021T140748Z/report.json`：布局/分析/绘图基线。

## 实现与测试

- `embedded/arm_latest_panel_p39/arm_latest_panel_p39.c`：互斥信箱+原子停止标记；refill逐次核验长度、布局、I/Q位置；low12掩码后符号扩展；RX结束先cancel并限时join，再销毁buffer/context。取消卡死走保守退出，不能提前销毁工作线程占用资源；RF前后读值一致、无TX API。
- `tests/test_native_latest_panel_p39.py`：18项实际C+mock动态库测试，覆盖单buffer、源序列/原始字节、独立数值、覆盖计数、异常布局/读取错误、真实SIGTERM、RF变化、不返回线程及参数边界。
- `tests/test_p39_summary_gate.py`：9项；`tests/test_p39_artifact_reuse.py`及`tests/test_p32_hold.py`：14项；`tests/test_p38_runner_gate.py`：更新后5项。保留严格路径、身份、同boot/idle截图父证据门槛。
- 第一构建`results/p39-build-20261021T140358Z`用于3秒基线；`results/p39-build-20261021T141323Z`用于取消、60秒和120秒；源/二进制SHA及输入快照保留。18项测试通过，ELF32/ARMhf/小端及GLIBC<=2.23检查通过。

## 实板结果（各次均单独结束并独立确认idle）

| 报告目录 | 软件时长/结束方式 | 发布/显示/覆盖/末尾待消费 | 验收范围 |
| --- | --- | --- | --- |
| p39-board-20261021T141057Z | 3.005秒，正常 | 1408/6/1401/1 | 初始单缓冲短测 |
| p39-board-20261021T141438Z | 3.015秒，SIGTERM | 1413/6/1406/1 | 主动取消、join和释放，summary=stopped，非时长完成 |
| p39-board-20261021T141547Z | 60.004秒，正常 | 28126/118/28007/1 | 固定配置一分钟监测 |
| p39-board-20261021T142055Z | 120.006秒，正常 | 56252/235/56016/1 | 两分钟监测与后续用户动态画面确认 |

以上均满足发布=消费+UI覆盖+末尾待消费。120秒记录maxrss=2588KiB；不能用单个进程峰值证明长期无内存泄漏。处理/绘图计时只对应CPU段，不能换算物理LCD FPS或ADC吞吐、端到端延迟。

## 屏幕复核后的小修复

两分钟结束后的framebuffer回读`results/p39-offline-review-20261021T142821Z/screen.png`显示底部RX STOPPED，但顶部残留RX active。这是状态提示缺陷，旧图/旧报告保留。已将顶部同步改成RX STOPPED或请求停止/失败并保留最后update/source序号；最终构建和短测证据见下方当前交付。两分钟实板证据属于修复前二进制，不能宣称修复后的精确SHA已经运行两分钟。

离线并行复核曾同秒创建相同输出目录而报FileExistsError，没有覆盖旧结果；目录时间戳增加微秒后60秒数据复核通过。未把此主机归档问题归因硬件。

## 剩余边界和下一步

厂家冷启动PRODUCT_ID_FF根因仍未关闭；此次厂家重入和hold成功仅增加启动样本。无自动合并启动、无无限运行/故障自恢复验收、无ADC连续性证明；58项Critical CDC、7输入/29输出延迟缺项、外部PCLK仪器验证仍开放。已知源RF质量和真实AI是后续独立验收任务。禁止热卸载RF/ADC/PWM/显示驱动或在驱动绑定时重配PL，禁止活动DMA改时钟。先做受控重复启动/0xFF诊断及有界长测恢复，再做可回退启动和已知信号/AI。

## 当前交付与可恢复记录

- 最终构建：`results/p39-build-20261021T142930Z/report.json`，SHA `777b93620f211f4e516c5a17a1bc703c6da06663a9afeff9c9a1c3fe72f4c925`，50904字节；18项native mock测试通过。
- 状态提示修复后的3秒实板短测：`results/p39-board-20261021T143048Z/report.json`；显示6次，正常停止并独立idle核验。
- 最终IQ归档：`results/p36-file-archive-20261021T143223Z/report.json`；最终framebuffer快照/归档：`results/p36-fb-snapshot-20261021T143144Z/report.json`、`results/p36-file-archive-20261021T143549Z/report.json`。
- 最终独立复核及回读图：`results/p39-offline-review-20261021T143615206174Z/report.json`、`results/p39-offline-review-20261021T143615206174Z/screen.png`；五项NumPy比较通过，图已人工查看，顶部/底部均停止。回读图不是实体照片。
- 五次会话的最后显示前缀、原始UART、机器摘要与独立复核索引：`results/p39-checkpoint-20261021T143630550744Z/sessions.json`；用户原话及范围：`results/p39-checkpoint-20261021T143630550744Z/human-observation.json`。
- 当前权威状态：TX-SOURCE-STATUS.json的p39_current；恢复步骤：`docs/handoff/RESUME-P39-20261021.md`。当前无后台RX/TX，串口已关，未发关机/断电命令。普通重启仍回厂家RF-only，临时RAM和PL应用状态不能靠断电保存。
