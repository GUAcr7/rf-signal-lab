"""Apply the reviewed explanatory corrections; original records were backed up."""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOC = ROOT/"docs/experiments"


def main():
    assert (ROOT/"results/p26-before-20261018").is_dir()
    (DOC/"EXP-HW-015-qam16-difference-check.md").write_text('''# EXP-HW-015：16QAM 差异复核（2026-10-18 勘误）

原稿、原始结果分别保存在 `results/p26-before-20261018/` 和原结果目录。本轮未覆盖原始采样。统一审查见 [HW-018](EXP-HW-018-review-and-streaming.md)。

**两份 16QAM 快照都能恢复到约 −37.2 dB；此前约 6.5 dB 差异来自测量流程，不能据此判定接收硬件波动。** 这是已知调制有限快照，不是盲 AI 验收。

## 独立复算

输入 `results/p22-transfer-20261017T132355Z/{big1,big2}.bin`，四通道、每份 65536 帧。TX 源按原参数重建并与已发文件逐字节核对。TX 参考去掉自身标称 960 kHz；RX 去掉接收到的实测载波，再按源位置取发送符号。

| 采样 | 已知符号 EVM | 判决反馈批量精修 EVM | 有效符号 |
|---|---:|---:|---:|
| big1 | −37.23 dB | −37.23 dB | 502 |
| big2 | −37.30 dB | −37.30 dB | 502 |

证据：`results/p26-qam16-reference-fix-20261018T121210Z/diagnosis.json`、`results/p26-known-modulation-features-20261018T121600Z/features.json`。后者同时保留粗估计、因果 PLL、批量精修读数，没有删掉环启动时的差结果。

## 原解释错误与修正

1. **“16QAM 四阶矩没有意义”错误。** 每个符号四次方不全部重合，但集合矩仍有相位信息。等概率、单位功率方形 16QAM 的 `E[x^4]=−0.68`，单位相位的四阶矩为 `−0.36`。有限样本、频偏和噪声影响估计；定轴要包含标称矩负号。
2. **QPSK 的差 EVM 来自漏掉标称四阶矩相位的 45° 定轴偏差。** 90° 对称旋转会改变位标签，但完整点集不变，不能解释该 EVM 异常。
3. **“正交抑制是旋转不变量”错误。** 幅度 CV 不受整体旋转影响；I/Q 功率比须在明确定轴后解释。
4. **最低 EVM 不等于实际坐标轴对齐。** 复增益会吸收残余常相位。`align_rotation()` 现在去掉该增益相位；测试也验证真实轴向，而非只看 EVM。
5. **短块因果 PLL 有启动过程。** 仅加 PLL，big2 仍约 −31.05 dB。离线快照现用全体 502 个有效符号做判决反馈线性相位/频偏精修，没有额外裁掉差符号。该方法使用整块数据，不是实时锁定环，也没有独立完成调制识别。
6. 原 +33.97 dB 已知参考异常来自混用 TX 标称偏移与 RX 实测载波。现已分开，旧数作废。
7. “16QAM 必须小于 10 Hz”不是普遍硬门限。要求依赖时长、SNR、符号率及 EVM 目标。

## 实现与限制

`reference_receiver.py` 做已知发送符号对照，禁止跨记录的 DMA 边界。`carrier_tracking.py` 提供旋转定轴及批量精修，原 PLL 保留。`p23_features_continuous.py` 保留入口名，输出明确为已知调制快照特征。

数学矩、相位、注入频偏、参考下变频和噪声反例均有测试。全块参与载波/源位置拟合，所以后半段零符号错误不能当独立 BER 或 AI 测试。每类只有两次采样，特征分离也不是跨会话识别准确率。
''', encoding="utf-8", newline="\n")

    path = DOC/"EXP-HW-016-cold-start-reproduction.md"
    text = path.read_text("utf-8")
    replacements = {
        '同一次开机内，第一次探测失败、第二次成功** —— 所以是 PL 配置后芯片就绪的时序问题，不是硬件故障。':
        '同一次开机内，第一次探测失败、第二次成功**：证明该次故障可重绑恢复。具体时序/复位或间歇硬件原因待验证，不能排除硬件故障。',
        '**尚未在板上部署验证。** 下次重启时才会真正跑到重试路径。':
        '6193 B 历史版后来已部署，有三次 attempt 1 重启记录；这不等于重试分支实测。审查版又改为按名字同时确认 PHY/ADC/DDS，并检查移除返回码，已部署核验。详见文件顶部更新。',
        '这是两块板独立晶振在不同上电周期下的偏差变化，量级 **~40 ppm**。':
        '观测是跨会话载波变化约 1.2 kHz，不能仅凭此归因哪块板的晶振。相对于 2450 MHz 是 **0.49 ppm**；不能除以采样率而称为 RF 或采样时钟误差。',
        '| 新的 `S99board` 重试逻辑 | **未部署、未在板上验证** |':
        '| 新的 `S99board` 重试逻辑 | 已部署；真实 attempt 2/3 分支待验证，模拟测试通过 |',
        '| 单缓冲采集**消除跳跃** | 每段 524,288 B 整缓冲，源位置连续 |':
        '| 单缓冲快照质量通过 | 原始字节与已知源强匹配；不能证明长期无丢样 |',
    }
    for old, new in replacements.items():
        if old in text:
            text = text.replace(old, new)
        elif new not in text:
            raise RuntimeError("expected HW016 paragraph not found: "+old)
    notice = '''> 2026-10-18 审查更新：以下 −37.04 ~ −37.18 dB 为原流程的历史读数。独立已知符号复算为 BPSK −37.19、QPSK −37.97、16QAM −37.64 dB，每份 502 个有效符号，后半段 251 个检查符号零错；原字节、回传与板端 SHA 一致，见 `results/p26-independent-audit-20261018T121819Z/report.json`。不能把不同测量口径混作同一比较。S99board 审查版哈希 `2a5533091321e1fe6329f8ac95ad63a0fc07f13407d865a37d1cda97484afb3e`，部署证据 `results/p26-boot-deployment-20261018T121928Z/report.json`；按名检查三设备、755 权限和只读就绪检查通过，真实重试分支未验证。完整报告见 [HW-018](EXP-HW-018-review-and-streaming.md)。

'''
    if notice not in text:
        first, rest = text.split("\n", 1)
        text = first+"\n\n"+notice+rest.lstrip("\n")
    path.write_text(text, encoding="utf-8", newline="\n")

    (DOC/"EXP-HW-017-multibuffer-continuity.md").write_text('''# EXP-HW-017：多缓冲采集（2026-10-18 审查修订）

**撤回“两个大缓冲连续、没有丢样”。** 正确结论是两个窗口在 ±1 整数估计容差内模周期一致，周期源不能排除整周期丢失。新增四通道 16 缓冲已检出 11 处非周期跳跃，大缓冲没有解决长期采集问题。

原稿备份 `results/p26-before-20261018/`；原始数据与历史 JSON 保留。统一审查与继续结果见 [HW-018](EXP-HW-018-review-and-streaming.md)。

## 方法与代码修正

每个 DMA 缓冲单独匹配已知 BPSK，只比较相邻且可信的窗口；相关门限 0.99，周期 131072 样本，容差 ±1。低相关/失败标待验证，不证明存在跳跃。

`p25_continuity_check.py` 已修复：保留失败窗口索引；不比较删除失败窗口后形成的非相邻对；用有符号模差接受 −1；拒绝残缓冲；输出独立新目录。测试中明确包含“丢掉一个整周期却模差为零”的反例。

## 实测

| 数据 | 每缓冲样本 | 缓冲数 | 检出跳跃边界 | 判定 |
|---|---:|---:|---:|---|
| P22 small.bin（四通道） | 4096 | 16 | 12 | 复现旧问题 |
| P25 two.bin（四通道） | 65536 | 2 | 0 | 模周期一致，不证明无丢样 |
| P26 buffers4（四通道） | 65536 | 4 | 0 | 模周期一致，不证明无丢样 |
| P26 buffers16（四通道） | 65536 | 16 | 11 | 长记录存在时间跳跃 |

P25 起点 8665、74202，相差 65537；+1 被容差接受，不等于证明它一定是估计误差。P26 16 个窗口全部强匹配，首五窗边界在 +1 内，之后 11 处跳跃。负的有符号模差不是负的物理丢样数，不能累加为缺失样本总数。

本次落盘为 tmpfs，不能将 SD 速度当已证实原因。完整四通道 4/16 原始数据都已回收，板端原始 SHA、gzip SHA、解压字节数全部一致。

## 证据与下一步

- `results/p26-independent-audit-20261018T121819Z/report.json`：原始字节复核与源位置判定。
- `results/p26-chunk-transfer-20261018T120112Z/{buffers4,buffers16}.bin`：完整原始采集。
- `results/p26-multibuffer-acquisition-20261018T115942Z/report.json`：命令、配置与 30 秒 TX 清理。
- `results/p26-continuity-recheck-20261018T121810Z/continuity.json`：修正后重跑对照。
- `results/p25-rx-2buf-raw/two.bin`：1048576 B，SHA `7b306680b60c9d7e067027241cd926fbbc0c6cbb71b120e4ad8007bbad711d73`。

先测试只采 RX1，减少无用 RX2 字节；之后评估采集/处理分离、实际吞吐与队列。增加队列只能延长突发缓冲时间，不能代替持续吞吐。长期无丢样验收需不重复标记、硬件计数或等效独立时间证据。滤波/PLL 不跨未知边界，不给拼接快照虚构连续 ADC 时间。
''', encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
