# P36 新启动单次试验：独立只读复核

- 日期：2026-10-21。
- 复核范围：START-HERE、RESUME-20261021、P35 单次加载脚本、hold 模板、UART 上传工具、配对 TTL33 位流与显式加载 DTBO 报告，以及本日已有固件回读证据。
- 本审查未连接板卡、打开串口、运行试验 main 或修改现有代码、配置、实验记录。仅运行主机端纯输入校验与解析，并新增本文。
- 结论：已确认运行时 staging 哈希阻塞在本次修改中修复；当前未发现新的 P1 执行阻塞或会遗留实验启动默认值的问题。允许继续既定的单次受控试验。这是脚本及输入复核，不是硬件成功验收。

## 已修复的执行阻塞

**P1：把模式派生的 staging 文件当作固定 display 文件。**

位置：`experiments/p35_once_merged_trial.py:165` 的 `factory_files()`；依据：`board/boot/S99board:132` 起根据当前模式比较并复制选定位流到 `system_wrapper.bin`。

旧条件会要求 `system_wrapper.bin` 等于 display/wrapper 备份 SHA `12566368…11286e`，而本日正常 RF 启动实际会生成 RF SHA `65b44449…2950a`，导致健康启动在真正试验前被拒。`results/p35-firmware-readback-20261021T025626Z/report.json` 记录了 boot `3e2ecb94-6929-4744-9d00-5e5f888f56c7`、taint=0、mode=rf，以及 wrapper 与 `ad9361.bin` 均为 RF SHA；启动日志同时记录 S99 的 staging 操作。

当前修复保持 `ad9361.bin`、`display.bin`、两个默认 DTBO 的逐字节固定哈希门槛，仅对派生 wrapper 接受上述两个已核验厂家版本，并逐次保存实际 SHA、时间、阶段及 role。位流原报告中的 FACTORY 字段仍是构建时来源约束；不会因运行时 RF staging 而改写旧证据。独立实验位流与 DTBO 继续使用各自唯一文件名及原始 SHA 门槛。

复测要求：本次试验 report 应在上传前、上传后、fresh hold 后及最终检查保存 staging observations；不能把正常 S99 staging 表述为实验修改了厂家固件。若出现两个允许值以外的 SHA，应停止。

## 非阻塞改进

**P2：设备异步 probe 的固定等待可能产生假阴性。**

位置：`experiments/p35_once_merged_trial.py:279`；当前 overlay 写入返回后仅等待 2 秒即要求 RF 名称、DRM 与 fb0 均存在。已读正常启动证据中 ADC/DDS 也存在异步出现过程，尚不能证明所有启动中 2 秒足够。

影响：可能把仍在完成的 probe 误报为失败；当前失败分支只保留被动日志并释放串口，故此项不构成重配置风险，也不会制造假通过。最小改进是将来改为有总时限、只读的就绪轮询，不增加 overlay apply、PL programming 或热卸载次数。本轮若仅因名称暂缺失败，应先用已有日志及一次后续只读现场确认，不重复加载。

## 关键机制复核

1. **上传与身份。** UART 包装器记录实际读取的 RX 字节，包括上传工具主动 drain 的数据；命令输出另外归档。上传只使用独立 RAM 路径，事后核验 SHA。长上传后再次核验原 boot ID、taint、空闲 RX、固定文件与 guard，再安装 hold；不会把同名板的另一次启动默认为同一现场。
2. **压缩传输。** gzip 仅作传输包，mtime=0、host 回解压逐字节比对；板端先验证压缩包 SHA，再 `gunzip -t`，解压到不存在的独立 RAM 目标，验证原生位流 SHA 后才复制唯一 firmware 文件并再次验 SHA。送入 FPGA 的仍是原始 5,709,252 字节 `.bin`，不是 gzip。该增量未改变 DTBO、hold 或显式一次加载顺序。
3. **fresh hold 与恢复。** 安装前备份并核验原 guard。hold 限制为新 boot，先恢复、同步并复核原 guard，然后才写 hold marker；模板不装 PL、不应用 overlay、不发射。host 看到恢复后的 guard SHA 后才清除 armed 标志，并要求新 boot marker、空 overlays、无 RF/显示实例。异常分支保留 pending hold 状态，禁止盲目热回滚。下一次普通 RF 启动仍由原 guard 选择厂家 RF 文件。
4. **时钟解释。** 解析明确依赖本内核 `clock enable_cnt prepare_cnt rate accuracy phase` 列契约，拒绝同名时钟。检查 fclk0/fclk1/clk_out1 的 rate 列；不会把 enable count 当作频率。结果作用域仅为软件读回，不能代替 PLL LOCK、物理像素时钟或显示实效证明。
5. **验收边界。** 成功状态明确仅涵盖 fresh boot、合并 probe 与软件时钟。脚本不启动 TX、不抓取 RF 数据；即使返回 passed，仍不能验收真实接收性能、画面刷新与 RF 并行持续运行、外部 I/O 时序或 CDC 生产闭环。

## 本次主机端纯校验

复核的 `p35_once_merged_trial.py` SHA256：

`74fa93488ea755a0465fe3e986023a43d33c80419aae9073c6d14b4e1e349f57`

- `validate_inputs` 对配对的 P35 位流、DTBO、来源 BD、来源 DTS、报告及无 firmware-name 约束：通过。
- 5,709,252 字节位流压缩为 1,037,112 字节，host 解压完全相同；压缩包 SHA256：`4290eef5766f64122b283968bac9db4d5eca66e9a0087af96fe96cd8879164fb`。
- hold 模板占位符替换、恢复 rename 先于 marker：通过。
- 当前 Python 语法解析：通过。
- 对已有真实 clk_summary，解析 fclk0=99,999,999 Hz、fclk1=199,999,998 Hz，均满足脚本的 1 kHz 容差；重复 clock 名称拒绝：通过。审查首轮离线断言误用了整数标称值完全相等，随后按真实值及既定容差更正并复测；这不是被审脚本缺陷。
- 未运行硬件试验；原有静态测试结果不冒充本次新脚本 SHA 的完整回归。

## 下一步依赖

1. 保存本次脚本、hold、输入 artifact 与 UART 原始日志，执行既定的一次 fresh hold、一次 PL programming、一次 overlay apply。
2. 先按 report 的确切失败阶段和原始 UART 核验；若成功，只接受脚本承诺的有限作用域。若等待不足，先做只读 probe 确认。
3. 只有新 TTL33 合并设计的基础状态健康后，才安排独立 RF 缓冲接收、显示实际输出、并行稳定性验证，并继续保留 CDC、外部 I/O 约束未关闭的限制。

可转交执行口径：保持当前唯一 firmware/DTBO 和恢复 guard 方案，只运行约定的单次试验；失败不热卸载、不重装、不自动重试。根据原始 UART、boot ID、SHA、恢复 marker 与驱动/时钟实际读回判定阶段结果。任何 passed 均不外推到真实 RF 接收、物理时钟或并行显示的最终验收。
