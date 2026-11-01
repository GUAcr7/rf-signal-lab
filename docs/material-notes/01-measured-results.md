# 实测数据与可用于报告的结果

## 1. 独立真实射频识别测试（P52）

旧P201 TX1经原衰减连接到新TLZ7xH RX1A。固定受控条件；三类为BPSK、QPSK、16QAM。54测试帧来自3个未见源seed、18个调制DMA块；分组与训练/验证隔离，同一DMA内的帧不应当作独立RF会话。

| 模型 | 正确/总数 | 受控测试准确率 |
|---|---|---|
| FP32 | 51/54 | 94.444% |
| INT8 | 52/54 | 96.296% |

INT8混淆矩阵，行是真值，列是预测，顺序均为BPSK、QPSK、16QAM：

| 真值 | BPSK | QPSK | 16QAM |
|---|---:|---:|---:|
| BPSK |17|1|0|
| QPSK |0|17|1|
| 16QAM |0|0|18|

原始测试报告：evidence/results/p52-test-20261024T045844Z/report.json；同目录fixtures/有18份真实I/Q二进制。原始SHA已逐份复核。evaluation.npz及C输出均保留。冻结模型在evidence/results/p52-trained-20261024T042912Z/，导出代码在p52-export-20261024T043113Z/。

注意：后续P74增加相位池策略，所以96.296%只能署给上述冻结P52测试流程，不能直接移作当前整个策略的新独立准确率。

## 2. 实际ARM执行与持续演示

- P52归档真实RF输入在实际ARM执行，完整mix/FIR/抽取/DC/RMS/CNN三窗口链均值约22.46–22.55ms/块，最大22.68ms；不含文件读取。这是归档数据板端运算，不是该次新RF采集或端到端延迟。证据p52-ARM-20261024T075009Z/。
- P76持续演示666.488秒、1153次更新，最大更新间隔0.857秒。稳定BPSK/QPSK/16QAM各40/40接受且正确，单音0/17接受。属于固定演示窗口，不是新独立测试。
- P81人工触屏完整彩排：479.668秒、802次更新；三种调制自然结束及真实RUNNING中STOP都有日志。4个自然结束窗口各16/16接受且正确。
- P81串口按键帧到目标状态读回：APPLY中位3.590秒（n=5、最大6.646），START中位5.350秒（n=5、最大7.062），STOP2.442秒（n=1）。不包括手指触摸至串口发帧时间。

证据分别见evidence/results/p76-review-20261026T124554Z/、p81-final-20261027T142631Z/，原始P81历史、最后I/Q与显存在p59-p79-session-archive-20261027T142252005759Z/files/。measured-data/summary.json便于取数。

## 3. 屏幕物理参数数据如何使用

P81 metrics-history.jsonl保存逐次参数，AI历史另存ai-history.jsonl；按source_block_sequence对应。采样率30.72MS/s，1024点显示FFT频点间隔30kHz，LO2450MHz。只用valid=true的记录计算统计；停止/校准不足时的null不可填成0。六条有效样例已提取到measured-data/p81-valid-metric-examples.json。

LO+center为接收LO加区域中心估计，99% ROI BW为限定区域累计能量带宽，ROI power为数字counts²，相对背景功率为该区域相对背景参考的比值。它们没有绝对RF频率/功率仪器校准，不能写成校准dBm、严格SNR或标准全频段占用带宽。

## 4. 资源/时序数据

当前安全合并设计P37的Vivado布线原表包含LUT21831、FF38376，WNS+0.352ns、WHS+0.036ns。依据evidence/results/p37-safe-route-20261021T084904Z/的utilization.rpt、timing.rpt。对象是XC7Z100合并工程，不是独立FIR或CNN资源。58项CDC Critical及外部延迟缺项仍开放；不能写成所有CDC/外部时序签核完成。
