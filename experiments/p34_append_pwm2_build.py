"""Append the PWM2 rebuild result to the P34 bitstream record."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "experiments" / "P34-bitstream-generated.md"

SECTION = """
---

# 追加：带背光修正的位流已构建（可部署候选）

上文第 2 节那个位流是**背光修正之前**的版本。本轮把 TTC0 通道 0 → 通道 2 的修正工程完整跑完，得到可部署候选。

## A1. 构建结果

工程 `E:\\p32-pwm2-105934\\project\\combined.xpr`（本轮之前**从未综合过**，所有 run 都是 Not started）。

```
P34_STATUS   write_bitstream Complete!
P34_PROGRESS 100%
DRC finished with 0 Errors, 24 Warnings, 58 Advisories
```

| 项 | 值 |
|---|---|
| 位流 | `E:\\p32-pwm2-105934\\project\\combined.runs\\impl_1\\rf_display_top.bit` |
| 大小 | **5,034,572 B**（修正前版本 5,037,020 B） |
| sha256（前 16） | `96c5d8f3a5fb8cd0` |
| 日志 | `E:\\FPGA_Tools\\Work\\p34-pwm2-build-20261020\\build.log` |

## A2. 时序与资源：与基线完全一致

| 指标 | 基线 P30 | 本轮 PWM2 |
|---|---:|---:|
| WNS | +0.449 ns | **+0.449 ns** |
| WHS | +0.013 ns | **+0.013 ns** |
| 失败端点 | 0 | **0** |
| Slice LUT | 21,828（7.87%） | **21,828（7.87%）** |
| Slice Register | 38,469（6.93%） | **38,469（6.93%）** |
| Block RAM | 12.5（1.66%） | **12.5（1.66%）** |
| DSP | 69（3.42%） | 69（3.42%） |
| 结论 | `All user specified timing constraints are met.` | 同 |

**数值完全一致是合理的**：改的是背光走哪个 TTC 波形输出，属于**引脚/走线变更**，不增减逻辑；而临界路径不经过该网络，所以 WNS/WHS 不变。位流大小差 2,448 B 说明内容确实变了。

## A3. 修正确实在这个位流里

不能只看"构建成功"，要证明改的东西进去了：

| 检查点 | 证据 |
|---|---|
| BD 连线 | `system.bd` L5493–5494：`"sys_ps7/TTC0_WAVE2_OUT"` → `"lcd_pwm_backlight"` |
| 设备树通道 | `fpga/integration/rf-display-p32-pwm2.dts` L359–361：`pwms = <&display_ttc0_pwm>, <0x02 0xc350>`，即**通道 2**、周期 50 µs |
| 配套位流名 | 同文件 L229：`firmware-name = "rf-display-p32.bin"` —— 上板时必须按这个名字安装 |

## A4. 部署前仍缺的三件事

| 项 | 状态 |
|---|---|
| **58 项 CDC** | 未收口（P33 进行中）。DRC 里它们仍是 Advisory，不是 Error |
| **WHS 13 ps** | 与基线同值，薄但为"MET"；多 corner + pessimism removal 已开，无自定义 OCV 降额 |
| **DTBO 编译与安装** | 设备树源码在 `rf-display-p32-pwm2.dts`，需编译成 dtbo 并与位流一起部署；本轮未编译 |

## A5. 部署需要的东西（下一步）

1. 位流装到 `/lib/firmware/rf-display-p32.bin`
2. `rf-display-p32-pwm2.dts` 编译成 dtbo
3. 启动脚本（或一次性 hold 模板）加载位流 + 应用 overlay
4. 上板后检查：DRM 起不来？`iio:device1..3` 在不在？背光与计时是否稳定？

**注意**：项目现有的规矩是**禁止热卸载 RF overlay 或 PWM 驱动**，所以部署要走冷启动路径，并保留回滚（原厂模式）。
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    text = TARGET.read_text(encoding="utf-8")
    if "带背光修正的位流已构建" in text:
        print("section already present, skipped")
        return 0
    TARGET.write_text(text.rstrip() + "\n" + SECTION, encoding="utf-8")
    print(f"appended to {TARGET.name}, now {TARGET.stat().st_size:,} bytes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
