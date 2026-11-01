# P35：TX busy返回的CDC-12布线网表扇入复核

日期：2026-10-21 凌晨（北京时间）。只读打开旧 `E:/p30c-1019-174235/merged-route.dcp`；没有打开正在构建的新TTL工程，没有保存工程/DCP，没有改RTL、约束、板卡或串口。未增加false path、clock group或CDC豁免。

## 结论

**此前“是否有未同步req域读指针混入busy OR”的疑点，已由实际布线网表排除。** 该锥体的三个源寄存器全部由同一个物理BUFGCTRL输出驱动。Vivado在同一C脚同时传播两个备选分频时钟名，并针对两个模式各报告一条CDC-12；不是发现了两个独立物理时钟同时进入三个源寄存器。

这解释了这两条告警的multi-clock来源，**不等于完整CDC验收或将58条告警关闭**。busy组合逻辑在多个源寄存器同时变化时的毛刺安全、停止/响应退休握手，以及动态切换时钟的复位/静止条件仍需相应证据。不能因报告名称不准确而凭空豁免，也不应仅为清掉两行报告修改RTL。

## 执行与证据

- [执行器](../../experiments/p35_cdc12_cone.py)；输出Tcl只包含open_checkpoint、查询、报告与导出约束到新文件，没有应用新约束。
- [最终原始报告](../../results/p35-cdc12-cone-20261020t161530z/report.json)，Vivado真实退出0；7个受保护输入的前后SHA相同。
- [完整扇入/寄存器/原语属性](../../results/p35-cdc12-cone-20261020t161530z/cone.txt)
- [解析与逐项检查摘要](../../results/p35-cdc12-cone-20261020t161530z/summary.json)
- [重新运行的限定CDC报告](../../results/p35-cdc12-cone-20261020t161530z/status-cdc.rpt)，CDC-12仍为2。
- [时钟关系](../../results/p35-cdc12-cone-20261020t161530z/clocks.rpt)、[时钟交互](../../results/p35-cdc12-cone-20261020t161530z/clock-interaction.rpt)、[原DCP导出XDC](../../results/p35-cdc12-cone-20261020t161530z/checkpoint-export.xdc)。导出文件是取证，不是新的部署约束。

第一轮 `p35-cdc12-cone-20261020T161319Z` 同样成功，已经取得三个起点和读指针同步链；但其原语筛选只查BUFGMUX_CTRL，漏掉综合变换后的BUFGCTRL。第二轮补查BUFGCTRL、C网络的实际叶驱动和LUT真值，保留首轮结果，没有用缺失项假称完整证据。

DCP SHA256：`032538c72821b992b9a7029d9a5abff7294b59bac4c7d9b46e74ec48e867756b`。这是P30旧布线基线，**本结论不能自动替代新TTL33候选的重新CDC复核**。

## 精确物理扇入

公共前缀：`i_system_wrapper/axi_ad9361_dac_dma/inst/i_request_arb/`。

目标为 `i_sync_status_dest/cdc_sync_stage1_reg[1]/D`，目标寄存器C脚只具有 `clk_fpga_0`，10ns。

`all_fanin -flat -startpoints_only`恰好返回三个FDRE起点。Vivado把顺序起点表示为C脚；下表给出对应寄存器：

| 相对寄存器 | C脚时钟名 | 物理C网络叶驱动 |
|---|---|---|
| `i_dest_dma_fifo/i_response_generator/enabled_reg` | `clk_div_sel_0_s clk_div_sel_1_s` | `i_system_wrapper/util_ad9361_divclk/inst/i_div_clk_gbuf/O` |
| `i_dest_response_fifo/i_raddr_sync/cdc_sync_stage2_reg[0]` | 同上 | 同上 |
| `i_dest_response_fifo/s_axis_waddr_reg` | 同上 | 同上 |

证据见 `cone.txt` 第1275、2548、3821行的STARTPOINT记录及紧接的 `CLOCK_NET_LEAF_DRIVER`；最终行号可由相应标记定位。

汇合单元是一个LUT3，虽然优化后名称位于 `i_raddr_sync` 层次，不能凭层次名误认它仍是首级同步器。三个输入对应I0=enabled、I1=已经同步的raddr、I2=waddr；INIT=`8'hBE`。8种输入组合逐一核对，恰好是：

```
busy = enabled | (synchronized_raddr ^ waddr)
```

它与源RTL的 `dest_enabled | ~dest_response_empty` 一致，因为单深度响应FIFO的empty是读写toggle相等。没有在综合时把raw req-domain raddr旁路进来。

## 读指针两级链没有被旁路

原始req域 `i_dest_response_fifo/m_axis_raddr_reg` 的时钟是 `clk_fpga_0`。

网表实际连接为：

```
req域 m_axis_raddr_reg
  -> sample域 i_raddr_sync/cdc_sync_stage1_reg[0]
  -> sample域 i_raddr_sync/cdc_sync_stage2_reg[0]
  -> busy LUT3
  -> req域 i_sync_status_dest/cdc_sync_stage1_reg[1]
  -> 原返回同步器stage2
```

raddr同步器两级都是FDRE、ASYNC_REG=1，C脚均是同一物理sample mux输出，放置在同一个 `SLICE_X35Y288`。stage2的D网络直接由stage1/Q驱动；stage1的D顺序起点是req域m_axis_raddr。完整属性及D_STARTPOINT已归档。当前取证证明拓扑存在；没有据此计算MTBF或签署任何模拟亚稳态概率。

## 同一个MUX的两种时钟模式

实际单元是 `BUFGCTRL`，位置 `BUFGCTRL_X0Y18`，来自源RTL的BUFGMUX_CTRL宏：

- I0来自 `clk_divide_sel_0/O`，时钟 `clk_div_sel_0_s`，主时钟rx_clk，除4、周期16ns。
- I1来自 `clk_divide_sel_1/O`，时钟 `clk_div_sel_1_s`，同一个rx_clk，除2、周期8ns。
- O携带两个时钟对象，驱动上述三个源寄存器的C脚。
- S0和S1来自同一clk_sel网络，`IS_S0_INVERTED=1`，S1不反相；CE0/CE1接常量1，IGNORE0/IGNORE1接常量0，PRESELECT_I0=1、PRESELECT_I1=0。固定选择下是互斥的单一物理输出，不是三个源寄存器分别采用不同clock net。
- 旧DCP本来已有 `set_clock_groups -logically_exclusive -group clk_div_sel_0_s -group clk_div_sel_1_s`，来自供应util_clkdiv约束。导出XDC第2218行可见；新报告两方向都显示Exclusive Groups。本轮没有新增该规则。

上述时钟周期为旧DCP声明的rx_clk=4ns下的静态分析值，不是本次实测采样DATA_CLK。

MUX选择逻辑的顺序起点包括 `i_tx/i_up_dac_common/i_xfer_cntrl/d_data_cntrl_int_reg[17]` 和 `i_rx/i_up_adc_common/i_xfer_cntrl/d_data_cntrl_int_reg[2]`。现有约束还把选择脚设为false path；**这不是动态切换安全证明**。CDC-13、软件切换时的DMA停止/复位次序和运行模式验证继续开放。

## 最小后续动作

1. 新TTL33工程综合/布线后重取相同目标扇入，确认优化结果及源时钟集合没有改变；不能把本DCP的结果直接贴到新构建。
2. 固定clock选择做busy握手回归：本地enabled清除、最后EOT响应写入、req侧消费、raddr同步回传的交叠必须覆盖；全局重新enable前busy确实归零，不能靠本地enabled单独判断。
3. 若要增加busy源端寄存，作为独立候选验证其增加一周期是否产生假空/早重启窗口，并重新构建；本取证未证明需要此RTL改动。
4. 动态选钟保持单独任务。若当前产品只承诺固定RF配置，可限定该运行范围进行下一阶段工程试验，但必须记录不支持在活动DMA期间切换。

本次可关闭的仅是“缺少routed cone，不知道是否有raw req指针直入OR”的资料缺口；不关闭整体CDC、并行功能或硬件稳定性验收。
