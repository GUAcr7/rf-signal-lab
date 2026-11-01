"""Build evidence-linked review, current entry points and a conservative status."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[1]


def latest(pattern):
    files = sorted(ROOT.glob(pattern))
    if not files:
        raise FileNotFoundError(pattern)
    return files[-1]


def relative(path):
    return Path(path).resolve().relative_to(ROOT).as_posix()


def main():
    audit_path = latest("results/p26-independent-audit-*/report.json")
    audit = json.loads(audit_path.read_text("utf-8"))
    boot_path = latest("results/p26-boot-verification-*/report.json")
    boot = json.loads(boot_path.read_text("utf-8"))
    if audit["transfer_incomplete"] or boot["status"] != "warm_boot_and_three_device_readiness_verified":
        raise RuntimeError("cannot publish completion while transport or boot remains unverified")
    if len(audit["buffer_progress"]) != 5:
        raise RuntimeError("expected old control, two, four, sixteen and RX1 sixteen cases")
    restore_path = latest("results/p26-rx-profile-restore-*/report.json")
    restore = json.loads(restore_path.read_text("utf-8"))
    if restore["status"] != "reviewed_rx_profile_restored_and_read_back":
        raise RuntimeError("final RX profile not restored/read back")
    pytest_log = latest("results/p26-verification*/pytest.log")
    pytest_folder = relative(pytest_log.parent)
    tests = int(re.search(r"(\d+) passed", pytest_log.read_text("utf-8"))[1])
    stamp = datetime.now(timezone.utc).isoformat()
    sources = audit["buffer_progress"]
    rx1 = sources[-1]
    jumps = rx1["assessment"]["detected_jump_count"]
    rx1_status = "检出跳跃，减少 RX2 字节仍未解决连续性" if jumps else "未检出非周期跳跃；仍不能证明长期无丢样"
    table = "\n".join(
        f"| {r['channels']} | {r['buffer_samples']} | {len(r['windows'])} | {r['assessment']['detected_jump_count']} | {r['assessment']['status']} |"
        for r in sources)
    snap_table = "\n".join(
        f"| {r['modulation_supplied']} / {r.get('case','冷启动')} | {r['reference_evm_db']:.2f} | {r['valid_symbols']} | {r['symbol_errors']}/{r['checked_symbols']} |"
        for r in audit["snapshots"])
    boot_sha = hashlib.sha256((ROOT/"board/boot/S99board").read_bytes()).hexdigest()
    header = f"状态更新：{stamp}（UTC）。最新审查：[EXP-HW-018](docs/experiments/EXP-HW-018-review-and-streaming.md)。\n"
    readbacks = "\n".join(s["output"] for s in boot["stages"] if s["port"] == "COM8" and s["command"].startswith("cat in_voltage"))
    (ROOT/"START-HERE.md").write_text("# 从这里恢复项目工作\n\n"+header+f'''
旧 P201 限时发送，新 TLZ7xH-EVM + FMCOMMS3 接收。三调制真实有限快照、保存/回传和已知符号恢复通过；**长期无丢样、真实 AI、FPGA 数据链上板及射频与显示共存尚未完成**。

## 最新完成

- 今天冷启动三调制原始字节/回传/板端 SHA 重新核对，已知符号 EVM −37.19、−37.97、−37.64 dB；每份 502 有效符号，后半段 251 检查符号零错。这使用已知源，不是独立 BER/AI 测试。
- 修复参考下变频、QPSK 标称相位、旋转搜索残相位、16QAM 短块 PLL 启动偏差；批量精修与已知参考法在 P22 六份数据上吻合。
- 四通道 4 缓冲未检出非周期跳跃，16 缓冲检出 **11 处**；只采 RX1 的 16 缓冲检出 **{jumps} 处**。{rx1_status}。
- 启动脚本按名字核对 PHY/ADC/DDS，拒绝移除失败的假重试；已备份、部署、哈希一致并通过一次 **warm reboot / attempt {boot['successful_attempt']}**。真实 attempt 2/3 是否执行：**{boot['real_retry_branch_exercised']}**；模拟驱动分支测试通过。
- Python 全回归 **{tests} passed**：[日志](results/p26-verification-20261018/pytest.log)。43 项原生 TX 模拟基线未重跑，C 发射代码未修改。

## 当前板卡状态

新板本轮最后为 **rf 模式**，风扇与三类 IIO 名字正常；屏幕黑屏符合现有互斥位流。旧板两次 30 s 发送都已清理退出，物理 RF 静默/LO 泄漏仍未测。COM8/COM9 是本次端口，重连须重新确认身份。

本轮 RF 采集时没有写 RF 属性。warm reboot 后实测恢复了原厂 slow_attack/71 dB、RX LO 2400 MHz；已先备份读数，再仅恢复此前验证过的 RX manual/0 dB、LO 2450 MHz并读回确认，未发射、未改变 TX 或采样率。最终读回见 HW-018。**不得把重启前配置当成重启后已生效**。

采样布局必须跟随实际 mask：四通道 I1,Q1,I2,Q2 为 8 B/帧；只启用 voltage0/1 的 RX1 为 4 B/帧。均为 le:S12/16>>0，有符号端点 −2048/+2047。不读取历史 en=0 来推断此前采集 mask。

## 恢复与下一步

1. 读 [本轮报告](docs/experiments/EXP-HW-018-review-and-streaming.md) 和 [恢复清单](docs/handoff/RESUME-20261018.md)，枚举端口、认板、核验模式/名字/配置。
2. 旧板若重启，其 RAM 临时文件丢失；复用已验证恢复包，不安装/重烧。原包及恢复程序见恢复清单。重读 boot_id，8 项包校验、inspect、6 支 check 通过后才能限时发射。
3. 已知调制短快照继续用单 DMA 65536 样本，并剔除滤波边缘。对跨缓冲数据记录边界、逐窗分析，不给拼接块虚构连续 ADC 时间。
4. 长采集先解决消费者吞吐/排队并增加独立丢样观测。若做真实 AI 数据集，用多会话、多随机源与测得/有依据的 SNR，按会话/源序列分组，不把同一周期波形切片随机分到训练和测试。
5. FPGA 与 RF/display 共存按实际新板原厂工程完成，不用桌面离线图代替上板验收。

`results/` 被 gitignore 排除，备份必须连同该目录和原始采样。历史记录在 `results/p26-before-20261018/`。机器状态：[TX-SOURCE-STATUS.json](TX-SOURCE-STATUS.json)；原路线：[实施指南](docs/implementation-guide.md)。
''', encoding="utf-8", newline="\n")

    resume = f'''# 恢复工作清单（2026-10-18 审查版）

先读 [START-HERE](../../START-HERE.md) 和 [HW-018](../experiments/EXP-HW-018-review-and-streaming.md)。此前“16QAM 四阶矩无效、QPSK 90° 导致 EVM 错、40 ppm、两缓冲证明连续”等说法均已纠正；原稿有备份，不按旧结论推进。

## 已完成与接下来

真实三调制短快照和数据回收通过，{tests} Python 回归通过。长期连续性未过，RX1 16 缓冲 {jumps} 处检出跳跃；真实 AI、合并 PL/屏幕与实际系统吞吐未验收。不重复安装 Vivado 或重烧现有可用固件。

## 下次按序做

1. 核对供电和已验证射频接线，枚举串口。旧板身份 `pzp201`，新板 `Zynq-Tronlong`。串口一次仅一个拥有者；本轮旧 COM9、新 COM8，不硬编码当永久身份。
2. 新板读 `/etc/board-mode`、`/sys/class/fpga_manager/fpga0/state`，运行 `/etc/rcS.d/S99board --check-rf`；此诊断不加载位流。当前是 rf，黑屏不表示驱动坏。
3. 读 PHY 的采样率、RF 带宽、RX_LO、gain mode、hardwaregain、rf_port。**重启会重置运行属性**。已验证收发条件是 Fs 30720000、RF BW 18000000、TX/RX LO 2450000000、TX port A/gain −10、数字单分量峰值 256、RX1 manual/0 dB、A_BALANCED。不同条件另立实验，不直接扩大功率或归因时钟。
4. 旧 P201 RAM 文件若已丢失，恢复包 `results/p13-upload-bundle-20261017T025802Z/board-session-bundle.tar`，SHA `9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e`。用 `p12_serial_upload.ps1` 的新 `/tmp/p12-source-stage-*` 和新证据目录；解包、chmod 755、8 项校验、inspect、6 支 check、当前 boot_id 全通过。当前旧板未重启时已恢复的目录是 `/tmp/p12-source-stage-1018/stage` 和调制源 `/tmp/p12-source-stage-mods1018/bundle`。
5. 只有确认实际配置/源文件哈希及原有限时守卫后才发射；不把恢复检查变成自动发射。三个调制峰值 256 文件在 `results/p21-mod-waveforms-20261017T122536Z/bundle/`，与六支旧测试波形包不同，须分别恢复。
6. 首先做单 DMA 快照。默认四通道 65536 帧应为 524288 B；明确只选 voltage0/1 时为 262144 B，解析器 channels=2。匹配采集元数据，保存板端 SHA，回收后校验。
7. 调用 `p23_features_continuous.py` 或 `reference_receiver.py` 做已知调制诊断；滤波每侧 640 保护点、保留约 502 符号。批量精修使用整块数据；它不是盲分类器。每次重新估载波。

## 长采集的正确边界

四通道 16 缓冲已经检出 11 处跳跃；只采 RX1 的测试见 HW-018。周期为 131072 的参考只给模周期进度，即使零跳跃也不能排除整周期损失。不要把低相关对齐当时间缺口，或把负模差当负的丢样数。

下一步先实现快速采集与处理解耦、实际吞吐/队列观测或采用有依据的降采样方案，再验证更长接收。数据集可以用明确带边界的快照，但按独立会话/随机源分组，SNR 没有测量依据就留空。

## 启动脚本回滚

审查版 SHA `{boot_sha}`。板端旧版备份在 `/etc/p26-S99board-before-20261018`，不在 rcS.d 的 S* 通配目录内。恢复时先复制到非 S* 临时名、校验/755、再原子替换；保留当前版本备份。不要把 `.off` 当作可靠停用。

若自然出现 PRODUCT_ID 0xFF，保存完整启动日志、模式/位流校验与设备名，确认真实 attempt 2/3 是否成功。当前普通 warm reboot 通过不代表重试分支已验证，不反复制造硬件故障。
'''
    (ROOT/"docs/handoff/RESUME-20261018.md").write_text(resume, encoding="utf-8", newline="\n")

    report = f'''# EXP-HW-018：独立审查、纠错与多缓冲推进

- 日期：2026-10-18；报告生成 {stamp}。
- 范围：主 AI 的 HW-015/016/017 交付、原始字节、参考测量、启动脚本与多缓冲采集。已授权修复及上板复测；没有代替 GUI 验收。
- 验收结论：**有限已知源接收通过；长期连续性未通过；本轮软件修复与普通启动通过；真实 AI、RF/display 共存仍待实现。**

## 1. 必须修复项与结果

| 严重程度 | 原位置 / 问题 | 影响 | 修复 / 复测 |
|---|---|---|---|
| P1 | HW-017 / P25：两缓冲零模差当无丢样；失败窗被删后比较非邻居 | 虚假连续、跨缺口滤波 | 保留索引、可信门限、有符号模差与不可证边界；旧对照仍复现 12 处；新 16 缓冲检出 11 处 |
| P1 | S99board：仅 iio:device1 存在即就绪；忽略 rmdir 失败 | PHY/ADC/DDS 不全时假成功、假重试 | 按三个名字确认，移除失败即停；真实脚本在模拟驱动下覆盖第 1/2/3 次成功、耗尽与移除失败；原子部署后 warm reboot 通过 |
| P2 | P23：TX 标称偏移与 RX 实测载波混用重建参考 | +33.97 dB 假差 EVM、难以定位硬件 | 新 known-source 接口分开处理，逐字节重建 TX 核验；QAM 两份 −37.23/−37.30 dB |
| P2 | align_rotation 只比最小 EVM，复增益隐藏残相位 | 不能证明坐标轴已对齐 | 去掉残增益相位，测试检查轴向与估计角 |
| P2 | 粗频偏 + 因果 PLL 启动过程影响短块 EVM | big2 仍被算成 −31.05 dB | 全有效符号批量判决反馈拟合相位斜率，无额外裁差；与已知参考吻合 |
| P2 | HW015/RESUME/状态：QAM 矩无意义、QPSK 90°、I/Q 比旋转不变 | 错误教学、错误指标解释 | 改为集合四阶矩、45° 标称矩相位、轴向限定；有数学和注入数据测试 |
| P2 | HW016/状态：1200 Hz 写成 40 ppm | 混淆 RF 与采样时钟 | 相对 2450 MHz 是 0.49 ppm；不据 CFO 判定哪块 LO 或 SCO |
| P2 | 入口停在 HW014、部署状态和“0/250”过期 | 恢复时重复/误操作 | 更新入口/机器状态/恢复清单，后半段检查数为 251/份；旧版备份保留 |

## 2. 原始证据复核

P24 三调制均验证：串口 base64 解码 = 已有 raw 文件 = 板端 SHA256。P25 三段回传重组与 1048576 B 原始字节、板端 SHA 一致。P26 新采集使用分块 gzip 回传，逐块哈希、压缩包 SHA、解压后原始 SHA 和长度全部核验，重启前全量回收。

| 调制 / 数据 | 已知符号 EVM dB | 有效符号 | 后半段错误/检查数 |
|---|---:|---:|---:|
{snap_table}

载波与源位置使用全块已知发射序列；后半段虽单独用前半段增益判决，也不是完全独立的 BER 试验或 AI 测试。低 EVM 不替代实际发射功率/频率标定。

## 3. 本轮两次真实 RF 试验

复用数字峰值 256、TX gain −10 dB、RX manual/0 dB、LO 2450 MHz、Fs 30.72 MS/s、RF BW 18 MHz及原接线。没有写 RF 属性，没有增加功率；两次发射都由原生守卫限 30 秒，退出 0、资源释放、DDS 零源读回。物理 RF 静默/LO 泄漏没有测量。

| 输入存储通道数 | 每 DMA 样本数 | 窗口数 | 检出跳跃边界 | 判定 |
|---:|---:|---:|---:|---|
{table}

**RX1 16 缓冲：{rx1_status}。** 四通道时消费者需搬运 245.76 MB/s，RX1 为 122.88 MB/s（理论原始负载，非已达成吞吐）。完整记录 wall time 包含启动/落盘，不能直接换算丢样总数。落点确认是 tmpfs，不能凭文件路径把原因归咎 SD。

源周期 131072 样本。即使模差为零，也可能漏一个或多个完整周期；±1 是估计容差，不是已证明的物理解释。有符号负模差不能当负丢样数。具体驱动排队、调度、复制机制仍需独立观测。

## 4. 启动脚本与最终状态

审查版 SHA `{boot_sha}`；原版备份 `/etc/p26-S99board-before-20261018`，不放在 rcS.d 的 S* 名字下。安装临时名不匹配 S*，校验后原子替换，权限 755。

新板一次 warm reboot 的 boot_id 确已改变，实际脚本日志完整、PHY/ADC/DDS 都可见，成功 attempt **{boot['successful_attempt']}**。真实 attempt 2/3 分支执行：**{boot['real_retry_branch_exercised']}**；模拟驱动分支通过不能替代真实间歇故障复测。一次 0xFF 重绑恢复只证明可恢复，不证明芯片无间歇问题或确定时序根因。没有为了测试故意破坏复位/电源/驱动。

新板最后 rf 模式，屏幕与 RF 官方位流仍互斥；旧板无活动发送，串口工具已释放。warm reboot 后运行 RF 配置读回如下，**不是重启前配置继续生效的假设**：

```text
{readbacks.strip()}
```

## 5. 测试与证据索引

Python 全回归 **{tests} passed**，见 `results/p26-verification-20261018/pytest.log` 与 JUnit。新增检查含：非邻窗/弱匹配/整周期不可见、QAM 数学矩与轴向、频偏注入、RX/TX 不同载波的黄金参考、启动脚本模拟失败与重试、传输截断拒绝。没有以 expected 值冒充实测。

- 独立审查：[report.json](../../{relative(audit_path)})。
- 修复特征：[features.json](../../results/p26-known-modulation-features-20261018T121600Z/features.json)。
- 4/16 四通道采集：[report](../../results/p26-multibuffer-acquisition-20261018T115942Z/report.json)，完整 [回传记录](../../results/p26-chunk-transfer-20261018T120112Z/report.json)。
- RX1 采集：[report](../../results/p26-multibuffer-acquisition-20261018T122051Z/report.json)，完整 [回传记录](../../results/p26-chunk-transfer-20261018T122135Z/report.json)。
- 启动部署：[report](../../results/p26-boot-deployment-20261018T121928Z/report.json)，[warm reboot](../../{relative(boot_path)})。
- 完整测试：[pytest.log](../../results/p26-verification-20261018/pytest.log)。
- 原文/代码备份：`results/p26-before-20261018/`。新代码、测试、实验脚本与机器状态都在项目内；results 被 Git 忽略，需独立备份。

## 6. 下一步按依赖

1. 采用本轮单 DMA 可靠快照接口，RF 配置、mask、边界、源哈希与会话 ID 绑定。长流问题解决前不跨未知边界做滤波/PLL。
2. 独立观测采集/消费队列，尝试采集先入预分配内存、分析/落盘分离；依据实际 AD9361/PL 速率链评估降采样。只增缓冲仅延长突发时间，不能宣布持续吞吐通过。
3. 引入硬件样本计数、不重复源标记或等效证据，验证更长连续采集和停止/重启。未取得证据继续标待验证。
4. 用独立会话和随机发送内容采集真实数据集，记录各类、SNR 方法、分组划分。不能以同一个循环帧随机切片构造虚高准确率，也不能把已给定调制的预处理当盲识别。
5. 继续实际新板工程的 FPGA 数据链与 RF/display 共存；模块测试/桌面回放/合成模型结果保留已有验收范围，不替代整机验收。

本轮无新 FPGA 或 AI 模型实现，所以不伪造资源/时序/量化指标；这些环节在对应开发阶段验收。无需用户重复安装或寻找信号源；后续物理测量/界面点击需要时再给最小步骤。
'''
    (ROOT/"docs/experiments/EXP-HW-018-review-and-streaming.md").write_text(report, encoding="utf-8", newline="\n")

    path = ROOT/"TX-SOURCE-STATUS.json"
    status = json.loads(path.read_text("utf-8-sig"))
    status.update(schema="rfsig.tx_source_status.v5", updated=stamp,
                  updated_note="HW-018: reference/phase/boot corrections; 4/16 and RX1 streaming tested",
                  record="docs/experiments/EXP-HW-018-review-and-streaming.md",
                  python_tests=tests, python_tests_evidence=relative(pytest_log),
                  python_tests_note="Full project run after measurement and boot-check corrections.",
                  status="known_source_snapshots_pass; long_stream_not_accepted; real_ai_combined_display_pending")
    status.setdefault("RF_transmit_count_prior_index", status.get("RF_transmit_count"))
    status["RF_transmit_count"] = None
    status["RF_transmit_scope"] = "Whole historical count not re-audited; HW-018 added exactly two bounded 30-second runs, unchanged RF attributes. Native cleanup verified; physical silence remains unmeasured."
    status["carrier_must_be_reestimated"]["implies"] = "Re-estimate each capture. 1200 Hz / 2450 MHz = 0.49 ppm, not 40 ppm; does not measure SCO or identify either oscillator."
    status["qam16_run_difference"] = {"verdict": "known-source big1/big2 -37.23/-37.30 dB; previous gap was a metrology issue",
        "fix": "separate nominal TX and received carrier; physically align axes; batch decision-directed slope fit avoids short causal PLL acquisition transient",
        "evidence": "results/p26-known-modulation-features-20261018T121600Z/features.json", "blind_ai_verified": False}
    old_cold = status["cold_start_reproduction"].get("results")
    status["cold_start_reproduction"].setdefault("historical_decision_pipeline_results", old_cold)
    status["cold_start_reproduction"]["results"] = audit["snapshots"][:3]
    status["cold_start_reproduction"]["note"] = "Raw transport/board hashes verified independently; known-source EVM uses full-block carrier/source fit. Not independent BER/AI."
    status["ad9361_probe_retry"].update(fix="verify actual PHY/ADC/DDS names; check removal failure; bounded three attempts",
        deployed=True, deployed_note=f"Reviewed sha256 {boot_sha}; mode 755, atomic install, one warm reboot success",
        evidence_policy=relative(boot_path), retry_branch_exercised=boot["real_retry_branch_exercised"],
        retry_branch_note="Mock driver covers attempt 2/3 and failures. Ordinary hardware reboot reached attempt 1; real failure branch unverified.")
    status["ad9361_probe_retry"]["what_is_proven"] = {"manual_recovery": "one earlier PRODUCT_ID 0xFF recovered after rebind, root cause not proven",
        "reviewed_boot": "hash persisted, boot ID changed, PHY/ADC/DDS and bring-up log accepted", "simulated_retry": True}
    status["multibuffer_continuity"] = {"record": status["record"], "answer": "long_stream_not_accepted",
        "cases": [{k:r[k] for k in ("source","channels","buffer_samples","assessment")} for r in sources],
        "lossless_proven": False, "evidence":relative(audit_path),
        "limits":"Periodic source cannot exclude whole-period loss. Four channels 16 windows: 11 detected boundaries. RX1 outcome in cases."}
    cc=status["modulated_reception"].get("continuous_recapture",{})
    cc["historical_feature_results_note"]="Superseded by HW-018 feature output; supplied modulation alignment is not blind separation."
    cc["separability_corrected"]={"note":"Amplitude CV is rotation invariant; I/Q ratio is axis dependent. QAM fourth ensemble moment is meaningful. See HW-018, no blind accuracy claimed."}
    cc["caveats"]=["502 symbols per snapshot, two archived P22 repetitions per modulation; not independent AI test.","No long-stream acceptance."]
    status["review_p26"]={"evidence":relative(audit_path),"rx1_jump_count":jumps,"boot":relative(boot_path),
                          "new_rf_runs":2,"capture_RF_settings_written":False,"tests":tests,
                          "rx_profile_restore":relative(restore_path),"final_rx_attributes":restore["after"],
                          "RX_attributes_written_after_reboot":restore["rx_attributes_written"]}
    # Report original post-reboot defaults alongside the explicitly restored
    # final configuration. Do not silently relabel the prior raw readbacks.
    report_path=ROOT/"docs/experiments/EXP-HW-018-review-and-streaming.md"
    text=report_path.read_text("utf-8")
    text += f'''
## 7. 重启后的恢复与工具复测

上面的启动读数是原厂默认：slow_attack/71 dB，LO 2400 MHz。本轮已先归档 before，再仅恢复经验证的 RX manual/0 dB 和 RX LO 2450 MHz，并逐项读回。采样率、带宽、端口与 TX 不变，期间不发射。最后实际配置：

```json
{json.dumps(restore['after'],ensure_ascii=False,indent=2)}
```

恢复证据：[report](../../{relative(restore_path)})；冻结配置 [profile](../../configs/rf-link-snapshot-p26.json)。启动脚本持久化不代表这些运行属性持久化；下次断电后仍须核验。

本轮工具自身也有两次被守卫拒绝的检查：首次重启验证误接收关机前残留提示符，因 boot_id 未改变而失败；没有再重启，只在原重启完成后续查并验证新 boot_id。之后增加新启动横幅条件。RX 读数解析曾把控制台折行片段当值，**在写入前拒绝**；改为明确值帧，补三项解析回归后实际恢复成功。失败目录保留 `p26-boot-verification-20261018T122934Z` 与 `p26-rx-profile-restore-20261018T123154Z`，不抹去失败记录。
'''
    # The final run includes the three serial-parser regressions. Preserve the
    # earlier 837-pass file rather than overwriting it.
    text=text.replace("results/p26-verification-20261018",pytest_folder)
    figure=latest("results/p26-review-figures-*/review.png")
    text+=f'''
## 8. 实测对照图

左图比较相同采样率/缓冲长度下的四通道与 RX1 模周期源位置；右图比较 16QAM 粗估计、因果 PLL、批量精修及已知发送符号对照。低 EVM 与零模差各自有本报告列出的使用范围。

![P26 真实证据对照](../../{relative(figure)})
'''
    quality_path=latest("results/p26-rx1-symbol-quality-*/report.json")
    quality=json.loads(quality_path.read_text("utf-8"))
    text+=f'''
## 9. RX1 全部 16 个 DMA 窗口的符号质量复核

对新 RX1 原始文件的每个 65536 样本窗口单独匹配、下变频和滤波，没有跨边界处理、没有删除差窗口。合计 **{quality['total_valid_symbols']} 个有效符号**，按每窗前半段增益检查后半段，合计 **{quality['total_symbol_errors']}/{quality['total_checked_symbols']} 错误/检查数**；逐窗已知符号 EVM 为 **{quality['evm_min_db']:.2f} ~ {quality['evm_max_db']:.2f} dB**。相同源位置诊断未检出非周期跳跃。

这为 RX1 mask 和整段窗口内的信号质量增加了实际证据；名义样本量仅对应 **{quality['represented_nominal_samples_ms']:.3f} ms**，源仍周期重复，且每窗使用全窗已知源拟合，所以仍不声称长期无丢样、独立 BER 或 AI 准确率。证据：[逐窗报告](../../{relative(quality_path)})。
'''
    status["review_p26"]["rx1_symbol_quality"]={"evidence":relative(quality_path),
        "valid_symbols":quality["total_valid_symbols"],"checked_symbols":quality["total_checked_symbols"],
        "symbol_errors":quality["total_symbol_errors"],"reference_evm_range_db":[quality["evm_min_db"],quality["evm_max_db"]]}
    report_path.write_text(text,encoding="utf-8",newline="\n")
    start=ROOT/"START-HERE.md"
    start.write_text(start.read_text("utf-8").replace("results/p26-verification-20261018",pytest_folder),encoding="utf-8",newline="\n")
    board_readme=ROOT/"board/README.md"
    board_text=board_readme.read_text("utf-8")
    board_text=re.sub(r"\| `boot/S99board` \|[^\n]+",f"| `boot/S99board` | {(ROOT/'board/boot/S99board').stat().st_size:,} | `{boot_sha[:12]}` | HW-018 已部署；三设备按名验收、普通 warm reboot 通过，真实重试分支待验证 |",board_text)
    board_text=board_text.replace("rf 查 `iio:device1`","rf 按名查 PHY/ADC/DDS（HW-018 修正）")
    board_text=board_text.replace("**共 17 处 `|| fail` 检查点**，111 行。三个脚本均通过 `dash -n` 语法检查。",
        "上述行号/17 处/111 行为 HW-008 历史版本；当前审查版按设备名检查并有有界重试，部署和复测见 HW-018。不要凭旧行号恢复旧文件。")
    board_readme.write_text(board_text,encoding="utf-8",newline="\n")
    path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+"\n",encoding="utf-8",newline="\n")
    print(relative(audit_path),"RX1 jumps",jumps,"tests",tests)


if __name__ == "__main__":
    main()
