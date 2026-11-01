# P36 合并初始化之后的只读复核

`experiments/p36_display_readback.py` 只供已经成功出现三 RF 名称及 `/dev/fb0` 的合并启动使用。操作员必须传入刚读取的 `--expected-boot`；工具固定 COM8，校验新板身份、boot、taint0、三 RF 名称、fb0 字符设备。门槛不成立即停止，不尝试部署、切模式、重启或修复。不得与其他串口工具并发使用。

每轮建立新的 `results/p36-display-readback-UTC/`，保存每条命令与原始输出、原始 UART 接收字节、已脱敏发送字节及报告。板端每条命令不超过 72 字符。可选节点读失败时保存原始错误并继续其他安全读取；串口失去应答则停止。工具没有寄存器、sysfs、固件、overlay 或 framebuffer 写入。

复核范围：clock summary 的 rate/enable/prepare/父子关系、framebuffer 的 mode/modes、virtual_size、bpp、stride、PWM debug 的 TTC 通道 2/通道 0/1、背光 brightness/actual_brightness、clocksource、前后 uptime/interrupts、相关设备绑定及内核日志。虚拟尺寸 `800,960` 是可容纳两页的存储几何，不能当作可见 `800,480` 失败。系统已有 `fbset` 时使用只读 `-s` 查询；缺少该工具时留待后续 ioctl 实测，不能凭虚拟尺寸宣布可见模式通过。

只有唯一设备绑定 `clk-wizard`、compatible 为 `xlnx,clocking-wizard`、资源覆盖 `0x43c10000`、fabric operating、FCLK0/FCLK1/该设备内部时钟/clk_out1 均启用且 prepare 正数、clk_out1 位于该 Wizard 子树时，才尝试现有 `devmem` 的两参数读取：`0x43c10004` 状态、`0x43c10200` M/D、`0x43c10208` 输出 0 的 O。缺工具或门槛不足明确 skip，不写寄存器，不主动开时钟。偏移和千分数解释已经核对并在报告中记录供应 `drivers/clk/clk-xlnx-clock-wizard.c` 的本地留档哈希；不声称供应源码就是运行内核的精确重现。

报告只写 `read_only_evidence_collected`，各 check 单独给结果。33 MHz 的软件 rate 与 M/D/O 推算相符、LOCK=1、framebuffer 存在，都不能替代外部 PCLK/背光波形测量或屏幕目视确认；也不能证明 RF 与显示并行的性能、连续采样或信号质量。所有实际硬件实验仍由主操作员执行。本脚本交付阶段只进行主机离线测试，没有打开串口。
