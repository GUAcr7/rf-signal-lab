# EXP-HW-018：独立审查、纠错与多缓冲推进

- 日期：2026-10-18；报告生成 2026-10-18T12:39:47.193238+00:00。
- 范围：主 AI 的 HW-015/016/017 交付、原始字节、参考测量、启动脚本与多缓冲采集。已授权修复及上板复测；没有代替 GUI 验收。
- 验收结论：**有限已知源接收通过；长期连续性未通过；本轮软件修复与普通启动通过；真实 AI、RF/display 共存仍待实现。**

## 1. 必须修复项与结果

| 严重程度 | 原位置 / 问题 | 影响 | 修复 / 复测 |
|---|---|---|---|
| P1 | HW-017 / P25：两缓冲零模差当无丢样；失败窗被删后比较非邻居 | 虚假连续、跨缺口滤波 | 保留索引、可信门限、有符号模差与不可证边界；旧对照仍复现 12 处；新 16 缓冲检出 11 处 |
| P1 | S99board：仅 iio:device1 存在即就绪；忽略 rmdir 失败 | PHY/ADC/DDS 不全时假成功、假重试 | 按三个名字确认，移除失败即停；真实脚本在模拟驱动下覆盖第 1/2/3 次成功、耗尽与移除失败；原子部署后 warm reboot 通过 |
| P2 | P23：TX 标称偏移与 RX 实测载波混用重建参考 | +33.97 dB 假差 EVM、难以定位硬件 | 新 known-source 接口分开处理，逐字节重建 TX 核验；QAM 两份 −37.23/−37.30 dB |
| P2 | align_rotation 只比最小 EVM，复增益隐藏残相位 | 不能证明坐标轴已对齐 | 去掉残增益相位，测试检查轴向与估计角 |
| P2 | 粗频偏 + 因果 PLL 启动过程影响短块 EVM | big2 仍被算成 −31.05 dB | 全有效符号批量判决反馈拟合相位斜率，无额外裁差；与已知参考吻合 |
| P2 | HW015/RESUME/状态：QAM 矩无意义、QPSK 90°、I/Q 比旋转不变 | 错误教学、错误指标解释 | 改为集合四阶矩、45° 标称矩相位、轴向限定；有数学和注入数据测试 |
| P2 | HW016/状态：1200 Hz 写成 40 ppm | 混淆 RF 与采样时钟 | 相对 2450 MHz 是 0.49 ppm；不据 CFO 判定哪块 LO 或 SCO |
| P2 | 入口停在 HW014、部署状态和“0/250”过期 | 恢复时重复/误操作 | 更新入口/机器状态/恢复清单，后半段检查数为 251/份；旧版备份保留 |

## 2. 原始证据复核

P24 三调制均验证：串口 base64 解码 = 已有 raw 文件 = 板端 SHA256。P25 三段回传重组与 1048576 B 原始字节、板端 SHA 一致。P26 新采集使用分块 gzip 回传，逐块哈希、压缩包 SHA、解压后原始 SHA 和长度全部核验，重启前全量回收。

| 调制 / 数据 | 已知符号 EVM dB | 有效符号 | 后半段错误/检查数 |
|---|---:|---:|---:|
| bpsk / 冷启动 | -37.19 | 502 | 0/251 |
| qpsk / 冷启动 | -37.97 | 502 | 0/251 |
| qam16 / 冷启动 | -37.64 | 502 | 0/251 |
| qam16 / big1 | -37.23 | 502 | 0/251 |
| qam16 / big2 | -37.30 | 502 | 0/251 |

载波与源位置使用全块已知发射序列；后半段虽单独用前半段增益判决，也不是完全独立的 BER 试验或 AI 测试。低 EVM 不替代实际发射功率/频率标定。

## 3. 本轮两次真实 RF 试验

复用数字峰值 256、TX gain −10 dB、RX manual/0 dB、LO 2450 MHz、Fs 30.72 MS/s、RF BW 18 MHz及原接线。没有写 RF 属性，没有增加功率；两次发射都由原生守卫限 30 秒，退出 0、资源释放、DDS 零源读回。物理 RF 静默/LO 泄漏没有测量。

| 输入存储通道数 | 每 DMA 样本数 | 窗口数 | 检出跳跃边界 | 判定 |
|---:|---:|---:|---:|---|
| 4 | 4096 | 16 | 12 | detected_jumps |
| 4 | 65536 | 2 | 0 | modulo_consistent |
| 4 | 65536 | 4 | 0 | modulo_consistent |
| 4 | 65536 | 16 | 11 | detected_jumps |
| 2 | 65536 | 16 | 0 | modulo_consistent |

**RX1 16 缓冲：未检出非周期跳跃；仍不能证明长期无丢样。** 四通道时消费者需搬运 245.76 MB/s，RX1 为 122.88 MB/s（理论原始负载，非已达成吞吐）。完整记录 wall time 包含启动/落盘，不能直接换算丢样总数。落点确认是 tmpfs，不能凭文件路径把原因归咎 SD。

源周期 131072 样本。即使模差为零，也可能漏一个或多个完整周期；±1 是估计容差，不是已证明的物理解释。有符号负模差不能当负丢样数。具体驱动排队、调度、复制机制仍需独立观测。

## 4. 启动脚本与最终状态

审查版 SHA `2a5533091321e1fe6329f8ac95ad63a0fc07f13407d865a37d1cda97484afb3e`；原版备份 `/etc/p26-S99board-before-20261018`，不放在 rcS.d 的 S* 名字下。安装临时名不匹配 S*，校验后原子替换，权限 755。

新板一次 warm reboot 的 boot_id 确已改变，实际脚本日志完整、PHY/ADC/DDS 都可见，成功 attempt **1**。真实 attempt 2/3 分支执行：**False**；模拟驱动分支通过不能替代真实间歇故障复测。一次 0xFF 重绑恢复只证明可恢复，不证明芯片无间歇问题或确定时序根因。没有为了测试故意破坏复位/电源/驱动。

新板最后 rf 模式，屏幕与 RF 官方位流仍互斥；旧板无活动发送，串口工具已释放。warm reboot 后运行 RF 配置读回如下，**不是重启前配置继续生效的假设**：

```text
cat in_voltage_sampling_frequency in_voltage_rf_bandwidth
echo __P22_RC__:$?
root@Zynq-Tronlong:/sys/bus/iio/devices/iio:device1# cat in_voltage_sampling_fre 
quency in_voltage_rf_bandwidth
30720000
18000000
root@Zynq-Tronlong:/sys/bus/iio/devices/iio:device1# echo __P22_RC__:$?
__P22_RC__:0

cat in_voltage0_gain_control_mode in_voltage0_hardwaregain
echo __P22_RC__:$?
root@Zynq-Tronlong:/sys/bus/iio/devices/iio:device1# cat in_voltage0_gain_contro 
l_mode in_voltage0_hardwaregain
slow_attack
71.000000 dB
root@Zynq-Tronlong:/sys/bus/iio/devices/iio:device1# echo __P22_RC__:$?
__P22_RC__:0
```

## 5. 测试与证据索引

Python 全回归 **840 passed**，见 `results/p26-verification-final-20261018/pytest.log` 与 JUnit。新增检查含：非邻窗/弱匹配/整周期不可见、QAM 数学矩与轴向、频偏注入、RX/TX 不同载波的黄金参考、启动脚本模拟失败与重试、传输截断拒绝。没有以 expected 值冒充实测。

- 独立审查：[report.json](../../results/p26-independent-audit-20261018t122935z/report.json)。
- 修复特征：[features.json](../../results/p26-known-modulation-features-20261018t121600z/features.json)。
- 4/16 四通道采集：[report](../../results/p26-multibuffer-acquisition-20261018t115942z/report.json)，完整 [回传记录](../../results/p26-chunk-transfer-20261018t120112z/report.json)。
- RX1 采集：[report](../../results/p26-multibuffer-acquisition-20261018t122051z/report.json)，完整 [回传记录](../../results/p26-chunk-transfer-20261018t122135z/report.json)。
- 启动部署：[report](../../results/p26-boot-deployment-20261018t121928z/report.json)，[warm reboot](../../results/p26-boot-verification-20261018t123023z/report.json)。
- 完整测试：[pytest.log](../../results/p26-verification-final-20261018/pytest.log)。
- 原文/代码备份：`results/p26-before-20261018/`。新代码、测试、实验脚本与机器状态都在项目内；results 被 Git 忽略，需独立备份。

## 6. 下一步按依赖

1. 采用本轮单 DMA 可靠快照接口，RF 配置、mask、边界、源哈希与会话 ID 绑定。长流问题解决前不跨未知边界做滤波/PLL。
2. 独立观测采集/消费队列，尝试采集先入预分配内存、分析/落盘分离；依据实际 AD9361/PL 速率链评估降采样。只增缓冲仅延长突发时间，不能宣布持续吞吐通过。
3. 引入硬件样本计数、不重复源标记或等效证据，验证更长连续采集和停止/重启。未取得证据继续标待验证。
4. 用独立会话和随机发送内容采集真实数据集，记录各类、SNR 方法、分组划分。不能以同一个循环帧随机切片构造虚高准确率，也不能把已给定调制的预处理当盲识别。
5. 继续实际新板工程的 FPGA 数据链与 RF/display 共存；模块测试/桌面回放/合成模型结果保留已有验收范围，不替代整机验收。

本轮无新 FPGA 或 AI 模型实现，所以不伪造资源/时序/量化指标；这些环节在对应开发阶段验收。无需用户重复安装或寻找信号源；后续物理测量/界面点击需要时再给最小步骤。

## 7. 重启后的恢复与工具复测

上面的启动读数是原厂默认：slow_attack/71 dB，LO 2400 MHz。本轮已先归档 before，再仅恢复经验证的 RX manual/0 dB 和 RX LO 2450 MHz，并逐项读回。采样率、带宽、端口与 TX 不变，期间不发射。最后实际配置：

```json
{
  "in_voltage_sampling_frequency": "30720000",
  "in_voltage_rf_bandwidth": "18000000",
  "in_voltage0_rf_port_select": "A_BALANCED",
  "in_voltage0_gain_control_mode": "manual",
  "in_voltage0_hardwaregain": "0.000000 dB",
  "out_altvoltage0_RX_LO_frequency": "2450000000"
}
```

恢复证据：[report](../../results/p26-rx-profile-restore-20261018t123231z/report.json)；冻结配置 [profile](../../configs/rf-link-snapshot-p26.json)。启动脚本持久化不代表这些运行属性持久化；下次断电后仍须核验。

本轮工具自身也有两次被守卫拒绝的检查：首次重启验证误接收关机前残留提示符，因 boot_id 未改变而失败；没有再重启，只在原重启完成后续查并验证新 boot_id。之后增加新启动横幅条件。RX 读数解析曾把控制台折行片段当值，**在写入前拒绝**；改为明确值帧，补三项解析回归后实际恢复成功。失败目录保留 `p26-boot-verification-20261018T122934Z` 与 `p26-rx-profile-restore-20261018T123154Z`，不抹去失败记录。

## 8. 实测对照图

左图比较相同采样率/缓冲长度下的四通道与 RX1 模周期源位置；右图比较 16QAM 粗估计、因果 PLL、批量精修及已知发送符号对照。低 EVM 与零模差各自有本报告列出的使用范围。

![P26 真实证据对照](../../results/p26-review-figures-20261018t123537z/review.png)

## 9. RX1 全部 16 个 DMA 窗口的符号质量复核

对新 RX1 原始文件的每个 65536 样本窗口单独匹配、下变频和滤波，没有跨边界处理、没有删除差窗口。合计 **8032 个有效符号**，按每窗前半段增益检查后半段，合计 **0/4016 错误/检查数**；逐窗已知符号 EVM 为 **-38.08 ~ -37.04 dB**。相同源位置诊断未检出非周期跳跃。

这为 RX1 mask 和整段窗口内的信号质量增加了实际证据；名义样本量仅对应 **34.133 ms**，源仍周期重复，且每窗使用全窗已知源拟合，所以仍不声称长期无丢样、独立 BER 或 AI 准确率。证据：[逐窗报告](../../results/p26-rx1-symbol-quality-20261018t123837z/report.json)。
