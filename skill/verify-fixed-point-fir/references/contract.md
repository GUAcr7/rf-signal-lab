# 支持的接口与数值契约

- Verilog模块fixed_fir_iq，参数N_TAPS=1..63、COEFF_FILE可为空。端口clk、rst_n、s_i/s_q、s_valid/s_ready、m_i/m_q、m_sat_i/m_sat_q、m_valid/m_ready与assets模块一致。
- 输入每个I/Q为signed12整数；系数signed18，Q17；36位精确累加；输出signed16，向最近整数舍入，恰好半整数取偶数；独立饱和标志。
- 系数第0项乘当前输入。零初始历史；尾部补N_TAPS-1个零，输出长度input_count+N_TAPS-1。不能每个块都重置而又称连续滤波。
- 本适配器检查有效输出在接受输入后N_TAPS+1周期出现；无暂停时输入间隔N_TAPS+3周期。不同流水线可以复用方法，但应先适配TB，不将时序契约自动放宽。
- case JSON：name为英文标识；coefficients_q17为1..63个整数；samples_iq为非空I/Q整数对，input_count+N_TAPS-1不超过100000。布尔/浮点数/越界数拒绝。
- scripts/verify.py只接受单一DUT文件。多文件IP、AXI封装、其他定点格式和连续不可反压ADC不在直接支持范围。

脚本用Python整数卷积生成完整黄金值与饱和标志，无浮点归一化。TB另含22条直接舍入边界、MAC中复位、阻塞输出时复位、反压保持及重复/漏输出检查；两种暂停模式分别运行。vectors.json为本次精确整数参考，源SHA写入report.json。
