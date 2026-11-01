# P33：sync_id、排空返回与 EOT 槽寿命的定点审查

日期：2026-10-20（北京时间）。本记录先只读审查既有 RTL 与最终布线报告，随后在新 E 盘沙箱对注册 sync_id 候选进行独立数字仿真。原供应 RTL、约束、P30/P32 工程和父级 bench 均未修改；未访问板卡。候选尚未整合工程、重新综合/布线或硬件验收。

## 结论与范围

最终报告的 58 条 Critical 包含时钟 mux 两种模式下的重复端点。这里处理的 4 条 CDC-10 是 RX、TX 各一条组合 sync_id 路径在两种模式下的报告；2 条 CDC-12 是 TX 一条状态返回路径的两种模式。不能据此称为 6 个独立故障。

**当前最具体、可操作的结构修正候选是：将 sync_id 的比较结果在 req_aclk 注册后再跨域。** 这可以消除比较 LUT 位于首级同步器前的结构，但必须一起验证停止/重启握手；不能只插寄存器后清告警。enabled/empty 先取得实现网表的完整扇入和 clock 列表，不能仅凭 CDC-12 标题断言存在未同步信号。EOT 不应添加逐位同步器，应证明已发布槽的元数据保持到全部消费者退休，并检查物理建立时间。

证据：
- [最终 58 条分类](../../results/p32-final-cdc-20261020t105847z/report.json)
- [P32 实际端点有限仿真范围](../../results/p32-fifo-mm-20261020t110537z/report.json)
- 最终原始报告：E:/p30c-1019-174235/merged-route-cdc.rpt，SHA256 = eed638cb23602307273099e6ea8f64b4c560b4402408605e8b6ddbee8c9608fd。
- 本轮源代码根目录：E:/FPGA_Tools/Work/p29-vendor-20261019T082112Z/adi/library。下述行号均指该目录中当前未修改源文件。

## CDC-10：比较结果进入控制同步器

精确来源：
- axi_dmac/request_arb.v:287：sync_id = ~enabled_dest && ~enabled_src && request_id != response_id。
- 同文件 1081–1089、1101–1109：{do_enable, sync_id} 进入目的/来源域的 sync_bits。
- 同文件 299–303：重新 do_enable 要求回传 sync 为 0、ID 相等、两端 disabled、两个请求 FIFO 和数据 FIFO 空。
- util_cdc/sync_bits.v:59–70：只有目的域的两级采样；输入端没有源时钟寄存。
- axi_dmac/inc_id.h:38–65：ID 是 Gray 码；不能用二进制 ID+1 判断合法转移。
- axi_dmac/request_generator.v:75–92：reset 清 ID；do_enable 为 0 时 ID 停止，正常运行只在环未满且未 pause 时递增。

诊断：Gray ID 的相邻递增有单比特性质，但 request_id、回传 response_id、enabled_src 和 enabled_dest 可以在一个 req_aclk 边沿同时改变。多输入比较/门控在实现 LUT 中仍可能产生短毛刺。两级同步器降低其首级亚稳态传播概率，却不会把毛刺自动变成正确的同步协议。RTL 零延迟仿真也不能排除该毛刺。

最小候选：
1. req_aclk 上注册比较结果，reset 时清零；保持输出是电平请求，继续使用原同步器和返回确认。
2. 重新使能的判据显式要求注册后的 sync 请求为 0，同时保持返回确认、ID 相等和空状态判据。增加一周期后，不能出现“本地请求仍为 1、返回尚为 0、do_enable 已重新为 1”的窗口。
3. 若增加状态后仍存在请求/回传复位窗口，则使用显式停止/同步/确认返回的状态机；不要以延时若干周期替代确认。
4. 只在独立候选源码中实施，重新综合/布线并审查关键锥体，保证 LUT 不再位于跨域起点寄存器与首级同步器之间。

最小复测：实际 FIFO→MM 和 MM→FIFO，分别在未开始、请求已发出但无数据、半个 burst、末拍停顿、响应尚未返回五个位置撤 enable；ID 至少多次回绕；pause、目的回压、两种快慢时钟比。观察请求/返回的 0→1→0 全过程，确认停止最终收敛、重启后无旧数据/旧 EOT。独立复位必须按约定恢复全链路，不能把孤立一侧复位引发丢失仍记为正常完成。

## CDC-12：dest_enabled 与响应 FIFO 空状态汇合

精确来源：
- request_arb.v:1091–1099：i_sync_status_dest 输入为 {dest_enabled | ~dest_response_empty, dest_sync_id_ret}。
- 同文件 1018–1037：i_dest_response_fifo 的写侧 dest_clk，读侧 req_aclk；响应数据是单比特 EOT。
- util_axis_fifo/util_axis_fifo.v:67–85：写指针同步到读侧；读指针同步回写侧。
- 同文件 87–90：写侧 empty = ready = (s_axis_raddr == s_axis_waddr)。其中 s_axis_raddr 已经是写侧同步器输出，不能把它误称为直接来自 req 域的裸指针。
- axi_dmac/dest_fifo_inf.v:131–149：TX 的 dest_enabled 来自同一 dest_clk 的 response_generator。
- axi_dmac/response_generator.v:64、66–85：有响应且 enabled 时才 valid；停止时等本地 request_id/response_id 相等，最后响应写入后才允许清 enabled。

源文本中此 OR 的预期用途是：本地响应生成器已经停下，但最终响应仍在跨域 FIFO 中时，返回的 busy 保持为 1，直到请求域消费响应且读指针同步回来。源文本没有证明一个未同步 req 域信号直接进入 OR。报告的两种分频时钟名均可传播到同一个 mux 输出；是否是工具对同一物理寄存器多个 clock 的分类，或综合优化形成了额外跨域扇入，**仍待实现网表验证**。

关闭前必须从 routed DCP 提取：
- i_sync_status_dest 首级 bit1 的所有 sequential startpoints、对应 clock pins 与 get_clocks。
- 每个输入是否经过原有两级 raddr 同步；是否被综合重定时/优化旁路。
- 两种 mux clock 的互斥关系及运行时 clk_sel 的停止/复位限制。

若确认仅是多个互斥时钟名，且结构和功能保持证据完整，可提交有范围的审查结论，不应修改 RTL 只为改报告文字。若确有组合锥跨域/毛刺难以证明，则候选为 **在 dest_clk 上注册该 busy OR，再送入原返回同步器**；多一周期应只延迟排空确认，但仍须验证 busy 初次拉高、末响应写入与 disabled 的重叠，避免引入假空窗口。

最小断言：只要本地 response_generator enabled，或响应槽尚未获得读侧确认，busy 不得被返回为“可安全重新启用”；观察到最终 EOT 被消费之前，不能以本地 enabled 已清零作为全局排空依据。测试要压住响应 FIFO 读握手/等效返回时延；本实例 response_dest_ready 被常量 1 驱动，不能仅依赖顶层输入随机回压来覆盖该处。

## EOT：应证明槽寿命，而非逐位同步

精确来源：
- request_arb.v:326–329：每个 req_aclk 都写 eot_mem[request_id]，没有 valid 写使能。
- request_generator.v:70、82–92：eot 由剩余 burst 数决定；只有尾指针前进时才发布一个新的 burst。
- 同文件 87：response_id == inc_id(id) 时禁止前进，为 Gray 环保留一个空槽。
- request_arb.v:792–820：request_id→src、src_response_id→dest、dest_response_id→req 均通过对应同步器。
- 同文件 741/772、546–547/578–579：RX 来源 FIFO 与 TX 目的 FIFO 的数据/响应 EOT 由本地当前 ID 索引 eot_mem。
- data_mover.v:92–102、126–172：EOT 决定末拍、req_ready、ID 递增及 pending_burst。
- response_generator.v:61–64、78–85：响应传输携带当前槽 EOT；sync_id 也可以推进响应 ID，不能把这种推进统计成完成数据传输。

可验证的正常运行逻辑：
1. 当前 request_id 是尚未发布的空闲尾槽。连续写该槽不是覆盖在途槽本身。
2. 发布边沿上，eot_mem[旧 request_id] 写入最终 request_eot，同时尾 ID 前进。消费者要经过 ID 同步链才看见新请求，因此元数据有提前建立的逻辑窗口。
3. 环未满条件阻止在旧响应返回之前追上并覆盖在途槽。
4. 只有确认该槽对数据、地址和响应消费者均退休，才能允许后续环回复用。正常握手与 abort/sync 的退休依据不同，scoreboard 必须区别。
5. 独立复位可能破坏上述环的历史和寿命；这不是在复位外的源保持证明可以自动覆盖的情况。

提供给 abort bench 的具体监视点：
- 每次 request_id 合法前进时，以 **Gray inc_id** 发布旧槽，并记录 eot_mem[旧槽]；记录此次属于成功传输还是同步丢弃。
- 从发布到最终退休，逐 req 边沿断言该槽 EOT 未变。当前未发布尾槽可变化，不能把它也纳入禁止写断言。
- 有效槽最大数小于 2^ID_WIDTH；发布下一槽前保证环未满，且一次前进仅改变一个 Gray 位。
- src/dest 消费者只可读取对应已发布槽；请求 FIFO 的末 burst 长度必须与该槽的最后一次元数据一致。
- 在数据末拍、EOT 响应与尾 ID 同边沿变化时，使用非阻塞赋值的边沿前值对账，防止 bench 本身错一拍。
- EOT 响应正确不等于数据正确：分别记录真实数据末拍、描述符完成、被 sync 丢弃三类事件。
- abort 完成后，重启前 ID 需收敛、请求/响应/数据 FIFO 空、同步请求及返回为 0；重启首次数据使用新代号，不能通过旧负载恰巧相同。
- 对独立复位只允许预先定义的合法策略。若任一时钟域复位后需要全链路 reset，测试应证明拒绝继续/完成全链路恢复，不应强求丢失状态的端点自行猜回历史。

即使以上数字仿真通过，还需实际路径的 bundled-data max-delay、bus-skew、同步器属性与最短可见窗口核查。原报告写有 Max Delay Datapath Only 不是约束数值、覆盖范围和 margin 已经证明的替代物。不能简单对每个 EOT 增加 2FF：独立延迟会破坏它与 ID/末 burst 长度的对应关系。

## divider 与本结论的边界

util_clkdiv/util_clkdiv.v:53–69 使用两个 BUFR，91–95 用 BUFGMUX_CTRL 选择。CDC-13 的 select 路径仍单独开放；本次 review 没有执行动态切换仿真或证明软件切换过程。固定时钟下的 FIFO/abort 测试不能验收动态选钟。必须从控制寄存器至 mux 的具体运行流程证明 DMA/接口已静止且适用复位先后关系满足后，才能讨论对应豁免或修正。

## 复核源文件摘要

| 相对源文件 | SHA256 |
|---|---|
| axi_dmac/request_arb.v | 9d61f5cef904d43f921999790a7b70ecf0ebf61df51c699d8a755ac190653c74 |
| axi_dmac/request_generator.v | 322b5a6eeef39386d71ceae3fab1f212b523f79f931f48c3acf477d2500483e7 |
| axi_dmac/inc_id.h | 9127b31e998fcb2cc98c73e56f786ad5ea1816291236d8328151bab72c79f5e1 |
| util_axis_fifo/util_axis_fifo.v | 47d6c549f9eac91f90e62f64e55e0b33f2edfff22cfa53a0f23fba29d6e00621 |
| util_cdc/sync_bits.v | 3b63c254ce8e4d719ca8aec8dde48f2b73d59b41ec0529f7da3d9a8b7607061d |

## 独立注册候选的执行结果与未解决起流疑点

执行器为 [p33_sync_candidate.py](../../experiments/p33_sync_candidate.py)。以已通过的 [原版 abort/reset 记录](../../results/p33-abort-reset-20261020t113240z/report.json)中的 21 个输入 SHA 为固定基线，先取输入快照，再在每个独立沙箱编译。每组原版/候选使用完全相同的 bench 字节。候选只改三处：wire sync_id 改为初值 0 的 reg；req_aclk 上 reset0 并注册原比较式；do_enable 判据加入 ~sync_id。未改 status 返回、EOT、同步器、时钟选择或 CDC 约束。

可整合文件（只能先整合到新的候选副本）：
- [精确差异](../../results/p33-sync-candidate-20261020t114404z/request_arb.patch)，SHA256 c7ef72781c628473a3ebefed2181f6b6504326ebe651a9f724e5c54afc8f0c93。
- [完整候选 request_arb.v](../../results/p33-sync-candidate-20261020t114404z/request_arb.candidate.v)，SHA256 46171f056205987c1d207fe410a99cf2c68321bfcd0de79bd757a3efc1e4ebd5。
- [本次实际执行脚本副本](../../results/p33-sync-candidate-20261020t114404z/executed-runner.py)，SHA256 2714f25122912d693779c1521a0abe71b9ff8d197e93ca4301cdb075bb98caae。

保留全部中间失败：

| 记录 | 结果和解释 |
|---|---|
| [首次比较](../../results/p33-sync-candidate-20261020t113545z/report.json) | sample 半周期16.3ns时两版通过；3.7ns时两版在完全相同的777.731ns触发 normal TX consumer underflow，尚未进入 abort。此更快采样场景未验收，不能称候选引入故障或已解决。 |
| [第二次比较](../../results/p33-sync-candidate-20261020t113745z/report.json) | sample 半周期27.1ns时，原版在 RX abort 后新 epoch 首次送数触发 overflow；候选完整通过。整体状态严格 failed，不能以候选相位改变后的通过宣称根治。 |
| [诊断重放](../../results/p33-sync-trace-20261020t114025z/report.json) | 同一输入追加本地打印，原版在同一247.423731us再次失败，候选通过；证明差异可重放。只打印上下文，不是新增物理 CDC 证明。 |
| [起流保护夹具首次编译](../../results/p33-sync-candidate-20261020t114243z/report.json) | 新计数器声明放在使用之后，被 Vivado2021 拒绝。属于本次独立夹具错误，未执行功能仿真；保留失败后把声明移至使用前。无供应 RTL 改动。 |
| [限定起流后的四次比较](../../results/p33-sync-candidate-20261020t114404z/report.json) | req 半周期5ns，sample 半周期16.3ns及27.1ns，两版各一次、两方向均通过。包括3轮32描述符正常传输、未完成描述符 abort、带新负载标签重启、协调全域复位且采样时钟延后释放，以及完全相同的新增局部断言。 |

新增局部断言为：do_enable 不得与本地同步请求或任一返回确认同时为1；前一个 req 边沿 do_enable 为0时，本次看到的 request_id 必须保持。它们在 req 时钟 active edge、非阻塞赋值更新之前取样，避免把合法尾 ID 最后一拍前进错误判为关停后前进。它们未覆盖所有 CDC 或模拟亚稳态。

最终16.3ns组 bench SHA为 ef5188ad7721cb0ca8e8dfc37004f2490ea446bd405924d2e9e959c8e4661c76；27.1ns组为 d126beae294d47602131f403cd60e5f51db70503de3eadaa121d1f4ace3d78ae。每组的 baseline/candidate 两文件 SHA一致。最终全部原始输入 SHA仍与固定基线相同。

### XFER_REQ 的实际来源与保守起流策略的边界

bench 的 wr_request 直接接 dmac_request_arb.fifo_wr_xfer_req。request_arb.v:782 接到 src_fifo_inf.xfer_req；src_fifo_inf.v:117 又接 data_mover.xfer_req；data_mover.v:88 最终等于 active。IP端口映射 axi_dmac_ip.tcl:146–150 也将该引脚标为 FIFO_WR.XFER_REQ。**它在本版 RTL 中不是逐拍 READY 信号。** data_mover.v:94 的真正 s_axi_ready 还需要 m_axi_ready、pending_burst 与 active；src_fifo_inf.v:94–97 在 en 已到而 ready 为0时设置 overflow。

诊断原文显示，原版 RX epoch3 的首个 wr_en 在247.397us附近到达时，wr_request=1、src_enable/src_enabled=1、src_ready=1，但src_valid=0、src_response_id=4、同步 tail=1。结合上述逻辑，疑点位于“已激活”与 pending/ID 可用的起流窗口；尚未逐拍完整证明其根因及外部接口期望。候选改变 resync 结束相位可能避开该窗口，因此候选通过不是修复此问题的证据。

为隔离 sync_id 候选的回归，最终独立夹具仅对 RX 外部发送增加一项实验条件：观察实际 wr_request 连续为高的3个 sample 上升沿后才允许首拍，维持原有每4周期一拍。它跟随接口请求的实际上升/下降，reset、enable撤销或请求降为0都清计数；没有关闭 overflow 断言，也没有改已失败的原夹具。该条件给固定的两种时钟比下 ID 同步与 pending 寄存留下建立窗口，但**3周期不是已确认的厂商接口保证，不能推广为产品延时，也不能据此关闭“XFER_REQ有效却溢出”的疑点**。当前证据只能证明在这个明确缩小的激励范围内，两版本均完成同步/关停回归。

后续应先定义原 FIFO 接口契约，逐拍核对 descriptor-valid、尾 ID 发布/同步、pending_burst、active、ready 与外部 EN 的最早关系，并检查实际 ADC packer 是否使用/忽略 XFER_REQ。若期望从 XFER_REQ 拉高后的下一拍就能无损送数，应修正请求资格或增加有真实握手依据的入口缓冲，并复测原即时起流失败；若接口允许未准备数据被丢弃，应在采集边界明确丢弃/有效样本标记，而不能宣称完整连续采集。同步注册候选与这个功能问题必须分别验收。

本轮状态：候选已有明确差异和受限数字回归；起流契约疑点仍开放。未新增豁免，未关闭58条CDC，未宣称修复板端故障。

