# P33：ADI DMA 停止、排空、重新启用与复位契约审查

日期：2026-10-20，北京时间。范围：只读检查供应 RTL、已归档供应驱动、P32 测试源与实验记录；没有操作板卡、串口或软件界面，没有修改供应 RTL、稳定 P30 工程或 P32 候选。本文是源码契约审查，不能替代新仿真或上板结果。

## 结论

1. 本版本 `enable=0` 表示停止接收新工作并结束已承担的协议义务，再排空和对齐内部 ID；不表示立即撤销 AXI 事务。禁止通过丢弃已经握手的 AXI 请求来构造“成功 abort”。
2. 在时钟持续运行、外部 AXI 对端继续响应且 FIFO 消费者接受最后一个在途拍的条件下，源码包含不依赖全局复位的重新启用路径。测试应先验证这一路径；不能一失败就补复位然后声称普通 abort/re-enable 通过。
3. 实际两种配置的内存域与请求域同钟且相应 ASYNC 参数为 0，所以该内存侧内部复位取自 `req_aresetn`，单独拉低未选中的 `m_*_axi_aresetn` 并不能测试内存端点复位。任意单域、在途复位后的透明恢复不在现有证据内。
4. P32 bench 只在排空后停止，原先把 FIFO 的 `wr_en/rd_en` 与顶层 `enable` 相与是该有限测试的前提。直接把相同夹具移到中途停止会令 TX 消费者停止接受最后一拍，可能人为造成死锁；这是需要修正的夹具前提，不能据此认定供应 RTL 已有 abort 缺陷。

## 源码证据与含义

供应目录：[axi_dmac](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac)。以下行号对应本次直接读取的未修改文件。

| 证据位置 | 直接观察 | 对测试的要求 |
|---|---|---|
| [address_generator.v:97](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/address_generator.v:97)、第 103–106、143–150 行 | 已拉高的地址 valid 必须等 ready 接受，才能关闭地址生成器。disable 后不再生成新的未承诺地址。 | 不能因 enable 下降就清除 AW/AR 队列、禁止地址 ready 或要求 valid 立即变零。 |
| [data_mover.v:104](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/data_mover.v:104)、第 111–120 行 | FIFO/AXIS 类端点 `DISABLE_WAIT_FOR_ID=0` 等待当前 valid 拍被接受；MM 默认模式等待 `response_id==request_id`，完成所有地址对应数据。 | disable 后继续发送 AR 已承诺的全部 R 拍，继续接收 AW 对应的全部 W 拍，保持阻塞时 valid/data 稳定。 |
| [response_handler.v:68](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/response_handler.v:68)、第 73–91 行 | B 通道处理器等所有响应结束后关闭。 | 模型继续产生每个完成写 burst 对应的 B，且保持 BVALID 直到 BREADY。不能把最后一个 B 丢掉。 |
| [src_axi_mm.v:128](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/src_axi_mm.v:128)、第 155–182 行 | MM 源先关闭地址生成，再由 data mover 按已产生地址 ID 收完读数据。 | TX abort 时不能立即清空 AXI 内存模型的读队列。 |
| [dest_axi_mm.v:108](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/dest_axi_mm.v:108)、第 163–217 行 | MM 目的端依次等地址、数据、B 响应结束；完全关闭后 `fifo_ready` 强制为 1，用于排掉遗留 FIFO 数据。 | RX abort 后仍需服务 AW/W/B；不要求被 abort 描述符完整写完，要求已承诺 burst 协议完整。 |
| [dest_fifo_inf.v:81](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/dest_fifo_inf.v:81)、第 87、93、120–128 行 | FIFO 消费握手依赖外部 `en`；关闭期间可把当前拍内部消费掉，但 `valid` 输出由 enable 屏蔽。关闭后强制 ready 排空。 | TX 读请求应在关闭过程中继续给出，允许已在途拍被内部丢弃；只能在 `rd_valid` 时计入对外有效数据。不能要求 disable 后保持原描述符全部 EOT。 |
| [src_fifo_inf.v:72](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/src_fifo_inf.v:72)、第 94–98、104–133 行 | FIFO 源不提供 backpressure；enable=0 继续写会产生 overflow。data mover 可在当前接受拍后停止。 | 对于以正确结束为目标的测试，停止新的源数据；持续 ADC 输入是另一种预期丢弃/overflow 场景，不能把停止期 overflow 一律判作 RTL 失败。 |
| [request_arb.v:802](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/request_arb.v:802)、第 808–809 行；[data_mover.v:153](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/data_mover.v:153) | 目的端 request ID 来自源端完成数据的 response ID；源 ID 只有完成 burst/末拍时前进（或停止后的 sync）。 | RX 目的 AW 的产生以完整源 burst 已进入内部 FIFO 为门槛。无并行复位/损坏时，停止源不应使已承诺 AW 缺少对应数据。仍要用模型逐事务核查，不能仅据源码代替运行证据。 |
| [request_arb.v:287](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/request_arb.v:287)、第 298–305、1081–1118 行 | 源和目的均关闭而 ID 未一致时产生 `sync_id`；重新启用等 ID 一致、两个 request 队列为空、source data FIFO 为空、sync 回执撤回。 | 关闭后等待真实内部关闭/排空，不以顶层 enable=0 或旧 EOT 数相等作为唯一验收。重新启用后用新数据标记检查无遗留拍。 |

## 有效的中途停止测试

建议至少覆盖 RX 的 W 回压和 TX 的 R 回压两个不同方向；两者使用不同的新旧 epoch 标记、非零且变化的数据、跨 burst 和跨 ID 回绕的后续新传输。

1. 先运行已接受的长描述符，确认正在传输且至少有一个非空在途事务。记录 enable 下降前后所有 AW/AR 握手和对应 W/R/B 的剩余量。
2. 在真实回压位置拉低 enable，停止提交新描述符。对已经完成 descriptor handshake 的工作不得在模型中提前抹掉；对被模型送出但尚未 ready 的 AXI valid 保持协议。
3. RX 允许源停止新增数据；AXI 目的模型继续接受所有已经拉高的 AW，完成相应 W，并返回 B。记录 abort 前后内存实际写入的地址/数据，不要求未完成描述符的剩余尾部必然写出。
4. TX 内存模型继续完成已产生 AR 对应的所有读响应。FIFO 消费器继续提供有限间隔 `rd_en`，包括 enable=0 之后；只对 `rd_valid=1` 的样本验数据。关闭期间因 valid 屏蔽而内部丢掉的旧数据不计为新 epoch 的有效样本。关闭期的预期 underflow 单独计数，不能沿用 P32 全程零 underflow 的断言。
5. 等待两端关闭，所有外部承诺事务完成/响应返回，内部 request 队列和 FIFO 清空，ID/sync 握手完成。设有界超时并在超时时保存所有关键状态及未完成事务队列，不能只给“没有 EOT”。
6. 不复位直接 enable=1，再提交地址与数据都不同的短/长描述符，检查完整长度、地址、WLAST/WSTRB、所有有效输出及 EOT；必须无旧 epoch 串入。停止/重启重复多次。
7. 另做“故意不响应最后一个 AXI 请求”的负对照：应保持未完全关闭且不得把它报告为普通 abort 失败。这是对端违约/永久停顿，不是证明 RTL 无法停止。

原 [P32 bench](../../fpga/tb/tb_p32_fifo_mm.sv-101) 在第 101、104 行把 `wr_en` 和 `rd_en` 都绑定 enable；第 126–127 行先等待全部目标数据和 EOT 再关闭，所以已有通过结果与此限制相容。新 abort bench 必须修改这一前提，保留 P32 历史结果的原始范围。

## 复位契约及能说明什么

[request_arb.v:340](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/axi_dmac/request_arb.v:340) 至第 385 行：异步端点通过 3 位移位寄存器异步置复位、按各自时钟延迟释放。ASYNC 为 0 时，该端点直接使用 `req_aresetn`。FIFO 类型的异步端点复位源也是 `req_aresetn`；只有异步 MM 类型选择对应 `m_*_axi_aresetn`。

[util_axis_fifo.v:65](E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library/util_axis_fifo/util_axis_fifo.v:65) 起的单槽队列、以及普通灰码 FIFO 的两侧，各自复位写指针和读指针；它们没有独立的“丢弃 epoch/重置另一侧指针”握手。仅复位一侧可改变空/满解释，存在旧数据或指针错配风险。因此现有源码不构成“任意一侧在有数据时复位，其他域无需协调即可恢复”的承诺。

对当前实际配置的合理下一项试验是：全局协调复位（请求域、选中的 MM 内部域、FIFO 两侧），并让采样时钟在释放时暂时停止；重新给足采样时钟边沿后再启用新标记传输。复位置低必须真正到达各同步复位逻辑：可先保留各时钟运行若干边沿再暂停采样钟；不能只给停钟域一个未被任何边沿观测的窄同步复位脉冲。若暂停发生在释放时，源/目的 reset shift 应在恢复时钟后的至少 3 个边沿后才能释放，再留出同步/队列稳定时间。

该试验通过只说明选定暂停/恢复顺序下的协调复位恢复。不能由它宣称所有单侧复位、总线侧不复位仍保留外部 outstanding、任意停钟或元稳态问题均解决。

若独立复位确属整机要求，先定义系统级顺序：禁止新提交 → 对外完成/撤销 outstanding 的统一 AXI 复位契约 → 协调相关 FIFO 两侧与仲裁域复位 → 恢复时钟和同步复位释放 → 软件重建/重新提交。不能仅改一个同步器或拉一个域复位来推定全链路恢复。

## 驱动所表达的意图与限制

归档供应 [dma-axi-dmac.c:325](../../results/p32-driver-contract-20261020t043240z/drivers__dma__dma-axi-dmac.c.txt-325) 的 `terminate_all` 只写 CTRL=0 并释放软件描述符；[第 351 行](../../results/p32-driver-contract-20261020t043240z/drivers__dma__dma-axi-dmac.c.txt-351) 的 `issue_pending` 写 CTRL_ENABLE，再提交新描述符。这支持“正常 terminate/restart 不需要硬件全局 reset”的设计意图。

但 `terminate_all` 内没有等待 RTL 全部排空的轮询，第 344–348 行的 synchronize 仅调用 `vchan_synchronize`。不能把该 C 函数返回当作内存端已无在途写的独立证据。是否需要在用户态释放/改写 DMA 内存之前补充硬件排空屏障，应结合实际 IIO/DMA 生命周期和运行结果继续审查；本次没有重现相应内存安全问题，也没有据此修改驱动。

## 关闭问题所需的证据

- 普通 abort/re-enable：上述协议正确模型下，两方向有限用例和多次新 epoch 重启通过，保留失败日志、源快照与参数。只有重新 enable 成功，不能替代旧事务与数据校验。
- 协调复位：明确实际配置的复位连线，暂停/恢复时钟的限定顺序，用新 epoch 检查恢复；独立单侧复位仍单独列为未验收。
- 物理 CDC：有限数字仿真仅验证逻辑流程。ID 比较组合逻辑、元数据建立/保持、空满跨域、物理时序与同步器实现仍要逐组复核，不能据本笔记或一组通过日志豁免 58 条告警。
