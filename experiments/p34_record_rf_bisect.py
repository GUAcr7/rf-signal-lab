"""Append the RF-half bisection result and record it in the status file."""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "experiments" / "P34-bisect-bitstream-vs-overlay.md"
STATUS = ROOT / "TX-SOURCE-STATUS.json"

SECTION = """
---

# 追加：另一半也通了 —— 射频侧在合并位流上初始化成功

上文第 5 节列的"下一步"已执行。结果把问题范围进一步收紧。

## B1. 实验设置

rf 模式下 `S99board` 的行为与显示模式不同：

| 模式 | 位流来源 | overlay |
|---|---|---|
| display | overlay 的 `firmware-name`（= `system_wrapper.bin`） | `d480p.dtbo` |
| **rf** | **脚本显式 `echo system_wrapper.bin > fpga_manager/firmware`** | `pl.dtbo`（无 `firmware-name`） |

所以要让 rf 模式用我们的位流，只需把 `ad9361.bin` 换成我们的裸数据（`cmp` 比较通过后 staging 会跳过拷贝）：

```
cp ad9361.bin ad9361.bin.vb        # 备份 17,416,348 B，sha256 65b44449…
cp p32.raw   ad9361.bin            # 我们的位流 sha256 34eeb736…
echo rf > /etc/board-mode
```

## B2. 结果：AD9361 完整初始化

```
board-init: mode=rf bitstream=/lib/firmware/ad9361.bin overlay=/lib/firmware/pl.dtbo
fpga_manager fpga0: writing system_wrapper.bin to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Found swapped sync word
board-init: fabric operating after explicit bitstream load
ad9361 spi32765.0: ad9361_probe : enter (ad9361)
ad9361 spi32765.0: ad9361_probe : AD936x Rev 2 successfully initialized
board-init: overlay applied: /lib/firmware/pl.dtbo (attempt 1)
cf_axi_adc 79020000.cf-ad9361-lpc: ADI AIM (10.00.b) at 0x79020000 … probed ADC AD9361 as MASTER
cf_axi_dds 79024000.cf-ad9361-dds-core-lpc: … probed DDS AD9361
board-init: rf ready: PHY/ADC/DDS names verified (attempt 1)
board-init: bring-up complete (mode=rf)
```

运行态复核：

| 设备节点 | `name` |
|---|---|
| `iio:device0` | xadc |
| **`iio:device1`** | **ad9361-phy** |
| **`iio:device2`** | **cf-ad9361-lpc** |
| `iio:device3` | cf-ad9361-dds-core-lpc |

`fpga_manager state = operating`。

## B3. 二分表（完整）

| PL | 设备树 | 结果 |
|---|---|---|
| 我们的合并位流 | 厂家显示 overlay `d480p.dtbo` | **✅ 启动；DRM/fb0 800×480/背光正常** |
| 我们的合并位流 | 厂家射频 overlay `pl.dtbo` | **✅ 启动；AD9361 Rev 2 初始化，4 个 IIO 设备** |
| 我们的合并位流 | 我们的合并 overlay | **❌ 无输出硬挂死** |

**结论：合并位流的射频与显示两半都是好的。唯一有缺陷的是我们手工重建的那份合并设备树。**

这也顺带否掉了"CDC 导致挂死"的猜想 —— 同一个位流在两种厂家设备树下都稳定运行，VDMA、DRM、PWM、AD9361 全部正常。

## B4. 由此得到的修复路线（比调试自制 overlay 更稳）

既然两份厂家 overlay 都能在我们的位流上工作，**正确的合并方式不是"重建"，而是"忠实拼接"**：

1. 取 `factory-rf.dts`（fragment@1..3）与 `factory-display.dts`（fragment@0..2）原文
2. 重新编号 fragment（RF → 0/1/2，显示 → 3/4/5），同步改写 `__symbols__` 里的路径
3. 去掉反编译带出的 `__symbols__` / `__fixups__` / `__local_fixups__` 与旧 phandle，交给 `dtc -@` 重新生成
4. 仅把 `firmware-name` 改为我们的文件名
5. `dtc -@ -I dts -O dtb` 编译

项目里 `experiments/p31_build_overlay.py` 已有 `clean_body()` 等现成机制可复用。

**关键差别**：现成的自制 overlay 是"按理解重建"的（可能与厂家结构有细微但致命的差异），而拼接方案**逐字保留厂家原文**，只做编号重排。

## B5. 当前板子状态

- 模式：**rf**
- PL：**我们的合并位流**（`state=operating`）
- 设备树：厂家 `pl.dtbo`
- 射频：**可用**（4 个 IIO 设备）
- 显示：无（rf 模式本就没有 `/dev/fb0`）

**这是一个可用状态**，且是"我们的位流第一次真正跑起射频"。

## B6. 证据

| 内容 | 路径 |
|---|---|
| rf 模式准备（备份与哈希） | `results/p34-rf-mode-prep-20261020/` |
| rf 启动日志 | 本轮抓取 19,218 B |
| **rf 运行态复核** | **`results/p34-bisect2-rf-verify-20261020/`** |
"""

RESULT = {
    "date": "2026-10-20",
    "result": ("the merged bitstream is good for BOTH halves: with the vendor RF overlay AD9361 "
               "initialises and four IIO devices appear; with the vendor display overlay DRM and "
               "fb0 800x480 come up. Only our hand-built combined overlay hangs the board."),
    "bisect_table": {
        "bitstream + vendor display dt": "boots, display OK",
        "bitstream + vendor rf dt": "boots, ad9361-phy + cf-ad9361-lpc + dds probed",
        "bitstream + our combined dt": "hard hang, no output",
    },
    "cdc_hypothesis": "ruled out for this hang: the same bitstream runs stably under both vendor trees",
    "fix_route": ("stop rebuilding the overlay from understanding; concatenate the two factory DTS "
                  "verbatim, renumber fragments, let dtc -@ regenerate symbols/fixups, change only "
                  "firmware-name. experiments/p31_build_overlay.py already has clean_body() for this."),
    "board_state_now": {
        "mode": "rf",
        "pl": "our merged bitstream (state=operating)",
        "device_tree": "vendor pl.dtbo",
        "rf": "working: iio:device1 ad9361-phy, iio:device2 cf-ad9361-lpc, iio:device3 dds",
        "display": "absent in rf mode, expected",
    },
    "evidence": ["results/p34-rf-mode-prep-20261020/",
                 "results/p34-bisect2-rf-verify-20261020/"],
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    text = TARGET.read_text(encoding="utf-8")
    if "另一半也通了" not in text:
        TARGET.write_text(text.rstrip() + "\n" + SECTION, encoding="utf-8")
        print(f"appended to {TARGET.name}, now {TARGET.stat().st_size:,} bytes")
    else:
        print("section already present")

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    data["p34_bisect_rf_half"] = RESULT
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status: p34_bisect_rf_half recorded")
    return 0


if __name__ == "__main__":
    sys.exit(main())
