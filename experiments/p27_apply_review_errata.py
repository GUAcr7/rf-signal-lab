"""Append errata to my own HW-016 and HW-017 records after the independent review.

Two of my published conclusions were wrong or too strong:

  HW-016: a 1.2 kHz carrier shift across power cycles was called "about 40 ppm".
          Relative to the 2450 MHz LO it is 0.49 ppm; 39 ppm is only what it
          would be relative to the 30.72 MHz sample clock. Mixing the two is a
          real error, not a rounding difference.

  HW-017: "two buffers continuous, so long captures are feasible" is too strong.
          A 16-buffer four-channel capture shows 11 jumps, and the audit records
          lossless_proven = false for every configuration including my two-buffer
          one. A zero modulo difference can also hide whole periods.

This script only appends; the original text stays for traceability.
"""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PPM_ERRATUM = """
---

# 勘误 E1：40 ppm 是错的，正确的是 0.49 ppm

> 独立审查（[EXP-HW-018](EXP-HW-018-review-and-streaming.md)）指出本文件把 1.2 kHz 的载波变化写成"约 40 ppm"，混淆了 RF 本振与采样时钟。核对属实。

| 参照 | 计算 | 结果 |
|---|---|---:|
| **2450 MHz 本振**（正确参照） | 1200 / 2450e6 | **0.49 ppm** |
| 30.72 MHz 采样时钟 | 1200 / 30.72e6 | 39.06 ppm |

**我把采样时钟当成了分母。** 两者的物理含义完全不同：

- 相对本振的偏差是 **CFO**（载波频偏）
- 相对采样时钟的偏差是 **SCO**（采样钟偏）
- 由一次 CFO 观测**不能**判定是哪块板的 LO 不准，也**不能**换算成 SCO

**结论修订**：两次上电之间载波变化约 1.2 kHz，相当于 **0.49 ppm @ 2450 MHz**。
"每次上电必须重新估计载波"这条操作要求不变，但理由要改成"绝对偏差虽小，在 2450 MHz 上仍是千赫兹级，足以在长块内累积成相位斜坡"。
"""

CONTINUITY_ERRATUM = """
---

# 勘误 E1：结论过强 —— 2 缓冲连续不等于长采集可行

> 独立审查（[EXP-HW-018](EXP-HW-018-review-and-streaming.md)）用同一套源位置方法测了 5 组配置。核对 `results/p26-independent-audit-20261018T122935Z/report.json` 属实。

## E1.1 实际读数

| 通道 | 缓冲 | 帧数 | 判定 | 跳跃 | `lossless_proven` |
|---:|---:|---:|---|---:|---|
| 4 | 4096 | 65,536 | detected_jumps | **12** | False |
| 4 | 65536 | 131,072 | modulo_consistent | 0 | False |
| 4 | 65536 | 262,144 | modulo_consistent | 0 | False |
| 4 | **65536** | **1,048,576** | **detected_jumps** | **11** | False |
| 2 | 65536 | 1,048,576 | modulo_consistent | 0 | False |

## E1.2 我错在哪

**① 把"2 缓冲连续"推广成了"长采集可行"。** 实际上同样 65536 缓冲、4 通道、16 缓冲时出现 **11 处跳跃**。缓冲大小不是唯一变量，**总吞吐**也是。

**② 把模差 0 当成了无丢样。** 源周期是 131,072 样本，模差为 0 **可能漏掉整周期**。`lossless_proven` 在**所有配置**（包括我的两缓冲）都是 `false`。

**③ 我的代码有个真 bug**：窗口对齐失败时我把它们从 `usable` 里删掉再算 `modulo_gaps`，于是相邻比较变成了**非相邻比较**。审查同时指出这一点。

## E1.3 结论修订

| 项 | 原说法 | 修订后 |
|---|---|---|
| 跳跃原因 | 缓冲太小导致频繁重填 | 方向对，但**不完整**：与总吞吐也有关，4 通道 1 MB 采集仍出现 11 处 |
| 2 缓冲 | 连续，可当 4.27 ms 连续记录 | 仅"模差一致"，**不证明无丢样** |
| 长采集可行性 | 先加大缓冲可能就够 | **未成立**。16 缓冲 4 通道失败；只有 2 通道 16 缓冲通过 |
| 能否自称无丢样 | — | **不能**，任何配置都没有 `lossless_proven` |

## E1.4 仍然成立的部分

- 对照组仍精确复现 12 处跳跃及幅值（2000/6293/5602…），说明**源位置对齐这套方法可信**
- `-b 4096` 的 12 处跳跃与 `-b 65536` 2 缓冲的 0 处，这两条读数本身没错
- 错的是**由它们推出的结论**
"""

STATUS_NOTE = {
    "my_errors_found_by_review": [
        "HW-016: 1.2 kHz was called about 40 ppm; relative to the 2450 MHz LO it is 0.49 ppm. 39 ppm would only be correct relative to the 30.72 MHz sample clock, and CFO cannot be converted into SCO or blamed on a specific board.",
        "HW-017: 'two buffers continuous, so long captures are feasible' was too strong. A 16-buffer four-channel capture shows 11 jumps, and lossless_proven is false for every configuration including my two-buffer one.",
        "HW-017 code: dropping windows that failed to align before calling modulo_gaps turned adjacent comparisons into non-adjacent ones.",
        "align_rotation minimised blind EVM, whose complex gain absorbs a residual rotation, so the chosen angle did not prove the axes were aligned.",
        "S99board checked only that iio:device1 existed, not that PHY, ADC and DDS were all present, and it swallowed rmdir failures so a failed rebind looked like a retry.",
        "P23 known-source reference mixed the TX nominal offset with the RX measured carrier, which is the root cause of the +33.97 dB nonsense figure.",
    ],
    "verified_from_review": [
        "840 tests pass (measured)",
        "the five-configuration continuity table matches the audit JSON field for field",
        "the 0.49 ppm figure is correct for the 2450 MHz reference",
        "the deployed S99board (sha256 2a553309...) checks all three device names and no longer swallows rmdir errors",
    ],
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    for relative, text, marker in (
        ("docs/experiments/EXP-HW-016-cold-start-reproduction.md", PPM_ERRATUM, "勘误 E1：40 ppm"),
        ("docs/experiments/EXP-HW-017-multibuffer-continuity.md", CONTINUITY_ERRATUM, "勘误 E1：结论过强"),
    ):
        path = ROOT / relative
        body = path.read_text(encoding="utf-8")
        if marker in body:
            print(f"  {relative}: errata already present, skipped")
            continue
        path.write_text(body.rstrip() + "\n" + text, encoding="utf-8")
        print(f"  {relative}: errata appended")

    status = ROOT / "TX-SOURCE-STATUS.json"
    data = json.loads(status.read_text(encoding="utf-8-sig"))
    data["independent_review_20261018"] = STATUS_NOTE
    data["pending_verification"] = [
        "continuity beyond 16 buffers and under sustained running; lossless_proven is false everywhere so far",
        "a hardware sample counter or sequence number before any gap-free claim",
        "real RF dataset with SNR labels and train/validation/test split",
        "which side compresses (TX or RX analogue chain) - needs a spectrum analyser tap",
        "measured confirmation of --full-scale 2048 with a known-amplitude signal",
        "screen UI and simultaneous display + RF on one bitstream",
        "whether a missing /etc/pointercal lets auto-calibration overwrite pointercal.xinput again",
    ]
    status.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("  status updated")
    return 0


if __name__ == "__main__":
    sys.exit(main())
