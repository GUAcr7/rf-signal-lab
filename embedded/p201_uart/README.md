# P201 UART候选与有界回环工具

此目录仅有测试工具；不是已验收的板端串口功能。硬件候选与实验结论见 `docs/experiments/EXP-P201-UART-CANDIDATE-20261024.md`。

候选分配：PS UART0→EMIO→J19第5脚E17(TX)、第6脚E18(RX)，LVCMOS33。现有PS UART1/MIO12..13作为控制台保留。须核对PL、PS初始化/驱动及DTB的配合，不能凭一个位流判断已可用，也不能热改运行中的RF工程。是否需重建FSBL由初始化差异与Linux驱动证据决定，不预设必须重刷BOOT。

## 测试工具

- `uart_loopback.c`：115200/8N1，默认1024字节、2000ms总超时；字节模式包含0..255，不是人类可读文本。
- 正式编译只接受/dev/ttyPS1..3，并解析sysfs device到UART0 e0000000；拒绝ttyPS0及PTY测试开关。若实际内核设备目录命名不同，先读取/核对身份再有依据地修改，不绕过检查。
- 不打开任何默认端口；必须给出设备及`--run-loopback`。恢复原termios后关闭，不改Linux启动、射频属性或GPIO。
- 退出码：0完整一致；2参数/身份被拒；3系统/termios失败；4超时或不完整；5收到字节不一致；130中断。
- 接收失联、错字节和中断不能记通过；输出JSON中的sent/received不是射频采样数。

仅在已验收候选启动、实物针号与电压确认后，同板TX↔RX短接或对端运行已知回显程序，再执行有界回环。**不要直接接串口屏运行此工具**：任意字节测试不是屏幕协议。接屏应另写对应厂商命令及握手。

同板TX/RX回环共享板内地，不需要另外跨接地线；外接另一块板/屏幕时需单独确认公共GND。J19前四脚均是电源，不能当GND。

## 电脑端复现

1. 项目虚拟环境运行 `python experiments/p201_build_uart_tool.py`，自动在WSL执行PTY测试与ARM交叉编译，结果保存到新的results目录，不访问板卡。
2. 候选工程准备运行 `python experiments/p201_prepare_uart_candidate.py`，只在E盘独立目录构建。
3. 准备报告的BD检查通过后，运行 `python experiments/p201_route_uart_candidate.py --validation 新候选report.json` 做完整综合与布线；不直接对缺少OOC IP的工程运行RTL elaboration。`p201_validate_uart_project.py`仅保留本次失败排查历史，不是后续必经步骤。所有原始失败记录保留，不覆盖为成功。

当前范围不包括外接设备型号确认、物理GND定位、目标板端收发或屏幕显示验收。
