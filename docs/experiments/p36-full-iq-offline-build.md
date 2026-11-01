# P36：完整返回缓冲采集器离线实现与构建

- 日期：2026-10-21。
- 范围：仅新增 P36 源码、模拟库、测试、构建脚本和文档；未修改 P27 稀疏采集器，没有串口/板卡/界面操作。
- 结论：**实际 C 的 25 项主机模拟测试通过，ARM 交叉构建及 ELF 检查通过；真实板端执行未尝试。**

## 实现

[arm_rx_full_p36.c](../../embedded/arm_rx_full_p36/arm_rx_full_p36.c)只复用既有已验证的 IIO 0.x ABI、libiio 0.20 版本检查、固定 RF 前后只读核验和 RX1 两通道布局合同。保留全部 packed 源字节，每块 65536 帧、4 B/帧。默认 16 块=4 MiB，CLI 允许 1–64 块；当前不开放 512 块，避免在缺少实时可用内存依据时自动分配 128 MiB 并再次落入 tmpfs。

目标内存和时间表先分配并预触页，含未按页对齐分配的最后一页。只有一个 IIO buffer；每次返回后检查字节数、步幅、I/Q 地址和结束位置，立即整块复制到独立槽位。没有逐块文件写入、日志、分析或绘图。启动日志在创建 IIO buffer 前刷出，避免已启动 DMA 后等待串口输出。

主线程用单调时钟观察 15 秒采集限额与停止信号；signal handler 只置标志，取消 API 由普通主线程调用。主线程有界 join 后才销毁 buffer/context、执行 RF 后读回和写文件；join 失败退出 3、标记清理未确认，绝不销毁 worker 仍引用的内存/资源。

完整/部分结果采用独立 `rfsig.full_returned_buffers.v1` schema。`iq-packed.bin`只含已完成块，不补零；时间表也记录失败的最后一次 refill。`complete_returned_buffers_saved`与完整请求通过分别报告，`complete_stream_saved=false`、`lossless_proven=false`、`hardware_gaps=unknown`不变。高 4 位按原样保留；解释信号时必须掩低 12 位并符号扩展，不能直接按已符号扩展 int16 读取。独立审查提出的观测改进已实现：RF 首个字段异常不再提前结束其余字段读取，失败后仍保存实际 before/after 值及逐字段读取状态；固定布局声明另附 `scan_layout_validated`，不把 preflight 失败时的期望当已验证读数。

## 离线验证证据

最终冻结输入与构建：[report.json](../../results/p36-full-rx-build-20261021t031400z/report.json)。

| 检查 | 实际结果 |
|---|---|
| [实际 C 模拟测试](../../tests/test_native_rx_full_p36.py) | 25 passed，无跳过 |
| 默认 16 块字节逐点比对 | 全部 4 MiB，包括块尾和未定义高位保留 |
| 64 块上限 | 16 MiB 完整保存，64 个时间表项 |
| 配置/格式/BIST/版本/布局/短返回失败 | 拒绝通过；清理或部分输出符合合同 |
| SIGTERM 取消 | 普通主线程取消、join 后释放、保存已完成 3 块 |
| 故意不响应取消的 mock worker | 退出 3，未销毁活动 buffer/context，输出清理未确认 |
| 输出已存在/非法块数 | 采集前拒绝，不覆盖 |
| GCC ARMv7 Cortex-A9 hard-float | 编译退出 0；Wall/Wextra/Werror |
| ELF | ELF32、ARM、小端、VFP 参数、armhf loader、pthread |
| 版本化 GLIBC 需求 | 最高 2.4，未高于已知接收板 2.23 |

二进制：[arm-rx-full-p36](../../results/p36-full-rx-build-20261021t031400z/arm-rx-full-p36)，31740 B。

- 二进制 SHA256：`b7db8cbf5502516075386c49c91d9de7f516e582d15964b61b620628df31fcb5`。
- 源码 SHA256：`0e3e7cdbd32ad82c4593cce502d1f8e8f00306c81f5d383edf5e7b750e78e307`。
- 固定头文件 SHA256：`e20a69cdef4654261b56cc5970bb91a9aacc3643ab0357b7f571aad9559a583d`。
- 完整输入副本、pytest/JUnit、编译/ELF 输出均在最终构建目录。`030757Z`、`030955Z`为两次观测改进前的离线检查，保留取证；部署请使用本段最终 SHA。

## 交主任务的最小上板步骤

1. 当前 RF/显示合并候选先按自己的启动/空闲合同验收；本文件不允许推断它已通过。
2. 独立绑定当前 boot_id、运行 PL/DTBO、RF 固定配置、实际 libiio 0.20 和内存余量，确认无另一个 RX/TX 会话。RF 不满足固定合同会安全拒绝，程序不替用户改配置。
3. 上传最终二进制并核 SHA，首次不发射、默认 16 块。**输出目录由程序创建，控制脚本不要预先 mkdir。** 运行语法和退出码见 [README](../../embedded/arm_rx_full_p36/README.md)。主机控制保留外部超时；若超时/退出 3，停止后续操作并独立检查清理状态。
4. 读回 buffer/scan 空闲、内核新增错误和 RF 前后配置。检查 16 块=4194304 B，板端/电脑 SHA一致，并归档整个输出目录。板端 SHA由主机调用已存在工具计算，未在 C 热路径加入哈希。
5. 仅在以上通过后，按 [完整 IQ 合同](p36-full-iq-contract.md)安排已知源跨块验证。仅凭完整字节、refill 顺序和软件计时不能宣布 ADC 无丢样。

尚未验证：真实板端线程取消/完整 memcpy 时延、DMA 连续性、完整采集与屏幕并行吞吐、板端文件回传及已知源质量。主机 mock 结果不替代这些硬件结果。

## 独立串口执行器（仅实现/离线测试，未执行）

新增 [p36_full_rx_run.py](../../experiments/p36_full_rx_run.py)，仅显式执行 main 才打开一个 COM8、DTR/RTS 关闭的 BoardConsole；复用既有 AuditPort 记录所有 UART 字节及 p35_uart_files 上传小二进制。它在操作前核验全部构建输入/二进制 SHA、期望 boot_id、RF 配置、taint=0、RX 空闲、RF 三设备、无竞争进程及可用内存。它不修改 RF、PL、overlay 或启动配置。

外层 `timeout -k 2 28` 对本轮程序提供 TERM/KILL 总 30 秒边界；调用单次读取 40 秒，其他单次读取不超过 30 秒。若返回帧缺失，不向可能仍活动的程序继续灌命令，而是标记状态未确认并关闭本机句柄。原生 completion 与 metadata 必须同时通过；独立读回 buffer/scan/RF/boot 与内核状态通过后，才允许 gzip。完整 4 MiB 仍留在板端，仅取 SHA/wc 和小元数据；报告明确“待主机完整回收”，不宣称回传验收或无丢样。

离线检查：[report.json](../../results/p36-full-runner-check-20261021t031917z/report.json)，**22 passed**，输入哈希固定；测试直接使用实际 C mock 产生的 metadata/completion，覆盖虚假连续性标志、未释放/未 join、布局未验证、字节错、索引错、时间逆序/NaN、缺帧/重复 completion 和本地证据路径拒绝。没有打开串口。该报告固定执行器 SHA `938bff34abd83f1f51e13ecd417286024e4d50f1031c559a46818779c511bbb0`。

供主任务审查后显式执行的命令形式：

```text
.venv\Scripts\python.exe experiments\p36_full_rx_run.py --expected-boot CURRENT_BOOT_UUID --build-report results\p36-full-rx-build-20261021T031400Z\report.json
```

默认 16 块，不为测试另建目录；接收程序自己创建唯一 `/tmp/p36-full-HHMMSS`。此处的 CURRENT_BOOT_UUID 必须来自主任务刚确认的本次启动，不能把本文或过往试验中的 boot ID 机械重放。运行 PL/设备树的对应和时钟异常必须由当前合并试验先判定，本执行器不以“fpga operating”替代那项验收。
