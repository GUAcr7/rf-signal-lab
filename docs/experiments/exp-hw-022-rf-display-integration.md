# EXP-HW-022：射频与显示合并候选、时钟纠错及重新上电恢复

日期：2026-10-19。承接 [HW-021](exp-hw-021-vendor-migration-and-reconnect.md)。本轮包含下午离线构建和晚间用户重新上电后的恢复；原始文件保留各自 UTC 时间戳。

**合并工程已完成完整综合与布局布线，尚未生成/加载新位流，不代表射频和屏幕已经同时上板。** 当前仍运行原厂 RF 固件。完整无丢样、真实 AI 与整机显示验收仍未完成。

## 实际完成

| 项目 | 结果与范围 |
|---|---|
| 第三份合并工程 | 精确器件 XC7Z100FFG900-2，单一 PS7；RF、VDMA、VTC、TPG、时钟、触摸、地址与 IRQ 已连接；59 个层级单元的初始框图验证通过 |
| 完整综合与最终资源 | 所有模块解析，无未解析黑盒；最终布线报告：LUT 21,828 / 7.87%，FF 38,469 / 6.93%，BRAM 12.5 / 1.66%，DSP 69 / 3.42%。综合后经实现优化，不能与初次综合资源混用 |
| 保存后的图结构核对 | 87 项通过，包含 EMIO64、UART1 MIO12/13、SPI0/1、HP0/1/2、跨域互连、7 个外设窗口与中断位；不是板上总线事务测试 |
| GPIO 原生仿真 | 352 次映射检查通过，覆盖逐位、方向、RF 输出、触摸及随机输入 |
| VTC 6.2 原生模型仿真 | 实际加密 IP 模型、AXI 读写与读回；800×480 两个完整帧，每帧384000像素、480行、每行800有效像素，1535次行周期检查通过 |
| 最终布线时序 | WNS +0.449 ns、WHS +0.013 ns；TNS 0.000、THS 0.000。仅覆盖已有约束 |
| 总线偏斜与布线 | 43项bus-skew约束均通过，最小余量4.004ns；52551条需布线网络全部完成，routing errors=0 |
| 时钟/内部覆盖 | no_clock=0，unconstrained_internal_endpoints=0 |
| 原厂源保护 | 原始资料与 1235 项源检查通过，11 项约束引用无异常；D盘资料未改 |
| 重新上电 RX | 新 boot_id=`b638a03f-2638-4288-b663-9b8c86e58c7e`，本次 attempt 1 成功；按已验证配置恢复 RX1 manual/0dB、LO2450MHz，Fs30.72MS/s、BW18MHz |
| 新 RX 自检与回收 | 16 DMA缓冲，0.034245817秒，2通道；只保留1.5625%稀疏数据，65536字节，板端/电脑SHA一致；缓冲释放。不是完整数据或已知信号/AI验收 |
| 旧板恢复 | boot_id=`6d5cb873-e976-4c91-9d37-3227445de891`；RAM包8项校验、9份波形文件检查、只读inspect通过，无发射、无RF配置写入 |

VTC 仿真采用加速像素时钟，配置完成/跨域稳定后门控闲置 AXI 时钟。它不能替代33MHz像素时钟、真实面板、TPG、VDMA、触摸或整条视频链测试。原厂480p配置为800×480、HTOTAL1056、VTOTAL528、像素时钟标值33000kHz；60为标称刷新标签，按33MHz与总像素计算约59.19Hz，未实测。

## 纠错与保留的失败证据

1. **导出的重建脚本缺少AXIS自动推导参数。** 按已综合基线XCI恢复两份转换器各14项接口属性，保留TKEEP/TLAST/TUSER等信号；没有用全零或删除接口绕过。第一次失败保留在`p30-create-20261019T093658Z`。
2. **ADI接口库误推导显示数据为FIFO总线。** 仅在副本的两个模块数据端口补充`X_INTERFACE_IGNORE`。去掉标注后与原厂逻辑文本一致，版权保留。依据[AMD UG994](https://docs.amd.com/r/en-US/ug994-vivado-ip-subsystems/Inferring-Control-Signals-in-a-RTL-Module)。本轮一次GUI解释器创建错误、一次已存在连接重复错误及一次内部Tcl读取错误分别留档；最终重建/审计通过，不掩盖失败。
3. **旧XDC含不支持的if/unset。** 最初出现Designutils 20-1307，条件检查不能当有效门禁。改为纯声明约束，把唯一层级、唯一主时钟和严格/2关系检查移至实际构建Tcl，完整重综合通过。旧XDC/DCP保存在`results/p30-xdc-correction-20261019T100001Z/`。
4. **ClockWiz把PS内部时钟当成外部输入，重新定义主时钟。** 首次布线虽WNS+0.480/WHS+0.013，却有TIMING-4/TIMING-27，不能通过发布。改`PRIM_SOURCE=No_buffer`，保持频率和MMCM比例，重新生成/综合/布线；最终报告不再含这两项严重告警。初次DCP/BD/报告在`results/p30-clock-source-preparation-20261019T133005Z/`。
5. **未使用外部TDD输入原来悬空。** 合并顶层接零，不冒充外部TDD同步实现；该相关CDC关键路径消失。当前FDD用途可继续，未来外部TDD需重做同步与测试。
6. **VTC测试编写中的启动/寄存器错误。** 首次宏传参未展开、缺glbl、寄存器偏移写错均在仿真中暴露。按留存的[Xilinx 2021.1驱动](https://raw.githubusercontent.com/Xilinx/embeddedsw/xlnx_rel_v2021.1/XilinxProcessorIPLib/drivers/vtc/src/xvtc_hw.h)核对后修正。1080p长仿真曾限时/主动停止，未写成通过；最后按实际800×480目标验收。
7. **旧板恢复兼容性。** P21 SHA256SUMS仍有CRLF，先拒绝，再仅在新恢复包生成LF清单并与P21记录哈希核对，原文件未改。上传字节校验通过，但BusyBox tar不支持-z；保留失败报告，复用已上传文件，用gzip解压、核对解压字节SHA，再用普通tar继续，未重复上传或修改固件。

## 还不能宣称完成的内容

- 外部时延仍缺：7个输入、66个输出。布线通过只覆盖已约束路径。未用零时延、放宽周期或新增false path作修复。
- 最终CDC仍有58项Critical：{'CDC-1': 50, 'CDC-10': 4, 'CDC-12': 2, 'CDC-13': 2}。原59项的分类是56项DMA、2项时钟MUX、1项TDD；当前TDD项消失，其余不能凭上游代码来源免审。FIFO握手/复位、BUFR→BUFGCTRL拓扑和DRC异步RAM控制仍需审查，DRC规则可能截断显示数量。
- 候选PS配置仍不是当前完整FSBL初始化的证明。原理图第10页及内核pinmux均确认调试UART为MIO12/13，第9页风扇为MIO8；运行时IO-standard与预编译PS-init还存在差异，不盲写寄存器修复。
- 本次冷启动成功与上午三次0xFF失败都保留；间歇启动根因未解决，不再称每次必失败，也不因一次成功称已修复。
- 真实VTC运行时覆写已在仿真验证，但实际ClockWiz动态配置、TPG/VDMA/DRM及目标TTL屏幕还未合并上板。LVDS/HDMI模式不能借TTL结果验收。
- 未新增已知源发射、长期无丢样、真实AI准确率或绝对频率/功率标定。864项Python回归是前轮结果；本轮以工具实际构建、RTL仿真、87项结构检查和板端恢复为验证。

## 恢复与下一步

1. 当前工程`E:\p30c-1019-174235\project\combined.xpr`；构建/重建说明见[合并说明](../../fpga/integration/README.md)。最终DCP是检查存档，不能直接当作可部署固件。
2. 新板当前rf，屏幕黑屏符合原厂互斥模式。旧板临时目录`/tmp/p12-source-stage-p30-132637`；native工具在`stage/arm/arm-tx-source`，后续限时发射只选`bundle/`三份峰值256波形。`stage/waveforms`六份只是兼容检查，并非重新批准其发射功率。
3. 优先完成剩余CDC/复位、外部IO时延及实际内核/设备树契约，再设计可回滚的临时加载；不覆盖BOOT.BIN/FSBL或原厂固件。
4. 上板分开验收：目标800×480显示→已知源RF→二者并行→ARM指标显示。长期采集/AI独立验收。

## 原始证据

- [synthesis](../../results/p30-synth-20261019t133134z/report.json)
- [route](../../results/p30-implement-20261019t133527z/report.json)
- [graph](../../results/p30-graph-verification-20261019t133631z/report.json)
- [vtc](../../results/p30-vtc-test-20261019t100408z/report.json)
- [gpio](../../results/p30-gpio-test-20261019t093658z/report.json)
- [tx_restore](../../results/p30-tx-file-verification-20261019t133248z/report.json)
- [sparse_rx](../../results/p30-smoke-archive-20261019t132314z/report.json)
- [vendor_sources](../../results/p29-source-verification-20261019t132730z/report.json)
- [最终交付清单](../../results/p30-delivery-20261019t134403z/report.json)
- [重新上电日志](../../results/p30-reconnect-20261019t132135z/report.json)
- [载板原理图提取与页图](../../results/p30-schematic-20261019t093956z/report.json)
- [原厂800×480配置](../../results/p30-display-profile-20261019t100223z/report.json)
- [VTC主参考留存](../../results/p30-primary-reference-20261019t095413z/report.json)
- [交付后180项文件与证据一致性检查](../../results/p30-delivery-verification-20261019t134804z/report.json)：DCP/源码/原始报告摘要/仿真输入/采样字节及文档链接核对通过。不是新增180个功能测试，不代替上板验收。
- [最终板端只读状态](../../results/p30-end-state-20261019t134633z/report.json)：两板boot_id保持一致，新板仍为原厂rf/operating，RX属性读回正确、buffer与4个scan enable均为0；旧板inspect通过，未观察到收发程序运行，两个串口已释放。未测物理RF静默。

`results/`被gitignore排除，保存项目时需连同此目录及E盘工作副本备份。没有删除或改写原始采样；停止前正常结束实验并sync/关机，旧板RAM临时文件下次仍需恢复。
