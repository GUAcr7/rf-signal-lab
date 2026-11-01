# 2026-10-16 下午后续：串口恢复与板端只读核验

记录时间窗：2026-10-16 **15:28–15:41**（本地时间 +08:00）。上一份当日记录 [EXP-AUTO-20261016.md](exp-auto-20261016.md) 停在 13:16，没有写入本时间窗的实测证据；本文件补齐该窗口。状态用词沿用 [工程与验证约定](../workflow.md)（第47行）：已实现／已验证／待做／本阶段不适用。除第6节明确标注“未归档”的那次复跑外，文中每个数字都能在“证据路径”列的文件中找到；没有证据的一律写“待验证”。

## 1. 一句话结论

记录从 13:16 更新到 **15:41**；“COM9 被占用、串口待恢复”“交付包未上板、板端脚本未运行”两条已由 **待恢复** 变为 **已验证（只读）**；仍然 **待做** 的是：真实发射、第二块新板、屏幕、受控 RF 链路（**没有 50 Ω 衰减器，只有一根 50 Ω SMA 同轴线，TX→RX 直连不安全**），以及把 15:39 之后的新版 ARM 程序按流程上板复核。

## 2. 与上一份记录的差异对照

| 上一份记录的状态 | 本次实测状态 | 证据路径 |
|---|---|---|
| COM9 被 SecureCRT 占用，串口打开被拒（EXP-TX-SOURCE 第62行“待恢复”） | **已验证**：15:28 起可独占打开 COM9 并登录；本窗口 5 份串口报告的 identity 均为 `Linux pzp201 5.10.0-98231-g9dfba10b795d-dirty ... armv7l`（15:28:20、15:29:06、15:30:11、15:36:21、15:37:11） | `results/p12-board-serial-inspect-20261016-152820/report.json`、`results/p12-board-tools-20261016-152906/report.json`、`results/p12-board-codec-20261016-153011/report.json`、`results/p12-board-source-check-20261016-153621/report.json`、`results/p12-board-identity-20261016-153711/report.json` |
| 本次未做板卡身份核对（仅有历史 MAC/IP） | **已验证**：boot_id `011edfe3-e45b-462d-b6dd-72422d640e45`；CPU part `0xc09`；eth0 `3a:d6:00:58:86:31`；usb0 `00:05:f7:19:e7:93` | `results/p12-board-identity-20261016-153711/report.json` |
| 交付包只在电脑上（EXP-TX-SOURCE 第71行） | **已验证**：1,584,387 字节 gzip 上传到板端 `/tmp/p12-source-stage-20261016-153240/`，板端 `sha256sum` 与主机一致 | `results/p12-serial-upload-20261016-153240/report.json` + 同目录 `serial-transcript.txt` |
| CHECK-ONLY.sh / INSPECT-ONLY.sh 未在板上运行 | **已验证**：两个脚本在**实板**上以 exit code 0 运行完（15 个波形文件 + 3 向量 SHA256 自检 + 逐文件格式检查；只读读回见第3节） | `results/p12-board-source-check-20261016-153621/report.json` |
| 串口传入没有可复用工具 | **已实现+已验证**：新增可复用上传器 `experiments/p12_serial_upload.ps1`；15:32:22 与 15:40:51 两次 4096 字节探针均校验通过、未执行代码 | `results/p12-serial-upload-probe-20261016-153222/report.json`、`results/p12-serial-upload-probe-v2-20261016-154051/report.json` |
| 模拟 IIO 场景 34 项通过 | **已过期**：同一 mock 于 15:40 重跑为 **43/43 通过**（`passed_count=43`、`case_count=43`、`real_rf_transmission=false`），新增“hw_serial 为空回退”“precontext 拒绝”等场景 | `results/p12-native-mock-20261016T074043903949Z/report.json` |
| ARM TX 候选源 SHA `626f5797…` 为部署版本 | **部分改变**：上板包里仍是 `626f5797…`；本机源码已于 **15:39:24** 改为 `b9ba90d3…`，新 ELF `0a188e1e…` **只做了交叉编译+主机文件检查**（`board_accessed=false`），**未上板** | `results/p12-arm-tx-prepare-20261016T073701393532Z/report.json`、`results/p12-arm-tx-prepare-20261016T073925403438Z/report.json`、`results/p12-source-delivery-20261016T051524098482Z/…/SHA256SUMS` |
| 全项目 Python 646 项通过 | **已过期**：复跑为 **667 项通过**（第6节） | `results/p13-python-regression-20261016T082222172Z/pytest.txt`（exit code 0，已归档） |
| 真实 RF 发射／新板／屏幕 | **不变，仍待做** | `docs/design/two-board-rf-link.md`、`TX-SOURCE-STATUS.json` |

## 3. 板端只读读回关键数值（15:36 实板 INSPECT-ONLY）

来源：`results/p12-board-source-check-20261016-153621/report.json`（该次输出末尾为 `INSPECT_PASS read_only=true no_buffers_created=true`）。

| 项目 | 读回值 |
|---|---|
| libiio | `0.24`（另见 `/usr/lib/libiio.so.0.24`，`results/p12-board-serial-inspect-20261016-152820/report.json`） |
| hw_model | `PUZHI PZSDR P201` |
| hw_serial | **空**（见下方影响说明） |
| TX DMA sampling_frequency | `30720000` |
| rx0 / rx1 sampling_frequency | `30720000` / `30720000` |
| rx0 / rx1 rf_bandwidth | `18000000` / `18000000` |
| rx0 / rx1 hardwaregain | `71.000000 dB` / `70.000000 dB` |
| rx0 / rx1 gain_control_mode | `slow_attack` / `slow_attack` |
| rx0 / rx1 rf_port_select | `A_BALANCED` / `A_BALANCED` |
| tx0 / tx1 rf_port_select、hardwaregain | `A` / `A`，均 `-10.000000 dB` |
| RX_LO / TX_LO | `2400000000` / `2450000000` |
| DDS（dds0–dds7） | frequency `9279985`，scale `0.000000`，raw `1`；`DDS_CHANNELS_INSPECTED=8` |
| BIST / loopback | `bist_prbs=0`、`bist_tone=0`、`loopback=0` |
| TX / RX 电压通道格式 | `TX_voltage0 format=le:s16/16>>0 enabled=0`；`RX_voltage0 format=le:s12/16>>0 enabled=0` |
| 其他（15:28 会话） | `/tmp` 为 tmpfs `502.4M`、已用 `36.0K`；`uptime` 2:50；eth0 `192.168.1.10`、usb0 `192.168.2.1`，两者收发计数均为 0 |

两条诚实备注：(1) 15:29 的 sysfs 直读（`results/p12-board-tools-20261016-152906/report.json`）记录的是 `in_voltage0/1_hardwaregain=71.000000 dB`（两路都是 71），与 15:36 的 71/70 相差 1 dB；结合 `gain_control_mode=slow_attack`，这**与 AGC 自身调整一致（推断，非本轮实测结论）**，不把任一次读数当成固定增益。(2) 上述都是**读回值**，不是本轮写入值。

**hw_serial 为空对 identity guard 的影响（重要）**：

- 已上板的旧程序（`626f5797…`）在 `--run` 路径要求 `hw_serial` **非空且与命令行参数完全一致**，否则打印 `exact board serial required` 并退出 → **在本板上它会被自己的身份门禁挡住，不能直接用来发射**（这是门禁按设计工作，不是缺陷）。该结论由源码 `results/p12-source-delivery-20261016T051524098482Z/p201-source-20261016T051524098482Z/arm_tx_source.c` 的判定条件与板端 `hw_serial=` 为空共同推出；**本轮没有运行这个二进制**。
- 本机 15:39 版（`b9ba90d3…`）改为：优先 `hw_serial`；为空时回退到严格合法的 `/proc/sys/kernel/random/boot_id`，形如 `boot-session:<uuid>`，并要求**重启后重新核对**（自检输出 `IDENTITY_SELFTEST_PASS valid_uuid=2 rejected_uuid=8 nil_rejected=true`）。
- 本板 boot_id 是**本次启动会话**身份，重启即变，**不能当永久序列号**；因此“板子是不是那一块”这一层仍缺一个稳定标识。

## 4. 交付包已上板并校验

| 项目 | 值 | 证据 |
|---|---|---|
| `source.tar` sha256 | `34d477d8322a3d8652bc19279c9e42b5ccfc56bf988576037840a18c2f2542e3` | 板端 `sha256sum -c` 输出 `source.tar: OK`（exit 0）；`results/p12-board-source-check-20261016-153621/report.json` |
| `source.tar.gz` sha256 | `5a807a467f59305e09cc49d1dfd4c25263b4c47f6c954afb97578cb88435dcb6` | 板端 `sha256sum` 与主机一致；`results/p12-serial-upload-20261016-153240/serial-transcript.txt` |
| 板端目录 | `/tmp/p12-source-stage-20261016-153240/`（gzip + 解出的 tar + 解包目录 `p201-source-20261016T051524098482Z`） | 同上报告 |
| 传输量 | 输入 1,584,387 B；线上 2,140,313 B；耗时 185.71 s | `results/p12-serial-upload-20261016-153240/report.json` |
| 状态字段 | `serial_upload_checksum_passed_no_code_executed`；`rf_operations=false`；`firmware_changes=false`；`tty_restored=true` | 同上 |
| 工具修订可追溯 | 15:32 使用的上传器副本 sha256 `8c1fbe1e49629322100ac73df6fa15dfaa5813ece1b8d49f7b2dba13cc14112b`；当前 `experiments/p12_serial_upload.ps1` 为 `a62669aa7266b214bcbc3a4d207373e98a2132c03f62434a136fb89e6721f785`（与 15:40:51 探针报告字段一致） | `results/p12-serial-upload-20261016-153240/uploader-used.ps1` + `uploader-source.json`、`results/p12-serial-upload-probe-v2-20261016-154051/report.json` |

`/tmp` 是 tmpfs（可用 502.4M），**断电即失**；结论性证据保存在电脑 `results/` 下，板端副本只是临时工作区。

## 5. 本次明确没有做的事

- **未发射**：所有报告 `rf_operations=false`；板端 CHECK-ONLY 以 `CHECK_ONLY_FINISHED_NO_IIO_NO_RF` 结束；INSPECT 为 `read_only=true no_buffers_created=true`；编译报告 `rf_transmitted=false`。
- **未改 RF 参数**：`rf_configuration_written=false`；只读路径未创建 buffer、未写采样率／增益／本振。
- **未改固件／FPGA／设备树**：报告 `firmware_changes=false`；`fpga/` 下最新文件修改时间仍是 10-15 20:58，本窗口未重新生成、未加载 bit/DTB。
- **未接第二块板**：TLZ7xH-EVM + ADCOMMS3 无实物连接记录，[双板方案](../design/two-board-rf-link.md) 仍是计划；`link-review.INCOMPLETE.json` 未通过。
- **未改 Git**：未 add／commit／reset；`.git/index` 的 SHA256 仍是 `8ead9f45d19caee3dca3792831bc4856801334a17a87c00e6080834572cbc83d`（与 `results/p12-final-regression-20261016-131336/report.json` 一致），其修改时间仍是 2026-09-09 22:43:33。
- **必须同时说明（不算“没做”）**：本窗口在**电脑上**修改了源码——`src/rfsig/iio_runtime.py`、`rf_link_budget.py`、`tx_package.py`、`host/tx_source.py`、`tests/test_iio_gain.py`、`tests/test_rf_link_budget.py`、`tests/native/tx_mock_iio.c`、`experiments/p12_test_tx_native_mock.py`、`p12_prepare_arm_tx.py`、`p12_serial_upload.ps1`、`embedded/arm_tx_source/arm_tx_source.c`。因此**“上板包里的程序”与“当前工作树的程序”不是同一版**，见第3、4节。
- 另外未做：网络连通性核对（无 ping/SSH，板端网卡计数为 0）、屏幕验证、衰减器／线缆实物核验。

## 6. 测试基线更正

- 复现命令（工程根目录）：`.venv\Scripts\python.exe -m pytest -q` → **`667 passed in 42.28s`，exit code 0**；环境 Python 3.12.14、numpy 2.5.3、matplotlib 3.11.1、pytest 9.1.1。归档：`results/p13-python-regression-20261016T082222172Z/`（`pytest.txt` + `report.json`，其中 `board_tests_executed=false`）。同名套件在 16:14 另有一次当场复跑，结果同为 667 项通过（42.99s），未单独归档。
- **旧记录的 646 已过期**：`README.md` 第7行、`docs/experiments/EXP-TX-SOURCE-20261016.md` 第58行（`646 passed，42.19s`）、`TX-SOURCE-STATUS.json` 的 `"python_tests": 646`。
- 646 的那份存档本身仍有效（`results/p12-final-regression-20261016-131336/pytest.txt` 写着 `646 passed in 42.19s`），只是数字不再代表当前代码；本窗口新增／扩展了测试（如 `tests/test_iio_gain.py`、`tests/test_rf_link_budget.py`）。
- 同理，`TX-SOURCE-STATUS.json` 的 `"native_mock_cases": 34` 也已过期：当前 mock 为 **43**（`results/p12-native-mock-20261016T074043903949Z/report.json` 的 `passed_count`/`case_count`）。
- **未同步**：为避免与另一侧会话同时改同一文件，本轮没有改动 `README.md`、`EXP-TX-SOURCE-20261016.md`、`TX-SOURCE-STATUS.json` 中的这三个过期数字；它们仍是 646／34／旧 sha，属于已知待同步项。

## 7. 下一步清单

**A. 需要用户提供实物条件（缺一项就不做受控 RF）**

1. **50 Ω 衰减器**：目前只有一根 50 Ω SMA 同轴线，没有衰减器，按双板方案第3步不能安全直连 TX→RX；需要最小衰减值、额定输入功率、频段与接口。
2. 旧板 TX SMA／PA 在目标频率与数字幅度下的**峰值输出依据**；新板 RX 的推荐输入范围。
3. 第二块板（TLZ7xH-EVM + ADCOMMS3）实物、供电与丝印照片、屏型号／接口，以及老师现用的显示系统。
4. COM9 的使用归属：同一时刻只能有一个程序打开该串口（SecureCRT 与上传器会互相占用）。

**B. 纯电脑可推进（不需要新实物）**

1. 用新上传器把 15:39 版源码／ELF 传到**新的** `/tmp` 目录，只跑 CHECK-ONLY，仍不发射、不写 RF 参数。
2. 归档一次 667 回归证据到 `results/`，再把 646→667 同步进 `README.md`／`EXP-TX-SOURCE-20261016.md`／`TX-SOURCE-STATUS.json`（本轮未改这些文件，避免超范围）。
3. 依读回值推一条现成结论：当前 `DMA=PHY TX=PHY RX=30720000`，按“DMA 速率必须等于文件速率”的守卫（[双板方案](../design/two-board-rf-link.md) 第39行），**只有 existing30m72 那套 30.72 MS/s 波形与现有板卡配置自洽**；planned4m125k / planned4m250k 需要改采样率（本轮未做，属写 RF 参数）。这是由读回值推出的判断，**不是**本轮发射实测。
4. 用用户给出的衰减／线缆参数补齐 `link-review.INCOMPLETE.json` 并复跑 `src/rfsig/rf_link_budget.py` 复核。
5. 新板接收程序的 ABI／IIO 版本核对（新资料 glibc2.23／libiio0.20，旧板实测 glibc2.28／libiio0.24）。

## 8. 给下一次会话／AI 的交接提示

> **⚠️ 本节写于约 16:27，其"下一步"已被当天 17:35–18:25 的工作取代。** 当时建议"补归档 667 回归"或"等用户给出衰减器"；**两项都不是当前的重点了**：
>
> - 667 回归**已归档**：`results/p13-python-regression-20261016T082222172Z/`。
> - 旧 P201 **已实际执行 3 次限时射频发送**，不再受"缺衰减器"阻塞（测频谱仪不需要衰减器，分析仪上限 +30 dBm）。
> - 当前最高优先项变成：**补拍一张标记落在主峰上的频谱照片**，把发射频率与功率定稿。见 [EXP-TX-001](exp-tx-001.md) 第 5 节更正。
>
> 下面这段原文保留，仅供追溯当时状态。

**先读本文件再动手**：15:28–15:41 的串口只读读回、板端 CHECK-ONLY／INSPECT-ONLY、1.58 MB 上板与校验都已完成，不要重复上传同一份 `source.tar.gz`（sha256 `5a807a46…`）或重跑同样的读回；下一步只需二选一——要么补归档 667 回归（第6节），要么等用户给出衰减器等实物条件；**任何串口操作前先确认 COM9 没有被 SecureCRT 或另一个会话占用（上传器要求独占端口，冲突时先释放再开）**，并且**板卡重启后必须重做 identity**（boot_id 会变，hw_serial 为空，不能沿用上一次的 boot-session 标识）。

## 9. 16:00 之后的续接（第二个 AI 会话，电脑侧）

16:00 之后接手时**板卡已不在位**：`[System.IO.Ports.SerialPort]::GetPortNames()` 只剩 COM3／COM4 两条蓝牙口，注册表 `HKLM\HARDWARE\DEVICEMAP\SERIALCOMM` 同样只有 `BthModem0/1`，直接打开 COM9 报“端口不存在”；FTDI（VID_0403）未出现在 PnP 枚举中。**SecureCRT 仍在运行（PID 4712，`D:\FPGA natch\...\SecureCRT.EXE`）**，即串口一旦回来仍可能是被占用状态。因此本节只做电脑侧工作，未接触板卡、未发射、未改 RF 参数或固件。

已完成的电脑侧事项：

| 事项 | 结果 | 证据 |
|---|---|---|
| 667 回归归档（补上第6节缺口） | `667 passed in 42.28s`，exit code 0 | `results/p13-python-regression-20261016T082222172Z/`（`pytest.txt`＋`report.json`） |
| 新增串口二进制回读工具 | 写出并语法自检通过；**尚未在实板运行** | `experiments/p13_serial_readback.ps1` |
| 新增只读 RX 底噪／频谱基线驱动 | 写出并语法自检通过；**尚未在实板运行**（16:27 一次执行因 COM9 不在位而按设计失败并已清理残留目录） | `experiments/p13_rx_baseline_capture.ps1` |
| 两个已确认的工具缺陷修复 | 见下 | `experiments/p12_serial_upload.ps1` |

**必须记住的两个环境事实（否则工具会直接报错）：**

1. **本机没有 PowerShell 7**（`C:\Program Files\PowerShell\7\pwsh.exe` 不存在，全盘常见路径也未搜到），只有 **Windows PowerShell 5.1 / .NET Framework 4.0**。该运行时**没有** `[Security.Cryptography.SHA256]::HashData`，也**没有** `[Convert]::ToHexString` / `::FromHexString`。`p12_serial_upload.ps1` 原版正好用了 `HashData` 和 `ToHexString`，在本机 5.1 下会直接抛“不包含名为 HashData 的方法”——**这就是它必须修的原因**。现已改为 `SHA256.Create()+ComputeHash` 与 `BitConverter`，并用标准向量自检（`sha256("abc")`、`sha256("")`）核对通过。此修复**改变了 `p12_serial_upload.ps1` 的 sha256**，其旧值 `a62669aa…` 只对应 15:40 之前那一版，不要再拿它当当前值。
2. **`od` 十六进制回读约 1.6 KB/s**（115200 波特下每字节约 3 字符）。按此估算：8192 B 的 `.psd` 需约 15 分钟，32 KB 的 `.iq` 超过 1 小时。所以基线驱动**只回读一个小包**：`session-1`（4096 复数样本）＋`session-2`＋两份 ROI 摘要＋前后 IIO 快照，并先在板上 `gzip` 再回读；若包超过 4 MiB 上限则按设计拒绝。

**下一位接手者的顺序**：①先让用户把板卡 JTAG_UART/PWR 的 micro-USB 接回并上电，并用 `[System.IO.Ports.SerialPort]::GetPortNames()` 确认端口号（**不要假定还是 COM9**）；②确认 SecureCRT 已释放该口；③再运行 `experiments/p13_rx_baseline_capture.ps1 -Port <实际口> -LoginPassword analog`；④解包后按 `p07b_verify_arm_spectrum.py` 的同一套独立核验（逐块 `sum_I2_Q2`／`min`／`max`、`bits=12`／`length=16`／`shift=0`、前后配置只允许 `hardwaregain` 不同、PSD 与 NumPy 参考比对）确认基线，再画图。

