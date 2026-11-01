# 旧P201独立UART候选实现

日期：2026-10-24（北京时间）。用户在资料核对后要求继续，本轮推进独立UART候选工程，不启动RF、不访问串口或板卡。主项目最后实板状态仍为P51。

## 实现范围

- 原厂138个HDL输入复制到独立短路径 `E:/FPGA_Tools/Work/uart-20261024T023801Z/hdl`，原文件及现用镜像不覆盖。
- UART0设为EMIO，顶层新增ext_uart_tx/ext_uart_rx，候选约束E17/E18、LVCMOS33，对应已查图纸J19第5/6脚。UART1保持MIO12..13调试功能。
- 离线设备树启用e0000000 UART0。原厂DTB实际节点在/amba，但serial0别名和stdout-path指向不存在的旧路径；候选仅纠正串口相关路径，固定serial0→UART1、serial1→UART0、stdout仍为UART1/115200n8。全树规范化比较确认其余设备属性不变；其他历史符号路径警告保留，未顺带修改。
- UART0新增后的Linux编号仍须实板确认；工具拒绝ttyPS0，要求非控制台串口的sysfs物理控制器为e0000000，不能凭设备名称猜。

## 电脑端工具与测试

`embedded/p201_uart/uart_loopback.c` 是有界115200/8N1双向回环工具，默认1024字节、2秒超时，覆盖NUL/CR/LF/XON/XOFF/FF；保存/恢复termios，校验完整字节，超时、错误和中断均失败退出。必须显式--run-loopback，不自动选择/探测串口。正式ARM编译不含PTY测试旁路，也不接受相应参数。

`results/p201-uart-tool-20261024T024115Z/report.json`：7项Linux PTY测试、2项正式版本拒绝测试通过，Cortex-A9 hard-float ELF32交叉编译/运行库版本检查通过。PTY验证模拟终端和程序边界，不证明物理电平、波特率精度、板上字节或屏幕协议正确。

## 失败与修正（证据保留）

1. 首轮 `results/p201-uart-candidate-20261024T023801Z/report.json`：DTB编译/回读、10项输入保护测试和6个原厂IP封装通过。随后BD检查脚本使用NAME完整路径过滤，错误地报告UART disconnected。
2. `results/p201-uart-validated-20261024T024349Z/report.json`：改为比较端口与PS管脚各自连接的实际网络，日志确认TX/RX网络完全相同，UART0/EMIO与UART1控制台保持检查通过。保留原查询返回空的证据。顶层直接RTL elaboration因原厂IP OOC模块未建立而失败，不能将该阶段写成顶层已通过。
3. 完整综合/布线继续记录在 `results/p201-uart-route-20261024T024517Z/report.json`。本文件更新时尚在运行，最终结论必须读取该报告和后续验收补充，不根据进程启动或BD通过宣称可部署。

## 部署前的必经关口

完整综合/布局布线、时序/CDC/约束与现用RF功能一致性审核；核对UART0时钟/复位和Linux驱动是否已能完成必要初始化，结合生成的PS初始化与现用启动链决定是否需重建FSBL，不预设必须重刷BOOT。准备相互匹配、可恢复的启动候选；先在无外设连接条件下核对UART与控制台，再接经过实物针号/电平/GND确认的回环线。当前没有新BOOT、没有板端测试，不提供热加载操作。

J19图中1/3是5V、2/4是3.3V，不能当GND；接地位置和实物版本仍待确认。未确认对方设备完整型号/逻辑电平，不接屏或另一开发板。串口功能是本次独立分支，不将其替代比赛主线的真实AI与最终十分钟整机验收。

## 完整布线复核

完整综合与route_design已完成，未执行write_bitstream。Vivado IO报告确认ext_uart_tx→E17、ext_uart_rx→E18，均LVCMOS33/Bank35。受约束路径WNS=+1.160777ns、WHS=+0.015740ns，TNS/THS=0；no_clock与unconstrained_internal_endpoints均0。不能将这组正裕量扩展成全部外部接口时序已验收。

独立复核 `results/p201-uart-review-20261024T025745Z/report.json`：16个输入、20个输出缺少外部延迟定义，涉及RF数据/帧与控制/I2C/SPI；CDC汇总为12个unsafe、55个unknown端点，报告跨越rx_clk与clk_fpga_0。它们是待逐项审核的工具告警，不自动判作已证实硬件故障，也不以加false-path掩盖。未将整机发布门禁判为通过。DRC的36项均为DSP使用方面Advisory，没有据此代替CDC/接口验收。

准备脚本现已按本次教训分为BD/DTB准备与完整综合布线两步，不再直接用缺少OOC模块的顶层RTL elaboration作为必经门禁；本次两个失败目录及执行Tcl保留，后续复现按embedded/p201_uart/README.md。

## 本轮结束状态

完整构建状态：`completed_full_offline_routing_requires_timing_and_board_acceptance`；主报告：`results/p201-uart-route-20261024T024517Z/report.json`。时序运行统计：`{"STATS.WNS": "1.160777", "STATS.WHS": "0.015740", "STATS.TNS": "0.000000", "STATS.THS": "0.000000", "STATUS": "route_design Complete!"}`。完成布线不等于全部时序/CDC和接口验收通过；本轮不批准部署，不生成/写入新的启动镜像。10项候选输入保护、7项PTY、2项正式程序拒绝测试通过，ARM工具已构建。原厂138个输入最终SHA核对未变。

串口分支检查点：`results/p201-uart-checkpoint-20261024T025820Z/report.json`，ZIP逐文件SHA/CRC核验。主线P51硬件验收和比赛任务顺序不替换，本轮没有读取或改变板卡当前状态。继续先读本记录、`results/p201-uart-active.json`及完整报告，不把“候选已实现”解释成“针脚现在能用”。
