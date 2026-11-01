# 双板路线与旧 P201 信号源候选：2026-10-16

> **⚠️ 本文件是 13:16 的历史快照。正文不改写，保留追溯；下列结论已被当天更晚的工作取代或需要限定。**
>
> | 本文件原结论（含行号） | 最新状态 |
> |---|---|
> | 第7行"旧板本次实际执行…待验证" | 旧板**已实际执行 3 次限时射频发送**（3 s / 5 s / 5 s），见 [EXP-TX-001](exp-tx-001.md) |
> | 第43行"源SHA `626f5797…` 为部署版本" | 该版要求非空 `hw_serial`，**本板 `hw_serial` 为空会自拒发射**。实际发射使用 15:39 修订版 `b9ba90d3ec85359e5b584704702e80d544ffb26e1fd28c271563316d1e41dd30`（ELF `0a188e1e…`） |
> | 第58行"646 passed，42.19s" | 现为 **667 项通过**，归档 `results/p13-python-regression-20261016T082222172Z/` |
> | 第61行"34/34场景" | 现为 **43 项通过**，`results/p12-native-mock-20261016T074043903949Z/report.json` |
> | 第64行"真实RF频率/功率/调制验证 待验证" | 射频**发射已执行**；但**频率与功率仍未验收**（归档照片标记不在主峰上），三类调制的接收验收仍未做 |
>
> **本文件仍然有效的部分**：15 个波形的格式与哈希、ARM 程序的守卫设计、交付包内容与 `archive_sha256`、DMA/PHY/文件速率一致守卫、以及"未改板卡RF设置/固件/Git"的边界声明。交付包本身**未被取代**，仍是波形与文档的来源；只有包内的 `bin/arm-tx-source` 因 `hw_serial` 守卫不可用于发射。

## 目标与边界

用户提供 D:/AD9361 新借板资料，拟让旧 P201 发送、新带屏板接收显示；授权AI继续读资料、编程和测试，并保留实验记录。本次复用10月15日已有进展，不重装原项目环境/烧写，不照资料中的制卡、saveenv、PL加载或天线发射步骤自动操作。

本记录不是“P12整体完成”。**信号源文件、ARM程序候选和电脑模拟验证已完成；旧板本次实际执行、新板接收与屏幕联调、受控RF均待验证。**

## 资料学习与新路线

详细依据：[新板资料审查](../design/new-board-ad9361-review-20261016.md)；系统分工、速率与验收顺序：[双板方案](../design/two-board-rf-link.md)。

原始资料共54文件、3,091,408,245字节，35个手册/源码/设备树等文件建立SHA256；不是对全部大镜像重新计算hash。已读取主要环境/开发手册、相关射频原理图和默认DTS/HDL；只读扫描rootfs共28,828成员，提取必要配置/库名、解析DTB并渲染关键完整页面。证据保存在 results/p12-new-board-review-20261016，D盘原资料未修改。

资料对应 TLZ7xH-EVM + AD-FMCOMMS3-EBZ，案例支持xc7z045/xc7z100，与旧P201的7020不同。补查扫描型产品目录37页后，第20页确认有HDMI IN/OUT、LVDS、背光、LCD RES及12V DC@3A标签；仍缺实物对应、插头极性/尺寸、屏型号/pinout/驱动。镜像含Qt5.7.1/Xorg，未从射频案例PL/DTB找到显示链路，不能将“自带屏”写成分析结果已可直接显示。新资料镜像glibc2.23/libiio0.20，不等于老师实物系统，也不直接沿用旧板0.24接口守卫。补查证据在results/p12-new-board-catalog-20261016，未将相近TLZ7x-EasyEVM的7020规格套到TLZ7xH。

## 实现内容

### 周期发送参考与格式

新增 src/rfsig/tx_waveforms.py 与 tx_package.py，复用已测试的调制映射和RRC。周期成形使用中心对齐圆周卷积，单音和数字搬频为整周期；通过与独立时域周期卷积及重复波形中段对照，避免直接循环P04的完整卷积尾巴。

原厂 axi_ad9361_tx_channel.v 的 DMA 路径使用 dma_data[15:4]；IIO报告TX存储s16/16>>0。因此文件是小端 int16交织I/Q，逻辑signed12 DAC码乘16，低4位0。不是RX码直拷，也不是归一化浮点直接astype。生成器峰值1..2047，本次512；码值、数字平均功率与RF dBm明确区分，不据此声称发射功率已知。

三套各5波形（正/负单音、BPSK/QPSK/16QAM）：

| 包 | 条件 | 电脑证据目录 |
|---|---|---|
| existing30m72 | Fs30.72MS/s；Rs240ksym/s；单音±960kHz/调制+960kHz；每波131072点 | results/p12-source-existing30m72-20261016T044743394644Z |
| planned4m250k | 计划Fs4MS/s、Rs250ksym/s、偏移±500/+500kHz；每波32768点 | results/p12-source-planned4m250k-20261016T044829901727Z |
| planned4m125k | 计划Fs4MS/s、Rs125ksym/s，其余同上 | results/p12-source-planned4m125k-20261016T044831216976Z |

所有配置仍只是文件参数；本次未改板卡Fs或FIR。4MS/s方案需要实际两板合法速率核对及接收搬频/滤波/抽取后才匹配1MS/s模型；30.72MS/s方案Rs240k不等于旧模型250k。理论RRC频带不当作99%实测占用带宽。三类统一分量峰值会有不同平均功率，本次未用其做新训练/准确率，周期重复帧也不是独立测试集。

### 原板本地有限时发送程序

新增 embedded/arm_tx_source/arm_tx_source.c，使用原板既有libiio0.24，ARM Cortex-A9/hard-float/NEON。板端程序核对P201型号、真实hw_serial、TX端口、Fs/LO/BW/gain与文件SHA；不写射频参数。原厂TX0有8倍插值，最终版额外要求**DAC DMA采样率=PHY TX采样率=PHY RX采样率=文件Fs**，只支持插值旁路；DMA速率缺失或3.84M/30.72M不一致时拒绝，不切active/GPIO。参数/字节/低4位/同一文件流SHA在dlopen之前检查。

模式：--sha256-selftest、--check（纯文件）、--inspect（只读IIO）、--run（实际发射入口，**本次未在实板调用**）。run需核对物理链路，命令不写入自动启动脚本，也不配置服务。

生命周期：BIST/loopback关闭、DDS scale0 → DDS raw0 → 创建cyclic buffer（驱动选择DMA）→ push → 本地单调时钟截止/信号 → cancel → join → destroy → DDS raw0并读回。看门狗线程在总时长截止时可取消阻塞push；信号处理器仅置flag。总时长参数最大60秒，含push耗时；3秒是libiio context timeout设置，不宣称驱动忽略超时时也有独立3秒硬互锁。数字零/清理不能证明RF绝对静默或消除LO泄漏。

权威编译：results/p12-arm-tx-prepare-20261016T051034359240Z；源SHA 626f57971c8a409fb3e4d751b798af2eb4c89794eb88c5e641ef462ea419e01f。ARM ELF SHA 5e242107723f8e9dfb31ebbae423811bfc7e0efe3f87f3e5e607ecdac17ba548；ELF32/ARM hard-float/NEON及GLIBC符号2.4核验，不等于本次已经在ARM运行。051034版覆盖此前未核对DMA速率的中间版本。

### 计划核验与只读入口

src/rfsig/rf_link_budget.py 对连接器峰值上限、最小衰减、线缆损耗下限、接收推荐上限、衰减器额定输入及余量计算，并检查频段、序列号、波形哈希和本地证据。测试数值是明确的虚构fixture，**不是P201或FMCOMMS3的推荐参数**。

host/tx_source.py 提供verify/inspect/review；review只输出命令参数建议，不执行发射。plan JSON不等于物理接线证明，板上程序还会重新读配置。生成的link-review.INCOMPLETE.json保留未知值并拒绝通过，不填造功率数据。

run-tx-source-inspect.cmd仅读取IIO；新板的 experiments/p12_receiver_readonly_probe.sh 仅读取型号/系统/IIO/显示节点，已sh -n语法检查，**未在新板运行**。

## 验证与验收

| 项目 | 状态 | 实测依据 |
|---|---|---|
| 周期波形与格式、计划/证据拒绝 | 通过（电脑） | 新增113项专项，含69波形、13包、31预算/计划测试 |
| 全项目Python回归 | 通过（电脑） | 646 passed，42.19s；results/p12-final-regression-20261016-131336 |
| ARM交叉编译与SHA/输入拒绝 | 通过（编译/主机） | 权威prepare目录12个host case；3个标准SHA向量另含在selftest |
| 15个完整波形原生C读回 | 通过（电脑） | results/p12-tx-file-suite-20261016T051317205386Z/report.json；--check在dlopen前返回 |
| IIO生命周期/异常停止 | 通过（模拟设备） | results/p12-native-mock-20261016T051205271366Z/report.json；34/34场景 |
| 原P201本次IIO连接 | 待恢复 | 13:00电脑出现COM9/FTDI；SecureCRT占用，串口打开被拒；无USB数据网卡，ip:192.168.2.1连接失败 |
| 原P201本次ARM候选实际运行 | 待验证 | 没有把主机运行或交叉编译当板端结果 |
| 真实RF频率/功率/调制验证 | 待验证 | 仍缺两板实际端口电平/衰减与接线证据，未发射 |
| 新板屏幕与射频共存 | 待验证 | 只有资料审查，无实物状态与组合工程证据 |

mock是私有内存共享库，只记录fake IIO调用，不访问设备/网络/实际IIO后端。覆盖只读inspect、型号/serial/port/RF/DDS/DMA速率门禁、create/step/first/push/DDSwrite失败、0.1秒本地deadline、堵塞取消、Linux SIGTERM及清理顺序。它证明程序逻辑，不证明实际射频硬件的时长、幅度或停止后输出。

## 交付与恢复

合并包：results/p12-source-delivery-20261016T051524098482Z/p201-source-20261016T051524098482Z.tar，4,177,920字节，SHA256 34d477d8322a3d8652bc19279c9e42b5ccfc56bf988576037840a18c2f2542e3。包含最终DMA速率守卫版ARM程序、15个原始波形、元数据、更新的缺失事实模板、SHA256SUMS、CHECK-ONLY.sh和INSPECT-ONLY.sh；没有自动发射脚本。电脑原始NPZ/bit/符号/taps仍在三个source目录，未为精简传输包删除。050229中间交付和050712第一次封存均已被此修正版替代，保留历史不部署。

先释放COM9或接回旧板OTG数据线，再只读恢复身份/配置；有数据网络时传入新的/tmp目录并校验，先CHECK-ONLY和INSPECT-ONLY。不要运行旧的中间prepare包，不要拿Windows/WSL主机可执行文件上板。

实际发射仍需：两块实物与正确口、旧板含PA的TX峰值输出依据、新板RX推荐输入、50Ω同轴及按电平确定的衰减器。文件生成完毕不能替代这些条件。新板还需主板基础资料、屏型号/接口、现用系统和显示工程；优先保留老师现有能显示的系统。

电脑当前状态证据：results/p12-current-host-state-20261016-125956/host-state.json；IIO失败记录 results/p12-readonly-20261016T050005378017Z/report.json。已向用户说明最少操作是断开SecureCRT COM9或接回OTG；未强制关闭终端或操作板卡重启。

## 修改、环境和错误留存

新增波形/预算/打包/只读工具、原生TX与mock、测试和文档；不改原厂固件/FPGA工程、不改模型、不重训、不执行RF/重启/烧写。资料目录只读。重要入口修改前备份：results/p12-doc-prechange-20261016-125401。Git index继续使用历史SHA8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d，未add/commit/reset。

本机WSL原先有ARM交叉工具但缺本机gcc；为完整mock验证在电脑Ubuntu-24.04增加gcc/libc6-dev/python3依赖，日志results/p12-host-build-deps-20261016-125051。未向板卡安装库。

保留中间失败/修正：首轮WSL无gcc、中间离线分支/未钉死serial/hash的版本未交付；独立检查发现DDS归零顺序会让DMA输出零，已修正后重新编译/模拟；计划模板None类型错误、包元数据与重新生成交叉验证补强；首轮mock在NTFS逐事件写日志太慢触发外层杀模拟进程，改Linux/tmp后复制；两例原断言把context本地disable误算为RF配置写，改为仍严禁DDS/enable/create/push。第一轮封存后复查发现8倍TX插值的DMA速率遗漏，追加双端速率守卫和3项Python/2项mock拒绝检查，重编、15文件复核、646回归与新交付全部通过。旧证据不覆盖，最终源/包/模拟报告通过哈希关联。
