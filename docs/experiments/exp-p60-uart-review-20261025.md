# P60：旧板独立UART候选的详细CDC复核

日期：2026-10-25。对应新流程W1准备；仅电脑端读取既有冻结设计检查点，未接屏、未访问板卡、未修改约束/RTL、未生成或部署新位流。

## 从摘要告警到具体端点

前次只有CDC摘要：12个unsafe、55个unknown。本轮使用Vivado2021.1读取`results/p201-uart-route-20261024T024517Z/uart-routed.dcp`，确认SHA与原报告一致，提取`report_cdc -details`、check_timing、clocks和UART管脚属性。

详细报告：`results/p60-uart-detail-20261025T025319Z/report.json`，工具成功完成，源DCP读后哈希未变。UART仍为E17/TX、E18/RX、LVCMOS33。

逐行提取到55条CDC-1 Critical和12条CDC-13 Critical，共67条。65条目的端点位于axi_ad9361_adc_dma，2条位于axi_ad9361_dac_dma，没有UART命名的关键告警端点。

## 与历史基线比较

比较对象是`results/p06-cdc-audit-20261015-200505/reports/cdc.rpt`，按规则ID、起点管脚和终点管脚构造多重集合，保留重复次数，不仅比较数量。

结果：67条关键告警端点集合与历史基线完全相同，新增0、移除0。依据：`results/p60-uart-comparison-20261025T025752Z/report.json`。这支持将这批结构告警定位为已有射频DMA结构的延续，不支持把所有告警归因为新增UART。

此比较没有证明CDC安全，也没有比较所有时钟定义、例外约束和布局后的延迟；不能据此将原`deployable=false`改为true。

## 剩余审核方向

原ADI `request_arb.v`中eot_mem_src/eot_mem_dest在req/src时钟写入、由不同域的ID寻址读出；工具报告对应RAM原语与EOT控制路径。下一步需结合FIFO/ID生命周期和握手证明数据在接收域使用期间稳定，并核对相应约束。没有通过增加false-path或随意添加ASYNC_REG来消除告警。

仍有16个输入、20个输出缺少外部延迟定义，涉及RF数据/帧、SPI/I2C等；当前报告没有给出整机接口时序通过结论。UART初始化、是否需要配套FSBL、可回退启动包、实体电平/方向和物理回环仍是独立门槛。

P59本次实板只读看到旧板当前仅有控制台UART1/ttyPS0，未启用候选外设UART。用户已确认触屏到手，完整型号待补充；型号到齐前可继续上述审核及通用控制准备，不接未知电平的屏幕。

本轮工具：`experiments/p60_uart_detail_review.py`、`experiments/p60_compare_uart_cdc.py`。旧候选和138个原厂输入未被本轮改写；原串口分支状态记录保留，P60新报告单独存档。
