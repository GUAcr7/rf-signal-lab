# EXP-P02：Python I/Q 读取、保存与回放

- 日期：2026-09-28（Asia/Shanghai）。
- 平台：璞致 PZSDR P201，板端 IIO 服务端 v0.24；电脑工程 `.venv` 为 Python 3.12.14。
- 当前状态：**P02 已通过本次启动状态下的验收**。Python 独立采集、保存配置和 I/Q、离线回放均有实测依据；已知射频信号的频率方向留待 P03 验证。

## 已验证的离线基准

使用 P01 保存的 `results/p01-20260928/capture-initial.csv`，
`experiments/p02_read_p01_csv.py` 读取到 400 对数值；首对为 `(-212, -78)`，末对为 `(-65, 50)`。
CSV 每行末尾有一个空字段，文件末尾有空行。
`src/rfsig/iq_io.py` 将有效数值保存为 `(N, 2)` 形状的 `int16` 数组。
`tests/test_iq_io.py` 使用答案已知的样本及无效输入验证读取规则：`5 passed`。
这份接收环境中的数据不是已知调制信号，不能当作调制识别真值。

## Python IIO 导入故障与修复

工程 `.venv` 安装 `pyadi-iio==0.0.21`、`pylibiio==0.25` 后，`pip check` 输出
`No broken requirements found.`。直接执行 `import iio, adi` 仍在
`iio.py` 调用 `find_library("libiio.dll")` 时失败：返回 `None`，随后出现
`TypeError: argument of type 'NoneType' is not iterable`。这只说明当前 Python
进程未找到原生 DLL，不代表板卡或已安装的 Python 包损坏。

原厂 IIO Oscilloscope v0.18 目录已有 `libiio.dll`。在 **当前 Python 进程**
临时将其目录置于 `PATH` 前端，同时用 `os.add_dll_directory` 提供 DLL 搜索目录后，
`iio` 和 `adi` 均可导入。为避免修改系统环境变量或复制 DLL，工程新增
`src/rfsig/iio_runtime.py`，由脚本在使用 IIO 时显式调用。

可复现的只读连接检查命令（在工程根目录运行）：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\experiments\p02_iio_import_check.py --libiio-dir 'D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin' --uri 'ip:192.168.2.1'
```

本机实测输出：选中 DLL 为上述目录的 `libiio.dll`，客户端 libiio 版本
`(0, 26, 'v0.26')`；板端型号 `PUZHI PZSDR P201`，设备列表包含
`ad9361-phy`、`xadc`、`cf-ad9361-dds-core-lpc`、`cf-ad9361-lpc`。
连接检查退出码为 0，未写板卡射频参数。

## Python 单帧接收（2026-09-28 实测）

新增 `experiments/p02_rx_once.py`。它沿用板卡当前的采样率、接收频率、接收带宽和增益模式，仅选择第 0 路复数接收通道，并读取 1024 对 I/Q。运行命令：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\experiments\p02_rx_once.py --libiio-dir 'D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin'
```

实测退出码为 0；输出如下：

```text
样本形状： (1024,)
数据类型： complex128
是否为复数： True
采样率 Hz： 30720000
接收中心频率 Hz： 2400000000
接收带宽 Hz： 18000000
增益模式： slow_attack
前 5 个样本： [-288. -33.j  -96.-191.j  -11.-279.j  -60. -49.j -320.  +4.j]
样本是否变化： True
```

这说明 Python 能从接收设备取到一帧格式正确且数值变化的复数样本。`complex128` 是 Python 端组合后的数据类型，不表示 AD9361 的 ADC 精度。数值变化不能单独证明接收到了目标发射信号，也不能据此判断调制类别。此脚本未将这帧新样本写入文件。

## 已知样本的保存与回放参考（2026-09-28 实测）

新增 `experiments/p02_save_replay_reference.py`，用三对答案已知的复数 I/Q
`[1+2j, -3+4j, -1j]` 测试 NumPy `.npy` 保存和重新载入。文件创建在临时目录，测试结束后自动清理。程序使用 `np.testing.assert_array_equal` 逐点比较，确保数值、顺序、形状和类型没有因存取发生变化。

本机运行退出码为 0；输出为：

```text
样本数： 3
数据类型： complex128
回放校验：通过
```

这项测试只验证电脑文件读写的黄金参考，不是新一次板卡接收；下面的真实采集实验完成板卡数据及配置的保存。

## 两次真实采集与独立回放（2026-09-28 实测）

实现 `src/rfsig/iq_recording.py`、`experiments/p02_capture_record.py` 和
`experiments/p02_replay_record.py`。保存格式见 [P02 I/Q 数据文件说明](../p02-iq-data-format.md)。
采集脚本只选择第一组 I/Q 和 1024 样本缓冲区，读取既有射频设置；没有发射，也没有重新设置采样率、接收本振、射频带宽或增益模式。每次运行创建不同的记录目录，保存 `iq.npy` 和 `metadata.json`，立即读回并逐点比较。随后在两个独立 Python 进程中分别执行离线回放，不依赖板卡 IIO 连接。

在工程根目录运行采集命令两次：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\experiments\p02_capture_record.py --libiio-dir 'D:\FPGA natch\IIO-Oscilloscope-v0.18-portable\app\bin'
```

两次运行退出码均为 0；记录及核对结果：

| 记录目录 | `iq.npy` SHA256 | I 范围 | Q 范围 | 接收调用耗时 |
| --- | --- | --- | --- | --- |
| `results/p02-20260928T122013158254Z/` | `7c8725475cfe8c908fcad24c056f8efeb99ea698bd471fab643ca4cd1b3a78e9` | -402～514 | -586～614 | 0.02584 s |
| `results/p02-20260928T122024774600Z/` | `4d278d80a892989bce6175776a6e3a4cb40543aacd4b25729dd8965d5bf` | -533～575 | -652～499 | 0.00428 s |

每份均为 `(1024,)`、`complex128`，每个 I/Q 分量都是整数且落在有符号 12 位范围内；同一帧保存前后的样本逐点相同，两份独立采集的数据不同且各自不是固定值。两份 `iq.npy` 文件各为 16,512 字节。接收调用耗时是电脑端单次调用时间，**不是持续吞吐率**；1024/30,720,000 ≈ 33.3 微秒才是每帧覆盖的信号时间。

板卡上下文为 `PUZHI PZSDR P201`；固件 `v0.35-dirty`，板端 libiio v0.24、客户端 libiio v0.26。`voltage0/1` 扫描格式均为小端、有符号、有效 12 位/存储位置 16 位、shift 0。两帧采样前后读取的采样率均为 30,720,000 Hz，接收本振 2,400,000,000 Hz，射频带宽 18,000,000 Hz，增益模式 `slow_attack`。第一帧增益读数为采样前 71 dB、采样后 69 dB；第二帧为 71 dB、71 dB。这些是自动增益下的时点读数，不代表固定增益。完整配置、时间、版本、数据哈希在各自的 `metadata.json`。

独立回放命令和结果：

```powershell
.\.venv\Scripts\python.exe -X utf8 .\experiments\p02_replay_record.py .\results\p02-20260928T122013158254Z
.\.venv\Scripts\python.exe -X utf8 .\experiments\p02_replay_record.py .\results\p02-20260928T122024774600Z
```

两个命令退出码均为 0，均输出“离线回放：SHA256、样本数和类型校验通过”，读取的前 5 个样本与对应采集时打印的前 5 个样本一致。首次采样为 `[-139+40j, -83-44j, -16+133j, 33+146j, 115+35j]`；第二次为 `[125-137j, 26-252j, -6-247j, -231-267j, -222-109j]`。P01 的 IIO Oscilloscope 导出 CSV 也已由 Python 对**同一份文件**解析为 400 对原始数值，首末样本与导出文件一致；未拿不同噪声帧的频谱相互比较。

存取功能单元测试 `tests/test_iq_recording.py` 覆盖已知样本逐点回放、类型/元数据保留、文件被改动时的 SHA256 拒绝、已有记录不覆盖、无效数据拒绝。与 CSV 读取测试一起运行：`12 passed in 0.58s`。

## 验收边界与后续

| 检查项 | 状态 | 依据 |
| --- | --- | --- |
| 离线读取 P01 I/Q CSV | 通过 | 400 对数值，首末样本与原文件一致 |
| CSV 读取规则单元测试 | 通过 | `tests/test_iq_io.py`：5 passed |
| Python 包依赖完整 | 通过 | 固定版本安装、`pip check` 无破损依赖 |
| 原生 libiio 加载与设备发现 | 通过 | 指定原厂 DLL 后成功连接 P201，接收设备可见 |
| Python `rx()` 取得新 I/Q | 通过 | 单次取得 `(1024,)`、`complex128`，样本变化，退出码 0；参数见上 |
| 已知样本 `.npy` 保存与回放参考 | 通过 | 三对复数样本逐点相同，退出码 0 |
| 两次真实采样与配置回读 | 通过 | 两帧各 1024 对；采样前后主要射频设置相同；扫描格式和版本已记录 |
| 原始数据保存与离线回放 | 通过 | 两份 `.npy`/JSON；立即逐点比较和独立回放校验均通过 |
| 软件 I/Q 配对与扫描格式 | 通过 | pyadi 映射和板端扫描格式确认实部=voltage0、虚部=voltage1、有符号 12/16 位；按 raw counts 保存 |
| 已知信号的频率方向 | 待 P03 | 当前输入无已知单音，不能从噪声判断正负频率方向 |

本阶段未改系统 `PATH`、未复制或覆盖 DLL、未修改 SD 固件或板卡射频设置。P02 属于原厂采集链路和文件存取验证，未开发 FPGA RTL 或 AI 模型，因此 TestBench、AI 量化和 FPGA 资源时序验收不适用。P01 CSV 证明 Python 能解析 IIO GUI 导出的同一份原始数据；**尚未做 Python 与 IIO GUI 对同一帧频谱的数值对照**，不据此声称频谱算法一致。`results/` 被 Git 忽略，转移工程时需另行复制两份记录目录。下一阶段 P03 才使用已知单音验证 I/Q 频率方向与收发链路；本轮不进入 P03。
