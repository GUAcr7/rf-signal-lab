# P52：独立真实RF数据、AI训练与验收

日期：2026-10-24（北京时间），进行中。用户明确切回“完成真实信号AI识别”，旧P201 UART分支保留，不部署、不继续扩展。

用户确认两板已供电、原接线恢复。pyserial/PnP确认COM8/CH340与COM9/FTDI，不能只用Win32_SerialPort漏列结果判断板卡缺失。本轮新板boot为4e7438d3-3e8f-470d-86a5-abf5f732bb71，旧板boot为a7d78ffb-f1a1-4472-937d-0846e345c6ac。新板自动P48已运行约45分钟；按既有owned control停止并临时暂停下次启动选择用于归档，不重启、不热装PL/卸驱动。

启动观察：results/p43-observed-cycle-20261024T031944Z/report.json，仅existing_new_boot_power_cycle_not_verified，不冒称真断电实验。最后IQ/屏幕复核：results/p42-review-20261024T032421Z/report.json。新boot时钟寄存器/驱动读回：results/p36-clockwiz-readback-20261024T032659Z/report.json，LOCK和M16.5/D2/O25约33MHz一致。

协议提前冻结在results/p52-plan-20261024T032533Z/report.json：6训练seed/3验证seed/3测试seed，采集组隔离、同组所有片段归同split；每类每seed两个完整65536样本DMA块，不跨未知间隙滤波/拼接。每组先采单音作公共IF校准；每次TX最大15秒、峰值256、TX -10dB、RX manual0dB、固定2450MHz与30.72MS/s，未提高功率。测试组在模型与推理流程冻结后再采集。

已见P46/P51 36帧完全排除出新训练/验证/测试。新P52已知源质量分析从受校验metadata重建精确源，移除P46固定seed=20261016假设，但不改旧脚本。38项输入、源包、前端/校准检查通过。模型输入仍用P51独立DMA的抗混叠前端和只依赖单音的公共校准，不使用真实调制标签拟合各类载波。

P201源包通过既有USB网络从电脑临时HTTP只读端点获取，板端验证压缩包/展开包/每个成员SHA、原保护程序--inspect/--check。服务器只提供指定/pkg.gz，结束即关闭。上传本身不发射。完整TX与接收/清理沿用P46控制逻辑，单次TX由30秒缩至15秒，并要求采集在保守14秒主机窗口内完成。所有错误、失败窗口和原始返回数据保留。

运行态权威入口为results/p52-active.json与批次report.json，COM8/COM9由子任务依次持有；不得另起板卡脚本。结束前必须恢复同一P48持久启动选择并只读确认idle，不能留下暂停状态。真实分类通过前不把标签接上小屏，也不将已知符号EVM冒充AI准确率。

## 11:58阶段记录（尚未完成验收）

前五组新RF源均完成原始字节SHA/CRC与已知符号质量检查，第六组采集中。数据集计划为108训练帧、54验证帧、54测试帧；帧来自独立seed组，不能把同一65536样本DMA中的三个片段当作三个独立射频实验。所有采集仍在同一板卡boot、同一接线和固定RF设置下，分组会话是采集组织，不代表独立冷启动或不同射频环境。

新增`p52_finish_learning.py`串行衔接已运行批次→数据集→训练→C/ARM导出冻结→新测试源采集→独立测试→实际ARM文件推理→离线实时显示候选构建。子任务一个接一个运行；任一门禁失败即停止，不能通过改测试集、丢弃失败帧或继续调模型绕过。当前训练/验证批次为results/p52-batch-20261024T033013Z/report.json；衔接记录为results/p52-flow-20261024T035339Z/report.json。

完整C前端旧权重数学探针results/p52-frontend-probe-20261024T034039Z/report.json通过，包含RX12高四位未定义位不影响结果、三类新RF输入Python/C数值一致、错误IF/模式/长度拒绝。此探针没有训练新模型，不是识别验收。ARM串口结果核验7项离线反例检查通过：results/p52-arm-evidence-tests-20261024.xml。当前boot显示单位/像素复核通过：results/p48-unit-review-20261024T034519Z/report.json。

实时显示候选隔离在P53生成器中，保留原P48程序不变。由同一个完整65536样本DMA取前8192样本画频谱，并对其中三个有效1024点AI窗口分类。仅显示BPSK/QPSK/16QAM三个封闭类别与处理时间，不声称任意信号分类、无信号拒绝或校准置信度。单次接收只允许0.1～10秒，后续拟以每类6秒配合原15秒保护发射窗口验证；尚未上板。旧权重离线模拟探针results/p53-probe-20261024T035648Z/report.json通过，不能冒充真实AI结果。

## 12:03～12:10：串口故障、保留失败记录后恢复

原批次完成六组训练数据后，在第七组验证源的BPSK接收已完成、压缩与SHA已读回之后，COM9触发Windows `ClearCommError failed (PermissionError 13 拒绝访问)`。失败记录results/p52-known-20261024T040217Z/report.json与原批次report保持原样；原衔接流程自动停止，没有开始训练或测试。不能把旧批次的`serial_closed`直接解读为板卡idle；失败后的idle必须新读回。新采集器已修正失败状态的这一显示口径。

首次恢复检查看不到COM9提示符，原因是该任务已设置PS1为空并关闭回显，而通信中断没能恢复终端。以只读`uname`、boot/taint与进程查询识别仍为原P201后，才恢复回显/原提示符；没有盲发Ctrl-C、重启、复位或重新配置射频。results/p52-tty-recovery-20261024T040457Z/report.json通过。随后results/p46-preflight-20261024T040507Z/report.json确认两板均原boot、taint0、DMA闲置，旧板DDS源读回为零；不把当前idle冒称历史丢失的TX完成消息。

中断产生的tone/BPSK共四个DMA块单独完整回传，results/p52-quarantine-20261024T040628Z/report.json，SHA/CRC通过，明确排除出AI。失败窗口没有按AI成绩或解调质量筛选。保留已完整验收的六组，按同一冻结协议重新采集未完成的第七组及尚未采集的第八、九组；这是排查后的显式通信故障恢复，不是对质量失败自动重试。

当前恢复批次：results/p52-batch-20261024T040915Z/report.json。新的学习衔接任务等待该批次完整后才运行，旧失败衔接记录保留。模型/测试尚未暴露；RF功率、接线、FPGA和驱动均未改。

另修正了RAM目录核验：Yocto的/tmp可能经符号链接位于/var/volatile/tmp，必须解析真实路径并检查最近挂载点为tmpfs，不能只查字面的`/tmp tmpfs`。5项含嵌套持久挂载反例的检查通过：results/p52-ram-gate-tests-20261024.xml；尚需后续实际ARM步骤读回当次路径。

## 12:25～12:34：300轮训练不足，按验证集延长训练并另留新测试组

九组训练/验证完整采集通过，数据集results/p52-dataset-20261024T042524Z/report.json：108真实训练帧、54真实验证帧；162帧来自54个调制DMA块，不是162个独立射频会话。第一次300轮CNN训练results/p52-trained-20261024T042525Z/report.json，最小验证交叉熵选第294轮，FP32 44/54、INT8 45/54，验证集未达到90%目标。模型/导出仍保留，不冒称完成。

基线模型在results/p52-export-20261024T042538Z/report.json冻结，其原预定测试seed2310～2312继续按原协议执行；截至新模型选择完成时没有读取这些测试I/Q或分类结果。改进仅由验证集触发：同一108/54帧，同一115参数Conv8网络、训练增强、优化器、量化和最小验证损失选择规则，将训练轮数由300增至3000。没有改动旧冻结模块/权重。

改进协议：results/p54-plan-20261024T042837Z/report.json；新测试源seed2026102313、2314、2315，只在电脑生成并校验源包，尚未射频采集。旧测试seed2310～2312明确排除出改进模型验收；训练/验证数据沿用，原始RF证据不复制伪造。较早results/p54-plan-20261024T042814Z/report.json有source_bank路径文字不当，未用于训练/发射；已保留该草稿，用后一个新协议替代，未改写旧协议。

改进训练results/p52-trained-20261024T042912Z/report.json：3000轮耗时120.23秒，第2991轮最小验证交叉熵0.14414，FP32/INT8验证集均53/54，BPSK18/18、QPSK17/18、16QAM18/18。模式按既定验证规则选INT8。新模型SHA256 bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457；量化模型d900b28411275a3e080b896a3c0fd4f1aa82d978f09eb2aa8a0413f258d02582。

新模型C完整前端对照通过并于results/p52-export-20261024T043113Z/report.json冻结，尚不能把53/54验证分数当独立测试成绩。新的串行衔接results/p54-flow-20261024T043250Z/report.json，等待旧基线任务释放板卡后，只读认板，再采全新的三组测试源、独立评价、ARM执行及P53候选构建。两个流程不并发占串口。当前实际板卡任务仍以results/p52-active.json为准。

## P54独立测试与P55继续恢复（15:40后）

原300轮基线独立测试results/p52-test-20261024T044224Z/report.json：FP32/INT8均39/54，未通过；完整C前端与Python数值/分类对照通过，失败是模型成绩，不能归咎为采集失败。改进模型在这些结果读取前已冻结，其新测试seed2313～2315均采集、归档和质量检查通过。

改进模型独立测试results/p52-test-20261024T045844Z/report.json通过：INT8 52/54=96.296%，BPSK17/18、QPSK17/18、16QAM18/18；FP32 51/54=94.444%。54帧来自三个未见seed/18个调制DMA块，分组从未随机拆到训练/验证；36次完整C前端检查通过。此成绩仅限记录的受控条件，非54个独立RF会话、非任意信号识别/实测SNR泛化。

最初ARM任务results/p52-ARM-20261024T045846Z/report.json因`decoder did not exit`停止。已定位：新驱动先将PS1置空以解析数值，而旧上传工具必须等非空`#`提示符；上传结束没有提示符，触发误判。旧冻结驱动保持不变，P55部署驱动仅在上传时启用短提示符、其余帧解析仍用空提示符；模型、量化、前端、分类代码和独立测试均未改变。

用户15:40继续后，results/p46-preflight-20261024T074202Z/report.json发现两板均是新boot：新板9734d483-07e3-44d3-9dd3-6582703ee77d，旧板7968dd1d-12b1-4236-8dc1-dae0973d94d8。原RAM记录已因重新上电清空，电脑归档完整。不得将旧boot替换为新boot伪装同次采集。首次P55核验在身份检查即拒绝，无上传/射频操作。

新板因此前归档暂停了P48下次启动，实际从原厂RF方案启动，LO2400MHz/AGC71dB。results/p55-rx-profile-20261024T074852Z/report.json只恢复已验证的RX manual/0dB、LO2450MHz，前后读回通过；未发射、未更换PL、未卸驱动。

results/p52-ARM-20261024T075009Z/report.json正在执行当前ARM上的归档文件计算验证：所有输入在电脑端按原独立测试fixture SHA/长度校验，再压缩上传RAM，解压/逐DMA再次SHA检查，区分`input_origin_boot`和本次执行boot。此项不是新RF采集，也不重新选择模型。原始冻结p52_arm_verify.py保留，执行的是记录了提示符修复和归档上传的新部署驱动。

恢复小屏的衍生启动工具p55_recovery_cycle.py保留原P43全部历史程序/文件校验，并额外绑定本次原厂启动preflight及RX恢复报告。只允许重用同一已验证持久目录，经正常软件重启在空驱动绑定阶段加载合并工程，不做热重装。离线门禁results/p49-migration-preflight-20261024T075316Z/report.json通过，尚未执行重启；需等待ARM上传核对关闭串口。

## P55实际ARM与当前上电后的真实RF/小屏通过（16:11）

results/p52-ARM-20261024T075009Z/report.json最终通过：18个归档完整DMA输入、每种模式54窗口，FP32/INT8的ARM输出均与冻结Python及主机C结果一致。原始RF采集boot为4e7438d3-3e8f-470d-86a5-abf5f732bb71，本次文件推理执行boot为9734d483-07e3-44d3-9dd3-6582703ee77d，两者明确分开。完整mix/FIR/降采样/DC/RMS/三窗口INT8分类耗时均值约22.46～22.55ms/块，最大22.68ms；文件读取不计入，不能当端到端射频延迟。RSS约2.5MiB，未将其解释为整机内存上限。

results/p55-recovery-flow-20261024T075938Z/report.json通过：正常软件重启一次，在空绑定启动阶段重用原安全合并固件，当前新boot cb8e6e0f-12b1-457c-977c-5200abc53683。自主P48接收更新、owned stop、独立idle、时钟寄存器/驱动一致、原始IQ/显存归档、NumPy频谱和显示单位逐像素复核均通过。未热卸载驱动，未声称这次是人工断电实验。原P48持久文件未改，只暂时暂停启动选择用于归档。

随后results/p55-live-flow-20261024T080314Z/report.json完成本次上电环境的部署：新鲜只读认板、完整DMA smoke、校验上传同一peak256/-10dB源包、单音30秒保护发射与两个完整DMA采集、归档后公共IF校准，再构建隔离P53实时AI显示候选。新校准只读单音，不读调制标签/AI成绩；无需改动模型或冻结前端。12项离线生命周期/失败注入与完整C前端对照通过，原P48源码/二进制保留。

results/p53-live-20261024T080707Z/report.json最终通过三类现场试验：每类RX6秒、TX原15秒保护窗口，峰值256、TX-10dB、RX manual0dB。每个UI更新对同一个完整65536样本DMA执行三个1024点AI窗口，并用该DMA前8192样本画频谱。BPSK/QPSK/16QAM最后保存的三个窗口各全部判对，共9/9；这些是当前上电的短时部署示范，不替代之前52/54独立测试成绩，也不代表所有中间窗口均已逐个保存核验。

三类每类的完整最后DMA和800×480显存均SHA/CRC回传；Python重算AI logits/类别与实际ARM一致，显存AI文字逐像素与预测类别、处理时间一致。屏幕输出图为该目录bpsk-screen.png、qpsk-screen.png、qam16-screen.png；这是实际显存导出，不是实屏照片，本轮未取得新的肉眼确认。停止后显示RX STOPPED并保留最后结果，避免把停止画面冒称持续接收。

本轮实现了受控三类真实RF识别、ARM执行及短时实时小屏输出。AI尚未替换P48开机程序；未知/无信号拒识、自动公共IF校准流程固化与十分钟整机AI演示仍待后续验收。旧P201外接UART候选未部署，PL自研FFT/功率谱任务不能由ARM频谱替代。

## 最终保存

权威结果：`results/p52-final-20261024T081254Z/report.json`，状态`passed_controlled_real_RF_AI_and_live_LCD_checkpoint_ready`。

独立测试：`{"fp32": {"frames": 54, "correct": 51, "fraction_correct": 0.9444444444444444, "per_class_fraction_correct": [0.8888888888888888, 1.0, 0.9444444444444444], "confusion_rows_truth_cols_prediction": [[16, 1, 1], [0, 18, 0], [0, 1, 17]]}, "int8": {"frames": 54, "correct": 52, "fraction_correct": 0.9629629629629629, "per_class_fraction_correct": [0.9444444444444444, 0.9444444444444444, 1.0], "confusion_rows_truth_cols_prediction": [[17, 1, 0], [0, 17, 1], [0, 0, 18]]}}`。实际ARM耗时：`[{"source": "bpsk", "mode": "int8", "repeats": 10, "mean_block_ms": 22.5490607, "max_block_ms": 22.680397, "frames_per_block": 3, "maxrss_kib": 2556, "scope": "mix/FIR/decimation/DC/RMS/CNN; file IO excluded"}, {"source": "qpsk", "mode": "int8", "repeats": 10, "mean_block_ms": 22.4626615, "max_block_ms": 22.613716, "frames_per_block": 3, "maxrss_kib": 2612, "scope": "mix/FIR/decimation/DC/RMS/CNN; file IO excluded"}, {"source": "qam16", "mode": "int8", "repeats": 10, "mean_block_ms": 22.4574368, "max_block_ms": 22.57269, "frames_per_block": 3, "maxrss_kib": 2512, "scope": "mix/FIR/decimation/DC/RMS/CNN; file IO excluded"}]`。

恢复原P48持久自启动；最后两板DMA/源/新板启动选择均已读回。串口关闭，板未关机。AI候选未替换持久程序，10分钟整机AI与任意信号拒识仍待验收。
