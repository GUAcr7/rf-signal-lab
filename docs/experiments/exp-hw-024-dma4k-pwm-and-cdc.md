# HW-024：4KiB DMA实测、背光计时器纠错与实际端点仿真

日期：2026-10-20，北京时间。本轮由用户重新接线通电后继续。所有`results/`均是文件系统证据，Git不会自动包含它们。

## 本轮结论

1. **4KiB DMA资源的当前内核探测门槛已通过，RX有限采集通过。** 原厂RF位流和原时钟保持配对，只将两个DMA资源长度64KiB改为4KiB；两驱动绑定，三个RF IIO设备齐全、tainted=0，完成16缓冲接收及65536字节稀疏诊断回收。TX DMA仅验证了探测/绑定，没有发射或TX传输验收。合并工程的100MHz DMA时钟尚未上板验证。
2. **发现并修正了背光的逻辑通道冲突，尚未硬件验收。** 原配置使用TTC0通道0；系统已经将该通道注册为`ttc_clocksource`，通道1用于`ttc_clockevent`。新副本把背光连线和设备树一起改为通道2，BD连接校验与设备树PC应用通过。新副本未综合/布线/生成位流。
3. **VDMA时钟名称已在新候选中纠正。** 五路时钟名称不再重复，时钟提供者仍为原先FCLK1/200MHz。供应源码中旧驱动容忍缺少可选时钟，此项属于契约纠错，不能宣称已重现并修复显示故障。
4. 实际RX FIFO→MM和TX MM→FIFO端点的数字仿真通过：各64描述符、2216数据拍、64 EOT，两方向合计128描述符/4432数据拍。包括ID回绕、RX内存端回压、排空停止后重新启用。**未覆盖中途abort、独立复位、模拟亚稳态或真实DDR吞吐；58项CDC仍未关闭。**

## 新开机身份与有限接收基线

[首次认板](../../results/p32-preflight-20261020t043038z/report.json)与[上午只接收](../../results/p27-smoke-20261020t043204z/report.json)、[诊断字节回收](../../results/p31-sparse-archive-20261020t043512z/report.json)已保存。后续工作开始时再次认板，发现用户间隔内已重新上电，因而使用[第二次认板](../../results/p32-preflight-20261020t105223z/report.json)的新身份，而没有沿用上午boot_id。

当前最终只读状态见[本轮结束核查](../../results/p32-preflight-20261020t111006z/report.json)：旧板boot=`d11f69a8-cf03-4b3e-b4c5-0afb8d5d7ff9`，新板boot=`5cb0b3a6-c099-4df2-a526-86c41da9921a`。新板原厂RF模式、三个设备齐全、tainted=0，RX1 manual/0dB、LO2450MHz、Fs30.72MS/s、BW18MHz；缓冲和四个scan enable均为0，两板未观察到实验收发进程。

本轮没有启动TX应用。旧板RAM发射工具和波形尚未恢复，后续已知信号实验必须重新上传、校验并使用当前boot_id。板卡保持通电，未执行收工停机。

## 4KiB试验方法、失败与恢复

[候选构建](../../results/p32-dma-trial-build-20261020t105152z/report.json)从哈希核验的原厂RF DTBO反编译，逐属性比较确认**仅两处reg长度变化**；没有改时钟、AD9361属性，也未添加firmware-name。

使用[一次性启动保持模板](../../board/boot/p32-once-hold.sh.in)，实际新启动时先校验并恢复原保护版S99board、sync，开风扇后保留一个尚未绑定RF驱动的系统。模板不自动加载PL或overlay，不卸载任何驱动。[三项主机测试](../../results/p32-hold-checks-20261020t105246z/pytest.stdout)覆盖新启动恢复、同boot拒绝及备份损坏拒绝。最初测试夹具把`/proc/sys/`路径重复改写而失败，已纠正；它未操作板卡。

[首次上板记录](../../results/p32-dma4k-runtime-20261020t105431z/report.json)确认了保护脚本恢复、空overlay/无RF绑定，随后加载原厂RF位流。脚本的设备枚举循环覆盖了临时变量`d`，下一条mkdir指向错误sysfs目录并失败；**候选尚未应用，没有发生热卸载或内核异常**。实际执行源码副本与失败原文保留在该目录。修正入口改用专有`ov`变量。

[限定阶段恢复](../../results/p32-dma4k-resume-20261020t105719z/report.json)只接受该明确的“应用前路径变量失败”，再次核验boot、保护脚本、空overlay、无RF绑定、原厂PL operating及候选SHA后，单次应用候选。未重新加载PL，未移除overlay。实际资源为`7c400000-7c400fff`和`7c420000-7c420fff`，RF三个设备齐全、tainted=0。

本次[RX16缓冲](../../results/p27-smoke-20261020t105730z/report.json)与[65536字节回传](../../results/p31-sparse-archive-20261020t105740z/report.json)通过。仍只保留每块1024/65536帧，即1.5625%，不作无丢样连续IQ或真实AI输入验收。随后普通reboot，原厂64KiB资源与保护脚本已恢复；[最终RX配置](../../results/p26-rx-profile-restore-20261020t105838z/report.json)读回通过。总计两次普通重启，无热卸载，无BOOT.BIN、基础DTB或原厂固件替换。

## TTC背光问题与最小修正

[实时资源采集](../../results/p32-live-contract-20261020t043525z/report.json)显示当前clocksource为`arm_global_timer`，可选项包含`ttc_clocksource`；启动中注册了TTC clockevent。当前没有PWM设备。`/proc/iomem`未列出TTC不能证明空闲：供应计时器代码使用`of_iomap`，没有通过资源申请来排斥PWM驱动。

[供应源码归档](../../results/p32-driver-contract-20261020t043240z/report.json)：`cadence_ttc_timer.c`第499、529、533行分别映射首个TTC块、以base注册clocksource、以base+4注册clockevent。`pwm-cadence.c`第97行按`4*(3*reg+pwm)`选寄存器，第133行使用所请求的hwpwm。原背光`pwms`通道0确实会写系统已注册的TTC0通道0；当前主clocksource是ARM全局计时器，因此不声称现有机器已经因此死机或必然影响通道1。

最小修正是把背光改用同组未由计时器初始化的通道2，**同时**将PL的外部背光引脚从TTC0_WAVE0_OUT改接TTC0_WAVE2_OUT。不能仅改设备树通道，也不能在系统启动后用overlay禁用timer节点就认为释放了早期计时器。

[新工程与BD验证](../../results/p32-pwm2-project-20261020t105934z/report.json)：`E:\p32-pwm2-105934\project\combined.xpr`。它是未综合的新副本；P30工程XPR、BD和已布线DCP的前后SHA相同。原基线仍在`E:\p30c-1019-174235`。

[配套候选](../../results/p32-paired-overlay-20261020t110125z/report.json)为[rf-display-p32-pwm2.dts](../../fpga/integration/rf-display-p32-pwm2.dts)，已编译并由原生libfdt在电脑应用。保留89项AD9361配置，修正VDMA五个时钟名称、选择PWM2并使用独立firmware-name=`rf-display-p32.bin`。**这个位流尚未生成，候选未部署。**

后续限制：供应PWM驱动仍暴露三个通道，不得导出/配置通道0、1；其remove还会关闭全部三个通道，因而继续禁止热卸载PWM驱动或含PWM的overlay。新硬件上必须验证背光、亮度与系统计时稳定，才能把此问题验收关闭。

## 最终CDC清单与端点仿真

[最终58项清单](../../results/p32-final-cdc-20261020t105847z/report.json)直接取P30最终布线报告，而非旧P29的59项RF单工程报告。58条按source/destination去重为30对，部分相同端点出现在两种分频时钟模式下；这不等同于58个独立硬件故障。

| 类别 | 条数 | 下一项关键核验 |
|---|---:|---|
| EOT元数据寿命与握手 | 46 | ID槽复用前全部消费者已结束、元数据建立时间与物理约束 |
| 组合sync_id送入同步器 | 4 | abort/resync时比较逻辑毛刺及安全握手；不可盲插寄存器 |
| FIFO数据保持与采样 | 4 | 指针可见之前数据已稳定，复位和终止后无旧数据 |
| 时钟mux选择 | 2 | 分频切换条件、停止与复位顺序及BUFGMUX_CTRL语义 |
| enabled/empty跨域汇合 | 2 | 排空确认不会早于在途数据完成 |

[实际端点仿真](../../results/p32-fifo-mm-20261020t110537z/report.json)使用未修改的ADI RTL、与实际XCI一致的端点类型/64位宽/128字节burst/FIFO_SIZE=4/异步参数/TX目的寄存切片。有限FIFO速率下，两方向数据、地址、WSTRB/WLAST、EOT、ID回绕、排空后重新enable通过。首次编译因bench变量声明顺序被2021.1拒绝，失败及当时源码保留在`p32-fifo-mm-20261020T110457Z`，未修改供应RTL。

这比P31的AXIS/AXIS仿真覆盖更接近实际配置，但没有中途abort、独立复位、真实总线仲裁和模拟亚稳态证据。未增加CDC豁免，未改ADI同步器或时钟mux，未将58项标为解决。

## 下一步顺序

1. 对实际端点补中途abort/重启与独立复位测试，逐组审查上述CDC，不凭工具条数或有限仿真清零告警。
2. 核对已有面板/载板资料，补外部IO时序依据；精确裸屏型号仍待现有资料交叉确认，暂不要求用户重复提供资料。
3. 对PWM2候选重新综合、布线，复核时序、资源、GPIO和设备树一致性。原P30结果不能直接继承为新工程通过。
4. 继续采用新启动单次加载和正常重启恢复的办法，验证合并RF/屏幕/触摸/背光/计时及并行运行；绝不热卸载原厂RF overlay。
5. 恢复旧板经校验的RAM发射工具与限幅波形，做已知信号的幅度、频率、解调指标验证，再推进完整连续IQ与真实数据AI。

旧内核热卸载的生命周期缺陷和冷启动间歇0xFF仍未根治。本轮新启动验证解决了一项兼容门槛，并提供继续集成的安全路径；不能把规避措施称为内核修复。

## 交付前复核与保存

[240项证据/结构复核](../../results/p32-delivery-check-20261020t111312z/report.json)通过，包含当前板卡身份与空闲状态、4KiB接收记录/字节SHA、原P30三个关键文件未变、配套新BD与设备树、ADI源码未变，以及仿真参数对实际XCI的核对。这是证据与结构核对数量，不是新增240项硬件功能测试。

重存BD时Vivado展开了307项原先隐含的PS7参数；逐项与原XCI比对一致，其他信号/接口/地址网络保持一致，仅背光网络改为WAVE2。BD校验仍保留未使用M04地址路径、SPI SSIN提示及部分传播元数据告警；未将BD通过说成所有告警解决。

交付审查又将一次性hold模板的恢复临时文件改成隐藏文件，避免中断遗留的`S*`文件在下次启动时被自动执行。[四项主机复测](../../results/p32-hold-checks-20261020t110933z/pytest.stdout)通过，新增rename失败场景。板端原保护脚本早已恢复，本次没有重新安装这个更新模板；硬件成功试验使用的实际旧模板在运行证据中保留，不混淆版本。

最新入口为START-HERE与RESUME-20261020，机器状态为p32_current。两板保持通电空闲，没有新增发射或合并固件加载。
