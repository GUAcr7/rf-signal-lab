# 板端脚本与实测数据（正式归档）

发布目录的文件名已规范为小写；下文 `S99board` 等写法指原工程与板上部署名称。恢复原路径大小写的方法见 [复现说明](../docs/reproduction.md)，当前仓库路径以实际目录和 `source_manifest.json` 为准。

> 这个目录是**板端文件的权威副本**。`tmp/` 下同名文件只是工作副本，不作为唯一来源。

## 1. 文件清单

| 文件 | 字节 | sha256（前 12 位） | 状态 |
|---|---:|---|---|
| `boot/S99board` | 7,961 | `89183f1fe397` | HW-023保护版安装/校验与一次完整warm reboot通过；禁止重复配置及全部热卸载重试 |
| `boot/S99board.deployed-20261017` | 1,596 | `c9a5b2649d6f` | 历史旧版归档，已被 5040 B 版本替代，不要重新部署 |
| `boot/board-mode` | 1,238 | `8ab1978e375a` | 已部署，HW-008 实测通过 |
| `boot/99touch` | 3,025 | `78a99f915c88` | 已修正 source 语义；HW-007 有重启证据 |
| `boot/pointercal.xinput` | 222 | `ac12ce208d50` | X 触摸标定主来源，HW-007 已部署 |
| `boot/S99fan.superseded` | 795 | `00ccaacb2de9` | 已作废（被 `S99board` 取代） |
| `touch-captures/tap-dump.txt` | 8,135 | `4a45f222db48` | 触摸原始事件（4 角点击） |
| `touch-captures/drag-dump.txt` | 11,837 | `74cf63d7b0a5` | 触摸原始事件（边框滑动） |
| `touch-captures/diag-dump.txt` | 137 | `ad9151ecc6c5` | 触摸原始事件（对角线，**采集为空**） |

`touch-captures/*.txt` 是 `od -An -v -tx1 /dev/input/event0` 的原始输出，每行一个 16 字节 `input_event`。用 `experiments/p15_decode_touch.py --trace` 解码。

## 1.1 新 `S99board` 的执行顺序（2026-10-17 审查后重排）

**风扇最先启动**，因为它挂在 PS MIO8 上、与 PL 位流无关，即使后面 fabric 配置失败板子也能散热。之后每一步都检查返回值，失败即停止后续配置（只停本脚本，不影响 rcS 其余部分）。

| 行 | 步骤 | 失败时 |
|---:|---|---|
| 49 | 风扇：`gpio914` export / direction / value | `fail` |
| 53 | 读 `/etc/board-mode` | — |
| 76 | `cmp` 判断是否需要复制位流 | — |
| 80 | `cp` **并 `cmp` 复核**复制结果 | `fail` |
| 85 | `mount` configfs 并**核对 `/proc/mounts`** | `fail` |
| 95–100 | rf 模式：显式加载位流**并核对 `state=operating`** | `fail` |
| 104 | 应用 overlay（检查返回码与槽位存在） | `fail` |
| 112 | 最终 `state=operating` 验收 | `fail` |
| 116–124 | 分模式终检：display 查 `/dev/fb0`；rf 按名查 PHY/ADC/DDS（HW-018 修正） | `fail` |

上述行号/17处/111行为HW-008历史版本。当前HW-023版本按设备名检查，已有overlay/RF设备时在配置PL前拒绝重复启动，全部自动热卸载重试已停用。一次probe失败则明确失败、下次启动恢复；不要凭旧行号或HW-018重试行为恢复旧文件。原厂热卸载已实测触发内核异常，见[HW-023](../docs/experiments/exp-hw-023-device-tree-cdc-and-kernel-recovery.md)。

## 2. 为什么重写了 `S99board`

### 2.1 旧文件的致命问题：`S99board.off` 无法停用

旧文档写"把 `/etc/rcS.d/S99board` 改名为 `S99board.off` 即可停用"。**这是错的**：sysvinit 按 `/etc/rcS.d/S*` 通配匹配，`S99board.off` 依然匹配 `S*`，只要文件仍可执行，就可能照旧运行。

**可靠停用方式（唯一无条件成立）**：把文件**移出** `/etc/rcS.d/`：

```sh
mkdir -p /etc/rcS.d.disabled
mv /etc/rcS.d/S99board /etc/rcS.d.disabled/
```

`chmod -x` 在 Debian 风格的 `rc` 里也有效（它检查 `-x`），但**本板的 `rc` 是否检查可执行位尚未实测**，不要依赖。

### 2.2 新模式：位流与 overlay 由同一个变量选定

旧脚本写死显示路径，切射频只能手工改文件，容易把位流和 overlay 配错。新脚本从 `/etc/board-mode` 读模式：

| 模式 | 位流 | overlay | 谁加载位流 |
|---|---|---|---|
| `display` | `display.bin` | `d480p.dtbo` | overlay 里的 `firmware-name=system_wrapper.bin` 自动加载 |
| `rf` | `ad9361.bin` | `pl.dtbo` | **脚本显式加载**（`pl.dtbo` 没有 `firmware-name`） |

两种模式都把选中的位流暂存为 `/lib/firmware/system_wrapper.bin`，因为显示 overlay 硬编码了这个文件名。

**配对由代码保证**：位流和 overlay 都从同一个 `$MODE` 派生，不存在配错的可能。缺文件时脚本 **退出且不再往下走**（不会半配置 fabric）。

### 2.3 风扇与模式解耦

风扇是 **PS MIO8（gpio 914）**，与 PL 位流无关，所以放在 `case` 之外，**两种模式都会开**。

## 3. 备份恢复时的部署参考（已部署，常规重连不重复执行）

前提：板上已有以下文件（`ls -l /lib/firmware` 核对）

| 文件 | 字节 | sha256 |
|---|---:|---|
| `display.bin` | 3,346,176 | `12566368b747728d00dda1e6774ff708b3d1a67fa37b38268bdaa8957f11286e` |
| `ad9361.bin` | 17,416,348 | `65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a` |
| `d480p.dtbo` | 4,712 | `7e740c420973a09630575c416f7acf8ab74ff91a9fd058e6227e09eccd4d03f5` |
| `pl.dtbo` | 8,201 | （原厂，未改） |

```sh
# 1. 现有文件名已经在 HW-008 部署并验证，不要重复规范化
cd /lib/firmware
sha256sum display.bin ad9361.bin
# 与上表核对；system_wrapper.bin 会随模式变化，不能盲目复制成 display.bin

# 2. 安装新脚本与模式工具（用 experiments/p15_serial_send.py 上传，base64 + sha256 校验）
chmod 755 /etc/rcS.d/S99board /usr/bin/board-mode

# 3. 设定初始模式
echo display > /etc/board-mode

# 4. 确认旧脚本已被新脚本替换（不要两个都在）
ls /etc/rcS.d/ | grep -i board     # 只应有 S99board
```

## 4. 切换模式的用法

```sh
board-mode            # 打印当前模式
board-mode rf         # 写 /etc/board-mode，重启后生效
reboot                # 开机脚本按模式配对位流与 overlay，风扇照常开
```

切到 `rf` 后验收：

```sh
cat /sys/class/fpga_manager/fpga0/state    # operating
iio_info -s                                # 应出现 ad9361-phy 与 cf-ad9361-lpc
```

切回 `display` 后验收：

```sh
cat /sys/class/fpga_manager/fpga0/state    # operating
ls /dev/fb0                                # 存在
```

## 5. 当前验收（HW-007/HW-008 已更新，HW-014 复核文档）

| 项目 | 状态 |
|---|---|
| 新模式脚本的实际部署 | 通过：p17-mode-install 原始日志及哈希 |
| 显示 → 射频 → 显示 **完整往返** | 通过：HW-008 三次启动日志 |
| `display.bin` / `ad9361.bin` 成对加载 | 通过：HW-008 两模式的终检 |
| 移出 `/etc/rcS.d/` 的停用方式 | ❌ 未实测（按 sysvinit 语义推断） |
| `99touch`/pointercal 在**重启后**是否自动生效 | 通过：HW-007 最终日志；本轮没有再次重启 |
| 触摸精度（四点标定量化） | ❌ 未做 |

上述通过项可引用对应实验记录；RF 与显示同时工作仍未实现。其他启动条件下自动标定是否覆盖配置、触摸量化精度仍不能扩大声明。最新入口见 [START-HERE](../start-here.md)。

---

## 6. 触摸持久化：四个缺陷与最终方案（2026-10-17 上板闭环）

完整记录见 [EXP-HW-007](../docs/experiments/exp-hw-007-touch-persistence.md)。这里只放**别的脚本作者必须知道的三条**。

### 6.1 绝不能在这类脚本里写 `exit`

`/etc/X11/Xsession` 用 `. $SYSSESSIONDIR/$SESSIONFILE` **source** `Xsession.d` 下的脚本。我第一版以 `exit 0` 结尾，直接把整个会话脚本终止，桌面永远起不来，`xinit` 见客户端消失就关掉 X。日志里只有一句：

```
xinit: connection to X server lost
```

**三类钩子的语义不同，别混**：

| 目录 | 谁执行 | 方式 | 能不能 `exit` |
|---|---|---|---|
| `/etc/X11/Xsession.d/` | `xinit /etc/X11/Xsession` | **source** | ❌ 绝不能 |
| `/etc/X11/Xinit.d/` | `/etc/X11/Xinit`（本板启动路径**不使用**） | `exec run-parts`（执行） | 可以，但本条路径是惰性的 |
| `/etc/rcS.d/` | `rcS` → `rc` | 执行 | 可以 |

`board/boot/99touch` 现在**一条 `exit` 都没有**（有断言检查），失败只记日志。

### 6.2 上传后必须补执行位

`Xsession.d` 循环里有 `if [ -x ... ]`。base64 上传得到的文件是 **644**，于是"文件在、内容对、却静默不执行"。症状是日志里没有任何该脚本的输出。

**部署清单**：上传 → `chmod 755` → 用 `grep <脚本前缀> /var/log/Xsession.log` 确认日志里有输出。

### 6.3 真正的标定来源是 `/etc/pointercal.xinput`

X 会打印 `Using calibration data stored in /etc/pointercal.xinput` 并**每次会话加载它**。该文件曾被 `30xTs_Calibrate.sh` / `30xinput_calibrate.sh` 写入**退化值**（`2915, 2915, 2759, 2662`），导致每帧刷 `Divide by Zero in xf86ScaleAxis`。

现在是两层防护：

| 层 | 文件 | 作用 |
|---|---|---|
| 主 | `/etc/pointercal.xinput`（`ac12ce208d50`，222 B） | X 启动时直接加载正确值 |
| 兜底 | `Xsession.d/99touch`（排在 `ls -X` 最后） | 无论前面怎么改，最后纠正一次 |

原坏文件保留为 `/etc/pointercal.xinput.bad`。

## 7. 历史文件清单（2026-10-17，当前以第1节和HW-023为准）

| 文件 | 字节 | sha256（前 12 位） | 状态 |
|---|---:|---|---|
| `boot/S99board` | 7,382 | `2a5533091321` | HW-018历史重试版，已由HW-023的7961字节保护版替代，禁止重新部署 |
| `boot/S99board.deployed-20261017` | 1,596 | `c9a5b2649d6f` | 板上正在运行（固定显示模式） |
| `boot/board-mode` | 1,238 | `8ab1978e375a` | 新，未部署 |
| `boot/99touch` | 3,025 | `78a99f915c88` | **已部署并已验证重启生效** |
| `boot/pointercal.xinput` | 222 | `ac12ce208d50` | **已部署**（替换了退化值） |
| `boot/S99fan.superseded` | 795 | `00ccaacb2de9` | 已作废 |
| `touch-captures/*.txt` | — | — | 触摸原始事件（3 份） |

## 8. 已验证 / 未验证（2026-10-17 深夜更新）

**已验证（有 transcript）**：

- 显示自启：`state=operating`、`/dev/fb0`、`gpio914=out`、dmesg 含 `fb0: frame buffer device` 与 `100x30` → `results/p16e-autostart-20261017/`
- 触摸反相与标定重启后生效：`243 = 0, 1`、`244 = 0, 4095, 0, 4095`、`Divide by Zero` 由 70 → **0**、X 存活 → `results/p16e-touch-final-20261017/`

**仍未验证**：

- **人工点击**（属性对 ≠ 指哪点哪）
- 新模式脚本 `S99board` 的部署与模式往返
- `/etc/pointercal` 缺失时自动标定是否会再次覆盖 `pointercal.xinput`（本轮靠 99touch 兜底，未验证兜底是否足够）
