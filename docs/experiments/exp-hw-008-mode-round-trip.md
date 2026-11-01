# EXP-HW-008：显示 → 射频 → 显示 模式往返（已闭环）

- 日期：2026-10-17 深夜。
- 承接 [EXP-HW-007](exp-hw-007-touch-persistence.md)（触摸持久化闭环）。
- 本轮目标：`EXP-ERRATA-20261017` §9 中"模式切换往返"一项。
- **结果：三段全部通过，已闭环。** 每段都有 transcript，日志逐步可读。
- 本轮性质：真实上板，三次重启。

## 1. 部署内容

| 文件 | 板端路径 | 字节 | sha256（前 12） | 权限 |
|---|---|---:|---|---|
| `board/boot/S99board` | `/etc/rcS.d/S99board` | 5,040 | `2bfc9e5f8cb7` | 755 |
| `board/boot/board-mode` | `/usr/bin/board-mode` | 1,238 | `8ab1978e375a` | 755 |
| （模式文件） | `/etc/board-mode` | — | — | 内容 `display` |

位流规范化（新脚本按固定名取文件）：

| 板端文件 | 字节 | 来源 |
|---|---:|---|
| `/lib/firmware/display.bin` | 3,346,176 | `cp system_wrapper.bin display.bin` |
| `/lib/firmware/ad9361.bin` | 17,416,348 | `cp sw-ad9361.bak ad9361.bin` |
| `/lib/firmware/d480p.dtbo` | 4,712 | 原有 |
| `/lib/firmware/pl.dtbo` | 8,201 | 原有 |

`/etc/rcS.d/` 里**只有一个** board 脚本（`ls | grep -i board` 确认），没有残留。

## 2. 三段实测

### 2.1 第 ① 段：display → display

```
board-init: fan on
board-init: mode=display bitstream=/lib/firmware/display.bin overlay=/lib/firmware/d480p.dtbo
board-init: staged bitstream already current
board-init: overlay applied: /lib/firmware/d480p.dtbo
board-init: display ready: /dev/fb0 present
board-init: bring-up complete (mode=display)
```

| 检查 | 结果 |
|---|---|
| `fpga0/state` | operating |
| `/dev/fb0` | 存在 |
| `gpio914/direction` | out |

### 2.2 第 ② 段：display → **rf**

```
board-init: fan on
board-init: mode=rf bitstream=/lib/firmware/ad9361.bin overlay=/lib/firmware/pl.dtbo
board-init: staged bitstream copied and verified
board-init: fabric operating after explicit bitstream load
board-init: overlay applied: /lib/firmware/pl.dtbo
board-init: rf ready: iio:device1 present
board-init: bring-up complete (mode=rf)
```

| 检查 | 结果 |
|---|---|
| `fpga0/state` | operating |
| `/sys/bus/iio/devices/` | **`iio:device0  iio:device1  iio:device2  iio:device3`**（xadc + ad9361-phy + cf-ad9361-lpc + dds） |
| `gpio914/direction` | out（风扇与模式无关） |

**注意 `staged bitstream copied and verified`**：从 display 位流切到 ad9361 位流，脚本真的复制并 `cmp` 复核了。这是 `rf` 模式特有的路径（`pl.dtbo` 没有 `firmware-name`，必须显式加载）。

### 2.3 第 ③ 段：rf → **display**

```
board-init: fan on
board-init: mode=display bitstream=/lib/firmware/display.bin overlay=/lib/firmware/d480p.dtbo
board-init: staged bitstream copied and verified
board-init: overlay applied: /lib/firmware/d480p.dtbo
board-init: display ready: /dev/fb0 present
board-init: bring-up complete (mode=display)
```

| 检查 | 结果 |
|---|---|
| `fpga0/state` | operating |
| `/dev/fb0` | 存在 |
| `/sys/bus/iio/devices/` | **只剩 `iio:device0`** —— AD9361 设备正确消失 |
| `gpio914/direction` | out |

**这一段是往返的关键**：它证明从射频位流切回显示位流后，AD9361 的设备节点**干净消失**，没有留下半初始化状态。

## 3. 这段证明了什么

| 结论 | 依据 |
|---|---|
| 位流与 overlay **由同一个 `$MODE` 派生，不会配错** | 三段日志里 `bitstream=` 与 `overlay=` 始终成对出现 |
| 每步都检查返回码，**失败即停** | 17 处 `\|\| fail`；三段日志都走到 `bring-up complete`，没有跳步 |
| 暂存逻辑**双向可用** | ① `already current`；②③ `copied and verified` |
| **风扇与模式解耦** | 三段都是第一行 `fan on` |
| rf 模式的显式加载路径正确 | `fabric operating after explicit bitstream load` 出现在 overlay 之前 |
| 切回后设备节点干净 | ③ 段 IIO 从 4 个回到 1 个 |

## 4. 这也顺带证明"显示与射频互斥"

同一时刻只会有一个位流生效：

- display 模式：`/dev/fb0` 有、AD9361 无
- rf 模式：AD9361 有（4 个 IIO 设备）、`/dev/fb0` 无

与 [新板审查](../design/new-board-tlz7xh-evm-review-20261017.md) 第 5 节的引脚级分析一致：两个官方位流都各自完整，不能同时存在。

## 5. 证据

| 段 | 路径 |
|---|---|
| 位流规范化 | `results/p17-mode-setup-20261017/` |
| 脚本安装与模式设置 | `results/p17-mode-install-20261017/` |
| 第 ① 段 display | `results/p17-roundtrip-1-display-20261017/` |
| 切到 rf | `results/p17-mode-set-rf-20261017/` |
| 第 ② 段 rf | `results/p17-roundtrip-2-rf-20261017/` |
| 切回 display | `results/p17-mode-set-display-20261017/` |
| 第 ③ 段 display | `results/p17-roundtrip-3-display-20261017/` |

## 6. 仍未验证

| 项 | 说明 |
|---|---|
| **不重启的热切换** | 本方案靠重启生效（`board-mode` 只写文件）。热切换需要先解绑驱动再重配 PL，风险更高，未做也未承诺 |
| **人工点击触摸** | 已由用户确认"点的很准"（本轮之前），但无自动化证据 |
| `/etc/pointercal` 缺失时的自动标定覆盖 | 上一轮遗留 |
| rf 模式下的真实 I/Q 采集 | 下一步 |

## 7. 留档的两条操作经验

1. **`board-mode` 只写文件，必须重启** —— 不要把"设置了模式"当成"模式已生效"。判断生效只能看 `dmesg | grep board-init` 里那行 `mode=...`。
2. **`dmesg | grep board-init` 是这套机制的验收入口** —— 六行日志对应六步，缺哪行就知道停在哪。
