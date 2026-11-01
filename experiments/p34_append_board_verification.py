"""Append the on-board verification results to the P34 record."""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TARGET = ROOT / "docs" / "experiments" / "P34-panel-ui.md"

SECTION = """
---

# 追加：上板显示已验收（2026-10-20 晚）

本文件第 5 节列的"上板显示未做"，现已完成。

## U1. 帧缓冲实测参数

| 项 | 实测 |
|---|---|
| `/dev/fb0` | 字符设备，root:video |
| `bits_per_pixel` | **32** |
| `virtual_size` | **800,480** |
| `stride` | **3200** = 800×4 ✓ |
| `wc -c < /dev/fb0` | **3,072,000** = 两页 |

**双缓冲/两页**这点很关键：帧缓冲可读长度是画面大小的两倍，所以对**整设备**做哈希永远不可能与单帧文件相等。正确做法是只比第一页：

```sh
dd if=/dev/fb0 bs=1024 count=1500 | sha256sum    # 1500*1024 = 1,536,000
```

## U2. 显示验证链

| 环节 | 结果 |
|---|---|
| 通道测试图（红/绿/蓝三竖条） | **用户目视确认顺序正确**，`bgra32` 成立 |
| 测试图写入完整性 | 回读第一页哈希与渲染文件**逐字节一致** |
| QPSK 面板 | 哈希 `a6e4301a…` 一致，用户确认可见 |
| 16QAM 面板 | 哈希 `ac6f30ed…` 一致 |

字体在 12 号下可读，星座簇与 4×4 网格均清楚。

## U3. 一个真实故障：帧缓冲控制台会重绘覆盖画面

**现象**：第一次写完测试图后画面正常，但几分钟后图像被破坏（哈希从 `a6e4301a…` 变成 `c026d4f8…`）。

**根因**：`/sys/class/vtconsole/vtcon1` 是帧缓冲控制台，**内核与串口输出会被镜像画到面板上**。我第一次执行 `echo 0 > vtcon1/bind` 后**没有读回确认**，实际 `bind` 仍是 **1**。

**判据**：解绑成功时内核会打印
```
Console: switching to colour dummy device 80x30
```
并且 `cat vtcon1/bind` 必须读回 **0**。

**验证方法**（重要）：解绑后写入画面，再**故意连发几条会产生控制台输出的命令**，然后回读第一页哈希：

```
写完后        a6e4301a…  ✓
发两条 echo 后 a6e4301a…  ✓ 未变
```

**这条"发流量再验哈希"的方法才是真验证**，只比一次哈希证明不了抗覆盖。

**所以画面消失不是"点屏幕"造成的** —— 当时没有 X、没有程序读触摸、也没有进程写 `/dev/fb0`；是控制台重绘。

## U4. 持久化与切换

板端现在有：

| 路径 | 内容 |
|---|---|
| `/root/panels/{qpsk,qam16}.fb.gz` | 21,725 / 22,423 B，**SD 卡持久**（断电不丢） |
| `/root/show-panel.sh` | 切换脚本：先解绑 vtcon1 并校验 `bind=0`，再写入 |

用法：`/root/show-panel.sh qpsk` 或 `/root/show-panel.sh qam16`。

两次切换的实测哈希均与渲染文件一致，且脚本未打印解绑告警。

**注意**：`/tmp` 下的临时副本在重启后消失，但 `/root/panels` 里的不会；`vtcon1` 的绑定状态重启后也会恢复为 1，所以**必须用脚本**而不是手工重定向。

## U5. 仍未做

| 项 | 原因 |
|---|---|
| 实时刷新 | 需合并位流（RF 与显示共存）后由板上持续绘制 |
| 触摸交互 | 未做；当前没有 X 也没有应用读触摸 |
| 开机自动显示 | 需在启动流程里加一步，且要与厂家桌面（xserver-nodm）取舍；本轮未改动启动集合 |
| 画面与采集联动 | 现在是"电脑渲染 → 传字节"的离线流程 |

## U6. 证据

| 内容 | 位置 |
|---|---|
| 帧缓冲参数 | `results/p34-fb-geometry-20261020/` |
| 控制台解绑 | `results/p34-unbind-vtcon-20261020/`（含 `colour dummy device` 日志） |
| 写入与回读 | `results/p34-write-testpattern2-20261020/`、`p34-write-qpsk-20261020/`、`p34-write-qam16-20261020/` |
| **抗覆盖验证** | **`results/p34-panel-stability-20261020/`**（写入 + 两条命令后哈希不变） |
| 切换脚本实测 | `results/p34-show-panel-test-20261020/` |
| 切换脚本源码 | `board/boot/show-panel.sh` |
"""


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    text = TARGET.read_text(encoding="utf-8")
    if "上板显示已验收" in text:
        print("section already present, skipped")
        return 0
    TARGET.write_text(text.rstrip() + "\n" + SECTION, encoding="utf-8")
    print(f"appended {len(SECTION):,} chars to {TARGET.name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
