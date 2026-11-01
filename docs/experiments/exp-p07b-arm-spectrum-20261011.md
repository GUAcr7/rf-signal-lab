# P07b：ARM 软件 FFT / 真实接收快照分析

日期：2026-10-11。这是 ARM C 软件模块，**不是 FPGA FFT**。已有FPGA原厂布局布线尚未时序验收，所以先验证可以复用的板端软件分析参考。

## 参考与功能

显式Fs=30.72 MS/s，1024点，周期Hann窗，保留DC、不归一化原始幅值；radix-2 FP64 FFT，经fftshift按[-Fs/2,Fs/2)输出，PSD=|FFT|²/(Fs×窗能量)，单位原始计数平方/Hz。记录时间平均I²+Q²、加窗平均功率和PSD积分；ROI[-9,9]MHz内按分段常值密度积分，等尾99%区间及中点。ROI包含噪声，未做目标检测；区间/中点不能视作已知发射信号的带宽/中心。

先用Python黄金参考核对Windows C，再在实际ARM上复核7类：正频单音、负频单音、非整数频点、DC、零、随机signed12、脉冲。完整PSD、独立整数平均功率、Parseval、ROI插值边界通过。短文件及覆盖已有结果请求被拒绝。首编译遇到misleading-indentation错误，修正语句后新目录重跑；未关闭警告。

## 新真实接收与目标执行

复用已经核验的原生IIO接收二进制，在新/tmp目录建立8×4096、释放再4×1024的两次会话，收到**36,864个复数样本**。先完成有限采集并释放缓冲区，再对文件处理成32+4=36个1024点频谱。它不是边采边算或无缝实时链路。

读到Fs30.72 MS/s、LO2400MHz、BW18MHz、slow_attack、增益71dB；BIST/loopback全0，前后配置一致。12个接收块各不相同，整数统计/格式验证通过。所有36帧ARM PSD与Python独立参考一致，最大绝对误差第一会话8.673617379884035e-18、第二会话8.673617379884035e-19；预定PSD容差rtol1e-10/atol1e-12、ROI边界1e-6Hz。

1024点周期Hann+FFT+PSD平均0.56749798/0.56518612ms；p95 0.569991001/0.58875ms；峰值RSS1116KiB。100次测量、5次预热，不含ROI、IO或接收，因此不能推导整条链路吞吐率。

## 证据与验收

- embedded/arm_rx_probe/arm_spectrum.c；experiments/p07b_prepare_arm_spectrum.py、p07b_verify_arm_spectrum.py。
- 编译、7个黄金向量及参考对照：results/p07b-arm-spectrum-20261011T060307Z。包SHA256 89f63114502d1dceebd0d0241c56389a2728341a007e8c1b6ffa2570a4c9146c。
- 实际上板运行：results/p07b-spectrum-board-run-20261011-140440。
- 已回收所有I/Q、PSD、统计、配置、耗时：results/p07b-spectrum-readback-20261011-140500/outputs 与 verification.json；回收包SHA256 c6bf452e1b56049d9bd6ca368d54014b8ea62d26e7b38014c2f4258d9d546d7f。

C软件参考/理论向量对照、目标实现/真实有限采集/相同输入比较和证据回收：**通过**。无需TestBench，因为本模块不包含RTL；FPGA FFT、队列持续运行、硬件丢样证明、受控RF精度、AI与小屏：**待验证**。未接Fs不兼容的1 MS/s FIR。
