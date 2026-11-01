"""Host-only, evidence-preserving cross-device writing handoff. Never opens hardware."""
from __future__ import annotations

from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import shutil
from zipfile import ZipFile, ZIP_DEFLATED

ROOT=Path(__file__).resolve().parents[1]

def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()

def write(path: Path, text: str):
    path.parent.mkdir(parents=True,exist_ok=True)
    path.write_text(text.strip()+'\n',encoding='utf-8')

README='''
# 跨设备项目写作资料包

本包用于在另一台电脑的 AI 中撰写项目总结、设计报告、演示讲稿和答辩材料。
它是当前文件与证据的离线快照，不是完整聊天记录导出，也不自动同步对话记忆。

## 最快使用方法

1. 解压整个 ZIP。
2. 有本地文件访问能力的 AI：将解压目录作为工作目录，把 `01-完整交接提示词.md` 的全部内容发给它。
3. 普通网页聊天：先上传本目录 00～04 的 Markdown 文件及 `project/docs/screen-fields-20261028.md`；按需要再上传证据表中的具体文档/图片。不要假定网页 AI 能看到你电脑上的路径。
4. 初次写文章，先读 `02-项目事实与完成情况.md`、`03-结论与证据索引.md`，再沿索引核验原始报告。

`project/` 保留原 rf-signal-lab 项目的目录层级。原文件通常写 `results/...` 或 `docs/...`，均从这个 project 目录解析。历史绝对路径 C:/Users/project_user/... 是原机器路径，换机后应映射到 project，不能据此说本包缺文件。

## 内容

- 01：可直接发给另一位 AI 的完整指令。
- 02：硬件、数据流、功能、指标、当前状态和限制。
- 03：关键结论对应的实验/JSON/图片路径。
- 04：文章建议结构与准确表述。
- project/docs：现有全部实验记录、交接、设计说明、教程和视频稿。
- project/src、host、embedded、board、configs、experiments、tests、fpga：代码及配置快照，包含历史版本，须按最新证据选择当前版本。
- project/results：历史 JSON 报告、文本/测试报告/历史数据、绘图，以及精选的完整原始证据、模型、安装快照和部分小型检查点。results 在原仓库被 gitignore 排除，本包从真实文件系统收集。
- manifest.json：逐文件字节数、SHA256与来源。
- omitted-files.json：未纳入的大型原始/重复构建产物，含路径、大小、原因。未纳入不代表原机器没有。

## 边界

这是写作与核验包，不是全量系统迁移或一键烧录包。未携带 Vivado/Vitis 安装器、许可证、.venv、浏览器账户配置、D:/AD9361 完整厂商资料、全部多GB旧检查点或全部ADC原始数据。源码与报告并不等于新电脑可以立即操作板卡。

本包不包含完整原始对话导出，也没有已经交付的手机演示视频。已整理的提示词/事实说明、实验记录、实际反馈和实屏照片可用于恢复项目背景。

禁止根据记录的旧状态认为板卡现在仍在运行。P85人工服务已结束；它的三类发射任务成功记录仍不能替代未归档的完整RX验收。硬件相关动作必须另行核对、单一操作者执行。
'''

PROMPT='''
# 给另一台设备 AI 的完整项目交接提示词

你现在担任本项目的总结文章、技术报告与答辩材料助手。请先读取我提供的资料包，建立准确的项目上下文，再进行写作。我是一名学过DSP、信号与系统的大三学生，文字要专业、易懂，避免堆砌术语。

## 本轮目标

主要依据已有证据，帮助我完成本项目的成果总结、设计报告、原理说明、视频解说、答辩问题及后续规划。暂不操作板卡、不运行发射/烧录/串口程序、不修改工程，也不重复整个开发流程。需要新的实验时只列出必要测量及用途。

先按以下顺序读取：
1. 本包 `00-使用说明.md`、`02-项目事实与完成情况.md`、`03-结论与证据索引.md`、`04-文章结构与表述建议.md`。
2. `project/START-HERE.md`。它保留大量时间顺序历史条目，阅读最上方状态与后续修订，不把早期障碍当作最新结论。
3. `project/docs/handoff/RESUME-P81-20261027.md`、`project/docs/experiments/EXP-P81-manual-screen-rehearsal-20261027.md`、`project/docs/experiments/EXP-P85-demo-resume-20261028.md`。
4. 需要AI细节时读 P52、P74、P75、P76 的实验记录及 evidence map 对应原始报告；需要显示/指标细节时读 P67/P69、screen-fields；需要演示时读 demo-video-script。
5. 需要原理与实现支撑，再查看 src/、embedded/、host/、fpga/ 与构建/验收报告。不要一次性读完所有历史日志。

## 已知项目背景

参赛：2026 FPGA创新设计竞赛，AMD/Xilinx自主选题。报名组别和最终评分细则并未全部确认，以包内用户提供的AMD选题指南及最新通知为准。

方案：旧P201作为可切换调制的射频发送端，新TLZ7xH-EVM作为接收分析/显示端；旧板TX1通过既有衰减连接与同轴线接新板RX1A。当前是受控有线真实RF验证，不是仿真文件回放；当前不含频谱仪量值对照、TX2镜像输出和空间任意信号验证。

硬件：旧板为璞致PUZHI PZSDR P201系列，项目目标XC7Z020/Zynq-7020，搭配AD9361。新板为创龙Tronlong TLZ7xH-EVM，本项目实际使用XC7Z100/Zynq-7100，配AD9361 FMC射频模块及7英寸800×480显示屏（背板TL-70RESLCD-R2）。旧板控制小屏为淘晶驰TJC4827T143_011C、4.3英寸480×272。不要从P201系列名称推测未确认Mini/Pro型号或封装后缀。

Zynq包含双核ARM Cortex-A9的PS与可编程逻辑PL。当前PL承担已实现的高速数字接口、数据搬运和显示相关通路；FFT、参数估计、轻量CNN推理在接收板ARM软件运行。PC负责淘晶驰屏到旧板的控制中转、恢复和校准，不能写成当前整机完全脱离电脑或CNN已经在FPGA硬件加速。

## 写作必须遵守的事实边界

- 当前支持受控BPSK、QPSK、16QAM三类；TONE用于参考校准，不是第四个已训练AI类别。
- 屏幕有I/Q时域、数字频谱、瀑布图、限定ROI参数和AI结果。采样率30.72MS/s，显示FFT1024点，频点间隔30kHz；这不是每秒显示30.72M帧。
- LO+center是接收本振加ROI中心偏移的频率估计；Center offset是相对本振的偏移，不自动等于发射频率误差。
- 99% ROI BW为限定分析区域内累计能量0.5%～99.5%区间宽度，不能不加限定称为已经按标准仪器标定的全信号占用带宽。
- ROI power用counts²；Above background为相同配置下当前与背景参考ROI数字功率的dB比，不是dBm、绝对射频功率或已标定SNR。
- 瀑布图按实际显示快照排列，ADC块间隙未知；UI skipped不是已经测得的ADC丢样率。不能写成无丢样连续接收。
- AI屏上耗时需依据相应计时范围，不能把完整前端/策略时间说成纯CNN单次推理或端到端延迟。
- P52原冻结推理的独立受控真实RF测试：INT8 52/54，约96.3%，样本很小且同设备/固定条件；不是所有场景通用准确率。
- P74/P75后来增加固定8相位logits平均与三帧一致性，P76部署。属于推理算法变更，不能把P52的52/54直接标作新版的独立测试准确率。新版本的40/40等是特定真实RF演示回归，不是全环境100%准确率。
- P81完成真实人工三类切换、自动结束、RUNNING中STOP及完整RX数据复核。P83/P84/P85是不同轮次，部分覆盖或未归档不能覆盖P81成功，也不能冒称这些轮次全部验收通过。
- 新板真正断电后的自主接收/显示启动已验收；不等于旧板源包和屏控服务也已持久化或完全离线。
- 当前仍依赖本地电脑；通常不需要互联网来运行演示，但不能把断网与脱离电脑混为一谈。
- 不使用早期FMQL30TAI/Icraft/NPU方案作为现实现，避免被原工作目录名称误导。现平台是Zynq/ARM/AD9361。
- 厂商IP、开源复用、自研代码与AI协作应分别说明，不夸大原创范围。

## 输出要求

收到本提示词后先给出简洁的项目理解、已完成成果与重要限制，再按我指定文体写作；若我没有指定，先写一篇约2000字的中文工程总结初稿，题目可用《基于Zynq与AD9361的射频信号分析及轻量化调制识别系统》。按背景目标、总体方案、收发链、可视化与参数、AI、软硬件联调、实测结果、问题与改进、总结组织。

正文用易读自然语言解释原理，必要时用简短公式和表格，不把实验流水账全部搬入正文。成果、计划、推测、历史失败需清楚区分。

每项重要数字/验收结论提供本包内可核验的相对路径；引用现场图片时说明是实屏照片还是显存/离线图。若只有历史截图，不能标成新测量。文章附一份“可直接采用的结论”和“待测/不宜夸大”的核对表。

不要虚构新的性能、资源占用、帧率、SNR范围、精度、功耗、外场覆盖、仪器测量、训练样本数量或竞赛得分。文件缺失先查 manifest/omitted-files；无法核验的地方注明待核实，不要求我重新抄已有内容。

资料包不是完整聊天记忆，未包含的口头反馈、数据、视频不能自行补全。若资料冲突，依实际原始证据、验收范围和后续明确修订判断，不简单按文件名最大阶段号判定全部通过。
'''

BRIEF='''
# 项目事实、完成情况与文章可用数据

快照日期：2026-10-28。以下是现有记录的整理，不是新一轮性能测量。

## 目标与系统组成

实现真实RF采集、I/Q时域/频谱/瀑布图显示、限定区域中心频率与能量带宽/相对功率估计，以及支持三类通信调制的轻量模型识别。旧板可受屏幕控制切换信号；新板在真实采集数据上计算和显示。

|部件|实际配置/职责|
|---|---|
|发送板|璞致PUZHI PZSDR P201系列，项目XC7Z020/Zynq-7020，AD9361；产生TONE/BPSK/QPSK/16QAM，原生限时与主动停止保护|
|接收板|创龙Tronlong TLZ7xH-EVM，实际XC7Z100/Zynq-7100，AD9361 FMC模块；采集、ARM分析/识别、显示|
|接收显示|7英寸800×480，背板TL-70RESLCD-R2；I/Q、频谱、瀑布图、参数及AI|
|发送控制屏|淘晶驰TJC4827T143_011C，4.3英寸480×272，串口按钮与状态|
|电脑|屏幕USB-TTL中转、控制源端、恢复、背景和单音校准、证据归档|
|链路|旧TX1 → 原衰减连接/同轴 → 新RX1A；TX2及频谱仪本次不使用|

两块Zynq都采用ARM PS + FPGA PL结构。不要将PS软件运行的FFT/CNN描述为已部署的PL算法加速器。配套FMC方案记录涉及AD-FMCOMMS3-EBZ，但不能据此虚构模块实物厂家/完整料号。

## 数据链与实现重点

源端已校验波形 → AD9361发射 → 有线衰减链 → 接收AD9361下变频与采样 → 数字接口/DMA → ARM软件前端/FFT/参数/识别 → 同源块结果绘制到LCD。电脑不承担当前新板的CNN推理。

发送控制：选择类别/时长→APPLY检查→READY→START→RUNNING→自然结束或STOP→清理→IDLE。默认15秒，时长以5秒步进、限制8～60秒；变更选择后要重新APPLY。RUNNING必须有原生任务提交证据，停止用任务身份/截止时间/清理读回，不仅改变界面文字。

原USB串口后台会话不可靠的问题通过已核同型号/boot的同USB网络非交互任务通道规避；这是有效工程规避方案，不能说底层串口问题根因完全根治。

## 主要配置

|参数|本受控演示配置/解释|
|---|---|
|接收采样率Fs|30.72MS/s|
|本振LO|2450MHz|
|RF滤波带宽|18MHz，与显示的99% ROI能量宽度不是同一指标|
|显示FFT长度|1024，频点间隔Fs/N=30kHz|
|源端基带偏移|+960kHz标称；两板独立本振可能产生实际偏移|
|调制符号率|240ksym/s，成形RRC滚降0.35|
|发射/接收增益|演示通常TX -10dB、RX manual 0dB；以当轮报告为准|
|源数据峰值|I/Q分量峰值256 counts，不等于射频输出dBm|

## 界面数据怎样解释

- 左上：最前64个I/Q样本的时域片段，I蓝色、Q橙色，单位counts。它们是下变频基带I/Q，不是直接显示2.45GHz波形。
- 右上：频谱，横轴相对LO的频率偏移，当前为每bin数字谱功率，不能误写成已标定dBm/Hz。
- 左下：多次显示频谱快照形成的瀑布图，旧在上、新在下，固定颜色范围；不能把行号称为连续ADC时间。
- 右下：受控单源限定ROI，Fs、bin、VALID状态、LO+center、99% ROI BW、Center offset、ROI power、Above background。
- LO+center = LO + ROI中心偏移。照片2450.997MHz及+996.7kHz仅是该时刻示例，不是系统固定精度或误差。
- 99% ROI BW：ROI累计功率0.5%至99.5%分位的频率差。照片308.6kHz是一次示例，不是所有调制恒定值。
- Above background = 10log10(P_ROI/P_background)，同增益/配置时用于判断输入相对背景增强和支持信号有效性门控。照片+57.5dB不是校准SNR。
- AI区：当前接受类别或无信号/不确定/待校准等状态；显示处理链耗时。照片85.7ms不是纯CNN或端到端实时吞吐率。
- update/source block为显示更新/源块身份；UI skipped为未绘制的旧块，不是ADC丢样计数。

## AI与实测结论

P52：真实RF数据按源seed组隔离，训练108帧、验证54帧；同DMA片段不能当多个独立实验。115参数Conv8轻量CNN，DC/RMS及前端处理，导出C/ARM与INT8数值对照。模型通过验证选择后再采新测试seed，54测试帧；原冻结INT8结果52/54≈96.3%，FP32 51/54。小样本、固定设备条件，不是大范围外场成绩。

后续P74：针对实际不确定块的相位敏感性，固定8相位旋转分别推理并平均logits；仍要求三帧分类一致。未改变原模型权重。这是新的推理算法，原独立52/54不能自动移植为其独立成绩。P75早期16QAM有2/65不确定，记录保留。

P76演示回归：同次自主接收会话666.487863秒、1153次更新，三类稳定窗口各40/40接受且正确；单音0/17接受。是特定演示回归，不是通用100%识别率。

P77：用户真实断电后的自主启动、实屏亮起和动态更新确认通过。与P76普通重启/十一分钟测试分别保留证据。

P81：实屏人工BPSK、QPSK、16QAM切换、自然结束、RUNNING中STOP通过；802次更新、479.668秒，完整历史/FFT/RMS/停止显存及资源释放复核。人工操作回显中位APPLY 3.590秒、START 5.350秒、STOP 2.442秒（STOP仅1个样本）；不能以中位值保证每次固定时延。

## 最新轮次状态，不与历史验收混合

P83只收到BPSK完整演示，已完整归档；P84只收到QPSK，完整RX归档因USB缺失未完成，后来新boot导致RAM历史丢失，主机日志和实屏照片保留。

P85重新接线后，识别COM5旧板/COM9新板/COM11小屏，仅对本轮拓扑有效。源程序恢复、背景、单音校准通过。人工服务最终为partial且serial_closed=true：实际有BPSK、QPSK、16QAM及额外QPSK自然结束任务成功；未记录主动STOP，完整RX历史尚未归档。不以该日志宣称本轮全量复核；也不否定P81既有完整验收。当前硬件实时状态未在写作打包中重新测量。

## 仍需完善/不能夸大的内容

- 整机PC-free：未完成；旧小屏经电脑USB-TTL控制，板间直连UART与旧源端开机持久控制待做。
- TX2同信号镜像与频谱仪对照：未完成，本轮已按用户要求暂缓。
- 空间天线信号/未知调制/多信号识别：未验收。现有结论限有线受控三类。
- 绝对功率dBm、标准占用带宽仪器精度、无丢样持续吞吐：未证明。
- 新8相位策略的全新独立准确率：未重新测得；保留原算法的独立结果与新版演示回归两种范围。
- 最终赛事资源/性能/可复现提交、自研与复用、AI协作说明、海报及手机演示视频：按最终交付清单补齐，不能说本包已替代所有比赛提交。

## 重要工程问题及处理

1. 新板LCD/RF硬件工程并存、像素时钟32位计算溢出等问题：以P35/P37至P43真实工程和验收追溯。原始不安全时钟候选已退休，当前约33MHz安全配置，不热卸载ADC驱动。
2. 自动休眠导致黑屏：完成背光与桌面休眠处理及真实断电/长时间动态观察，证据见相应实验，不以软件计数代替人眼确认。
3. 四通道IIO按二通道误解析：改为I1/Q1/I2/Q2真实扫描格式；错误版本保留用于反例，不沿用旧错误结论。
4. 相位敏感/早晚16QAM不确定：同块捕获与固定相位汇总，实际改善；不能宣称任意条件下完全根治。
5. USB串口编号/拓扑变化：按设备身份、Linux型号、boot、配置SHA和真实TJC序列号绑定，不能死写COM号码。
6. 按钮响应慢：保留核验，批量读取状态与预部署辅助；实测等待缩短，尚非毫秒级发射切换。
'''

EVIDENCE='''
# 结论与证据索引

以下所有路径从本包 `project/` 起算。先读人类可读的实验记录，再核JSON。manifest保证的是快照文件一致性，不代替科学验收。历史报告中提到的未打包大文件见 omitted-files，不把缺文件当原实验失败。

|要写的内容|首选文档/报告|
|---|---|
|当前工程与历史纠错|START-HERE.md；docs/WORKFLOW-NEXT-20261024.md；docs/experiments/EXP-P85-demo-resume-20261028.md|
|真实RF训练/独立测试|docs/experiments/EXP-P52-real-RF-AI.md；results/p52-final-20261024T081254Z/report.json；results/p52-test-20261024T045844Z/report.json|
|当前权重/导出|results/p52-trained-20261024T042912Z/；results/p52-export-20261024T043113Z/|
|相位策略与限制|docs/experiments/EXP-P74-phase-pool-20261026.md；docs/experiments/EXP-P75-live-phase-pool-20261026.md；results/p74-offline-20261026T094450Z/report.json|
|新版持久接收/十一分钟回归|docs/experiments/EXP-P76-persistent-demo-20261026.md；results/p76-review-20261026T124554Z/report.json；results/p76-boot-20261026T123208Z/report.json|
|真实断电与实屏反馈|docs/handoff/RESUME-P77-20261026.md；results/p77-final-20261026T130128Z/acceptance.json；results/p77-user-power-cycle-20261026.json|
|人工三类+STOP完整验收|docs/experiments/EXP-P81-manual-screen-rehearsal-20261027.md；results/p81-final-20261027T142631Z/report.json；results/p79-review-20261027T142421Z/report.json|
|P81原始按键/全RX证据|results/p80-screen-control-20261027T141654Z/；results/p59-p79-session-archive-20261027T142252005759Z/|
|控制提速与等待|docs/experiments/EXP-P80-screen-latency-20261027.md；results/p80-final-20261027T140528Z/report.json；P81 latency字段|
|四区与指标含义|docs/screen-fields-20261028.md；docs/experiments/EXP-P67-RX-dashboard-20261026.md；docs/experiments/EXP-P69-ROI-metrics-20261026.md（如名称不符按docs索引检索）|
|P83部分演示及复核|results/p83-final-20261028T113405Z/report.json；results/p83-review-20261028T113315Z/report.json|
|P84实际实屏照片|results/p84-demo-20261028T115853Z/screen-photos/rx-screen-user-photo.jpg；同目录tx-screen-user-photo.jpg。照片只支持可见画面，不证明全部三类或STOP|
|P85最新部分演示|results/p80-screen-control-20261028T134008Z/report.json；本包05-P85状态快照.json；对应原始任务报告|
|USB身份恢复|results/p59-p78-screen-preflight-20261028T133432201529Z/report.json；experiments/p85_topology_preflight.py|
|作品视频稿|docs/demo-video-script-20261028.md；docs/demo-visual-20261028.md，注意其中旧P83状态注释为历史|
|竞赛指南与判断范围|docs/design/contest-scope-20261028.md；results/contest-rules-20261028/amd-2026-user-provided.pdf|
|自研/复用/AI协作|docs/ai-assistance.md；fpga/vendor-baseline/；相关实验与源文件|

## 当前实现检索路线

- 板端显示与处理：embedded/arm_live_panel_p69/、arm_live_panel_p74/、相应P75构建快照；当前实际组合以P76安装证书 files 与SHA为准，不以旧目录名当最终版本。
- 小屏协议：src/rfsig/source_screen.py、host/source_screen_link.py。
- 实屏RF控制与提速：host/source_screen_rf.py、host/fast_panel_control.py。
- 固定板控/身份/会话：host/board_control.py、src/rfsig/board_session.py、configs/receiver-profile.json。
- 本地USB网络任务：host/p201_usb_network.py、board/source-job.sh、embedded/arm_tx_source/。
- AI前端/训练/导出：experiments/p52*及p74*文件、冻结的P52导出与P75实际构建。历史tiny_cnn_probe注释可能指早期合成训练版，不代表最终模型的数据来源。
- FPGA/器件/显示时钟：fpga/、相关results中的构建rpt/tcl/hdl文本与P37/P43记录；大型DCP/完整Vivado临时目录未全部携带。

包内保留很多失败/旧候选，尤其P51诊断、最初300轮模型、未修正通道格式、P35旧时钟等。引用时需要写明阶段和后续修复，不能把失败候选当现实现，也不要删除其历史。
'''

OUTLINE='''
# 总结文章建议结构与准确表述

## 约2000～3000字工程总结

1. 背景与需求：射频教学/受控通信信号观察，三项功能目标；说明使用真实RF而非仅模拟回放。
2. 总体架构：双Zynq/AD9361收发，PS/PL/PC分工，控制屏和显示屏分别承担什么。
3. 发射源：可切换BPSK/QPSK/16QAM、RRC成形、限时发送、主动停止、受控同轴衰减链。
4. 接收与可视化：IIO/DMA格式、同源数据块、FFT、I/Q与瀑布图，显示快照与ADC连续性区别。
5. 参数估计：Fs/N、LO+ROI中心、99% ROI能量带宽、counts²与背景功率比，写明分析区域和量纲。
6. AI实现：数据按组划分、轻量CNN/INT8/C移植、原算法独立小样本测试、后来固定相位汇总与拒判策略。
7. 工程难点：LCD与RF共存、时钟与启动、四通道解析、相位不确定、USB后台任务、屏控响应；每项写问题→证据→处理→仍有限制。
8. 测试结果表：独立52/54、P76十一分钟回归、P77真断电、P81人工三类/STOP与按键延时，严格分列测试范围。
9. 局限与后续：电脑直连控制迁移、源端持久化、仪器量值对照、外场/未知类、多信号、实际PL算法加速（均为后续）。
10. 个人/团队收获：嵌入式调试、DSP参数解释、模型数据隔离、证据链、软硬件协同；作者贡献让用户补充，不虚构分工比例。

## 可直接使用的简介

本设计基于Zynq异构平台与AD9361射频收发芯片，构建可切换调制信号的发送端和集采集、分析、显示于一体的接收端。系统利用FPGA完成已实现的高速数字接口、数据搬运及显示相关通路，在ARM侧实现I/Q时域、频谱与瀑布图展示，以及限定分析区域的中心频率、99%能量带宽和相对背景功率估计；采用轻量化模型完成当前支持的BPSK、QPSK、16QAM调制识别。系统已完成受控有线真实射频链路和触摸屏启停联动验证，可用于射频教学和信号分析实验，后续可向独立运行与空间射频监测扩展。

## 用词对照

|建议写|避免写|
|---|---|
|当前支持三类的受控有线真实RF演示|任意环境任意射频信号均可识别|
|新板ARM运行FFT/参数/CNN，PL负责已实现的数据与显示通路|已实现FPGA并行FFT和CNN硬件加速|
|原冻结INT8推理在54帧独立受控RF测试中52帧正确|新版算法通用准确率96.3%或100%|
|特定演示回归三类各40/40接受正确|系统所有信号识别率100%|
|限定ROI的99%能量宽度，数字相对功率|已标定标准OBW、dBm、SNR|
|自主启动接收显示，屏控仍需本地电脑|整机已完全脱离电脑|
|显示快照持续更新，ADC间隙未知|30.72M帧/秒显示、连续无丢样|
|实际照片中的一次读数|设备标称精度或所有工况固定参数|

## 文章配图建议

- 实物全景：两板、两个屏、衰减链和电脑，应由用户补充清晰照片；包内已有LCD实拍可先用。
- 系统框图：根据真实链路和PS/PL/PC分工绘制，标注是示意图。
- 四区实屏照片与字段说明：使用已保存P84照片，遮挡的AI文字不能猜。
- AI测试混淆矩阵：根据P52最终测试JSON原值重绘，标明原算法、n=54、固定受控条件。
- 响应时延表：引用P81实际样本数和中位/最大值，STOP仅1样本。
- 计划中的分路器/天线/PL加速若绘出，用虚线注明未实现。
'''

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    # A short staging root avoids MAX_PATH on this Windows host. The original
    # repository path is already long; nested copies there are not portable.
    export=Path.home()/'Downloads'/('rf-write-'+stamp)
    package=export/'rf-project'
    package.mkdir(parents=True)
    for name, text in [('00-使用说明.md',README),('01-完整交接提示词.md',PROMPT),
                       ('02-项目事实与完成情况.md',BRIEF),('03-结论与证据索引.md',EVIDENCE),
                       ('04-文章结构与表述建议.md',OUTLINE)]:
        write(package/name,text)

    current=ROOT/'results/p80-screen-control-20261028T134008Z/report.json'
    latest=json.loads(current.read_text(encoding='utf-8'))
    jobs=[{k:j.get(k) for k in ('kind','passed','signal','cancelled','report','report_sha256','cancel_reason')}
          for j in latest.get('jobs',[])]
    completed=sorted({j['signal'] for j in jobs if j['kind']=='run' and j['passed'] and not j['cancelled']})
    stop=any(j['kind']=='run' and j['passed'] and j['cancelled'] and j['cancel_reason']=='stop' for j in jobs)
    snapshot={'snapshot_utc':datetime.now(timezone.utc).isoformat(),'source':current.relative_to(ROOT).as_posix(),
              'source_sha256':sha(current),'status':latest['status'],'serial_closed':latest['serial_closed'],
              'completed_natural_TX_signals':completed,'actual_STOP_recorded':stop,'jobs':jobs,
              'full_RX_archive_for_this_round':False,'hardware_reinspected_by_packager':False,
              'note':'Host-side snapshot only. Successful TX jobs do not replace complete RX history review. P81 remains the full human acceptance evidence.'}
    write(package/'05-P85状态快照.json',json.dumps(snapshot,ensure_ascii=False,indent=2))

    candidates=set()
    omitted=[]
    skip_parts={'__pycache__','.pytest_cache','.git','.venv','.Xil'}
    for folder in ('docs','src','host','board','embedded','configs','experiments','tests','fpga'):
        for p in (ROOT/folder).rglob('*'):
            if p.is_file() and not skip_parts.intersection(p.relative_to(ROOT).parts) and p.suffix.lower() not in {'.pyc','.pyo'}:
                candidates.add(p)
    for p in ROOT.iterdir():
        if p.is_file() and p.suffix.lower() in {'.md','.json','.toml','.ini','.txt','.in','.cmd'}:
            candidates.add(p)

    # Full report/text/plot timeline, including failed experiments, collected from disk.
    text_ext={'.json','.jsonl','.md','.txt','.csv','.xml','.svg','.py','.c','.h','.sh','.in','.tcl',
              '.xdc','.v','.sv','.dts','.dtsi','.rpt','.HMI'.lower(),'.tft','.png','.jpg','.jpeg'}
    selected_folders=[
        'p52-trained-20261024T042912Z','p52-dataset-20261024T042524Z',
        'p52-export-20261024T043113Z','p52-test-20261024T045844Z',
        'p74-offline-20261026T094450Z','p74-native-20261026T094712Z',
        'p75-build-20261026T100057Z','p76-boot-20261026T123208Z',
        'p76-review-20261026T124554Z','p76-final-20261026T125153Z',
        'p77-final-20261026T130128Z','p80-final-20261027T140528Z','p81-final-20261027T142631Z',
        'p83-final-20261028T113405Z','p80-screen-control-20261027T141654Z',
        'p59-p79-session-archive-20261027T142252005759Z','p79-review-20261027T142421Z',
        'p80-screen-control-20261028T111832Z','p83-review-20261028T113315Z',
        'p80-screen-control-20261028T120101Z','p84-demo-20261028T115853Z',
        'p80-screen-control-20261028T134008Z','p85-demo-20261028T134008Z',
        'p59-p78-screen-preflight-20261028T133432201529Z',
        'contest-rules-20261028']
    full=set(selected_folders)
    for p in (ROOT/'results').rglob('*'):
        if not p.is_file() or skip_parts.intersection(p.relative_to(ROOT).parts):
            continue
        rel=p.relative_to(ROOT)
        size=p.stat().st_size
        explicit=rel.parts[1] in full
        # Selected raw evidence is small; avoid shipping large repeated legacy checkpoints.
        include=(explicit and size<=30*1048576) or (p.suffix.lower() in text_ext and size<=16*1048576)
        if include:
            candidates.add(p)
        else:
            omitted.append({'path':rel.as_posix(),'bytes':size,
                            'reason':'large/duplicate build or raw artifact outside selected writing-evidence subset'})

    # Keep this writeup-oriented selection deterministic and traceable.
    for p in sorted(candidates,key=lambda p:p.as_posix()):
        target=package/'project'/p.relative_to(ROOT)
        target.parent.mkdir(parents=True,exist_ok=True)
        shutil.copy2(p,target)

    # Known teammate documents are useful originals and were already supplied by the user.
    for name in ('P67-实屏验收记录-20261026.docx','P67-联调对接说明-20261026.docx'):
        original=Path.home()/'Downloads'/name
        if original.is_file():
            target=package/'attachments'/name
            target.parent.mkdir(parents=True,exist_ok=True)
            shutil.copy2(original,target)

    write(package/'omitted-files.json',json.dumps({'scope':'writing handoff, not complete runnable restore',
          'omitted_results':omitted,'not_copied_directories':['.venv','.git','.Xil','tmp','data full synthetic collections','old duplicate export archives'],
          'external_vendor_material_not_copied':'D:/AD9361 and tools/installers/licenses are not included'},ensure_ascii=False,indent=2))

    # Resolve evidence table with actual filenames instead of allowing a stale naming guess.
    evidence_file=package/'03-结论与证据索引.md'
    evidence_text=evidence_file.read_text(encoding='utf-8')
    matches=list((package/'project/docs/experiments').glob('EXP-P69*'))
    if len(matches)==1:
        evidence_text=evidence_text.replace('docs/experiments/EXP-P69-ROI-metrics-20261026.md（如名称不符按docs索引检索）',
                                           matches[0].relative_to(package/'project').as_posix())
        write(evidence_file,evidence_text)

    manifest=[]
    for p in sorted(package.rglob('*')):
        if p.is_file():
            rel=p.relative_to(package).as_posix()
            manifest.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha(p),
                             'source_kind':'original_project_snapshot' if rel.startswith('project/') else
                                           'user_supplied_document' if rel.startswith('attachments/') else 'new_handoff_summary'})
    manifest_path=package/'manifest.json'
    write(manifest_path,json.dumps({'schema':'rfsig.writing_bundle.v1','created_utc':datetime.now(timezone.utc).isoformat(),
          'original_project_root':str(ROOT),'purpose':'Cross-device article writing with verifiable evidence; no hardware operations',
          'files':manifest},ensure_ascii=False,indent=2))
    # START-HERE contains historical live-state notes. Prefix a snapshot notice
    # in the COPY only, preserving the original bytes in the working project.
    start=package/'project/START-HERE.md'
    old_start=start.read_text(encoding='utf-8')
    write(start,'# 写作包状态提示\n\n本包仅用于写作。P85服务已结束，实际状态见包根目录05-P85状态快照.json；下方“已就绪等待人工”等是历史，不能用于判断硬件现状。P81完整验收保留。原文件SHA见旁附快照元数据。\n\n'+old_start)
    write(package/'source-state.json',json.dumps({'START_HERE_original_sha256':sha(ROOT/'START-HERE.md'),
          'copied_START_HERE_has_added_historical_state_notice':True,'hardware_not_accessed':True},indent=2))
    # The two additions above must be included in the final member manifest.
    manifest=[]
    for p in sorted(package.rglob('*')):
        if p.is_file() and p.name!='manifest.json':
            rel=p.relative_to(package).as_posix()
            manifest.append({'path':rel,'bytes':p.stat().st_size,'sha256':sha(p),
                             'source_kind':'original_project_snapshot_with_status_notice' if rel=='project/START-HERE.md' else
                                           'original_project_snapshot' if rel.startswith('project/') else
                                           'user_supplied_document' if rel.startswith('attachments/') else 'new_handoff_summary'})
    write(manifest_path,json.dumps({'schema':'rfsig.writing_bundle.v1','created_utc':datetime.now(timezone.utc).isoformat(),
          'original_project_root':str(ROOT),'purpose':'Cross-device article writing with verifiable evidence; no hardware operations',
          'files':manifest},ensure_ascii=False,indent=2))
    zip_path=export/('rf-signal-lab-writing-'+stamp+'.zip')
    with ZipFile(zip_path,'w',ZIP_DEFLATED,compresslevel=6) as z:
        for p in sorted(package.rglob('*')):
            if p.is_file(): z.write(p,p.relative_to(export).as_posix())
    print('ZIP_CREATED',zip_path,flush=True)
    with ZipFile(zip_path) as z:
        names=z.namelist()
        if len(names)!=len(set(names)):
            raise ValueError('Duplicate archive entries')
        if z.testzip() is not None:
            raise ValueError('Archive CRC failed')
        for item in manifest:
            data=z.read(package.name+'/'+item['path'])
            if len(data)!=item['bytes'] or hashlib.sha256(data).hexdigest()!=item['sha256']:
                raise ValueError('Archive member mismatch: '+item['path'])
    downloads=Path.home()/'Downloads'/zip_path.name
    shutil.copy2(zip_path,downloads)
    if sha(downloads)!=sha(zip_path): raise ValueError('Downloads copy differs')
    result={'status':'passed_P86_writing_bundle_crc_all_members_sha_verified','zip':str(downloads),
            'working_copy':str(zip_path),'folder':str(package),'bytes':downloads.stat().st_size,
            'sha256':sha(downloads),'files_in_zip':len(names),'manifest_files':len(manifest),
            'omitted_result_files':len(omitted),'hardware_operations':False,
            'full_conversation_export':False,'full_runnable_migration':False,
            'P85_snapshot':snapshot}
    write(export/'report.json',json.dumps(result,ensure_ascii=False,indent=2))
    print(json.dumps({k:result[k] for k in ('status','zip','bytes','sha256','files_in_zip')},ensure_ascii=False),flush=True)


if __name__=='__main__':
    main()
