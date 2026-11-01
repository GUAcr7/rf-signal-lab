# P02 I/Q 数据文件说明

一份采样记录是 `results/p02-时间标识/` 下的两个文件：

- `iq.npy`：1024 个按时间顺序排列的复数样本，可用 `np.load(path, allow_pickle=False)` 读取。
- `metadata.json`：采集时间、板卡与固件、IIO 版本、接收通道、扫描格式、采样配置，以及 `iq.npy` 的 SHA256、样本数和类型。

第 `n` 个样本写作 `x[n] = I[n] + jQ[n]`。本阶段使用 pyadi-iio 的 RX 通道 0，其复数实部来自 IIO `voltage0`，虚部来自 `voltage1`。这说明文件中两列如何配对；真实射频信号的正负频率方向仍需 P03 的已知单音来验证。

板卡报告两个扫描通道均为小端、有符号、**12 位有效值存于 16 位位置**，右移量为 0。pyadi-iio 将 I/Q 合并后返回 `complex128`，因此 `.npy` 的类型是电脑中的存储类型，**不是 ADC 精度**。当前 `rx_output_type` 为 `raw`，数值按未缩放的接收计数保存；不能直接称为伏特或 dBm。当前扫描通道没有提供可用于换算的 `scale`/`offset` 属性。

`metadata.json` 的 `settings_before` 和 `settings_after` 分别记录采样前后的采样率、接收本振、射频带宽、增益模式与增益读数。`slow_attack` 是自动增益模式，读到的 dB 值仅代表读取时刻，不是固定增益设置。`capture_start_utc`/`capture_end_utc` 是电脑时钟时间，不是板卡硬件时间戳。

1024 个样本在 30.72 MHz 采样率下对应约 **33.3 微秒的信号片段**。`capture_call_wall_seconds` 则是电脑调用接收接口的耗时，包含软件和传输开销，不能据此声称连续采样吞吐率。

`src/rfsig/iq_recording.py` 在保存时计算 `iq.npy` 的 SHA256；载入时校验文件哈希、样本数、数据类型和格式，再返回样本。`experiments/p02_capture_record.py` 会在采集后立即逐点比对；`experiments/p02_replay_record.py` 可在不连接板卡的独立 Python 进程中回放。新的采集运行会创建新的目录，不覆盖旧记录。

工程的 `.gitignore` 忽略 `results/` 中的原始数据。实验记录保留目录和 SHA256，转移工程或交给另一位队员复现时，需要另行复制相应采集目录。
