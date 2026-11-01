# P06：ARM 原生 C / 本地 IIO 接收验证

日期：2026-10-11。平台：当前 P201，原厂 Linux armv7l、glibc 2.28、libiio 0.24。通过 USB 串口 COM5 自动执行；没有操作 SecureCRT COM9、调谐、发射或写入固件。

## 实际操作与依据

使用原厂已有 libiio 动态库，头文件取自 ADI 的 [libiio v0.24 官方源码](https://github.com/analogdevicesinc/libiio/blob/v0.24/iio.h)，来源与 SHA256 保存在 embedded/vendor/libiio-v0.24/source.json。C 程序检查 PHY 和 RX 设备、输入扫描通道及格式，再建立非循环接收缓冲区。结束后释放缓冲区与 context，然后重新建立第二会话。

实际收到 8×4096 + 4×1024 = **36,864 个复数采样点**，12 个块的哈希各不相同。Python 独立回读板端原始字节，整数和、平方和、最小/最大值与 C 记录一致。两次缓冲区释放及重新建立通过。

两条通道均为小端有符号 12 位有效数据、16 位存储、shift=0、repeat=1。保存为交织 int16 I/Q。配置前后采样率 30.72 MS/s、LO 2400 MHz、RF 带宽18 MHz、slow_attack、读到的增益71 dB；BIST/loopback 均为0。本程序没有写这些属性。

第一会话耗时0.023645857秒、第二会话0.004782837秒，进程峰值 RSS 2192/2200 KiB。这是有限接收及文件写入的观测，不能换算成长期无丢样能力。硬件块间连续性和目标调制未知。

## 证据与验收

- 程序：embedded/arm_rx_probe/arm_rx_probe.c；准备脚本 experiments/p06_prepare_arm_rx.py；独立验证 experiments/p06_verify_native_rx.py。
- 编译/ELF/源文件/包：results/p06-native-rx-20261011T053133Z。
- 实际板端执行：results/p06-native-rx-board-run-20261011-133241/report.json 与 serial-transcript.txt。
- 已回收原始数据：results/p06-native-rx-readback-20261011-133251/outputs；逐项验证 verification.json。
- 回收包 SHA256：8871aaa3b88730f69d4171dc4cb9f68bc4b58b94459fcb88f3ff5eed05a11a78。

本地 C 读取真实 RX、格式确认、有限多块采样、释放后重开、保存回读：**通过**。持续无缝采集/受控 RF 信号/已知调制/实时 FIR 与模型连接：**待验证**。1 MS/s FIR 不能直接用于当前30.72 MS/s，不混用模型的 float32 文件与 RX int16 文件。

## 恢复

成果已保存在电脑；板端 /tmp 断电会消失。需要时从准备目录重新传到新的 /tmp 目录，核对哈希后执行，避免覆盖已有结果。无需重复安装或烧录。
