# EXP-HW-007：触摸持久化闭环 —— 四个真实缺陷的定位与修复

- 日期：2026-10-17 深夜（板卡已上电，实测）。
- 承接 [EXP-HW-006](exp-hw-006-tlz7xh-display-and-fan.md)（屏幕点亮、风扇、触摸初修）。
- 本轮目标：把 `EXP-HW-006` 里唯一未闭环的"触摸重启后是否自动生效"验到底。
- **结果：已闭环。** 重启后 `243 = 0, 1`、`244 = 0, 4095, 0, 4095`、`Divide by Zero` 从 70 降到 **0**、X 存活。
- 本轮性质：**真实上板实测**，含多次重启。所有结论均有 `results/p16e-*` 下的 transcript。

## 1. 结论摘要

| 项 | 状态 |
|---|---|
| 显示自启（PL 位流 + fb0 + 风扇） | ✅ 已归档证据（`results/p16e-autostart-20261017/`） |
| 触摸反相持久化 | ✅ 已验证 |
| 触摸标定持久化 | ✅ 已验证 |
| 桌面会话存活 | ✅ 已验证（Xorg pid 1358） |
| 触摸点击的可用性（人工点击） | ⏳ **未做人工点击测试**，只验证了属性与警告计数 |

## 2. 四个真实缺陷（按发现顺序）

### 缺陷 1：`p15_serial_read.py` 没有 `--evidence`

我在 `EXP-HW-006` §11 里写了 `--evidence` 选项，**但那个工具根本没有这个参数** —— 又一次"文档声称了代码没有的能力"，而这正是当初显示/自启证据丢失的原因（当时用的就是这个工具、无归档）。

**修复**：给 `p15_serial_read.py` 实现 `--evidence`，写 `transcript.json`（schema `rfsig.serial_read_transcript.v1`），并记录每条命令是否疑似停在续行提示符。

### 缺陷 2：`exit 0` 把整个桌面会话杀掉

`/etc/X11/Xsession` 的结尾是：

```sh
SESSIONFILES=`ls -X $SYSSESSIONDIR`
if [ -n "$SESSIONFILES" ]; then
  for SESSIONFILE in $SESSIONFILES; do
    if [ -x "$SYSSESSIONDIR/$SESSIONFILE" ]; then
      . $SYSSESSIONDIR/$SESSIONFILE      # ← source，不是执行
    fi
  done
fi
exit 0
```

脚本是**被 source** 的。我第一版 `99touch` 以 `exit 0` 结尾（另有一条 `exit 1`），于是：

- `exit 0` 直接终止 `/etc/X11/Xsession`
- 窗口管理器永远没机会启动
- `xinit` 发现客户端消失 → 关掉 X

现象（`/var/log/Xsession.log`）：

```
touch-cal: calibration set: 0, 4095, 0, 4095
touch-cal: inversion set: 0, 1
xinit: connection to X server lost
waiting for X server to shut down (II) Server terminated successfully (0).
```

之前桌面能用，是因为那时**还没部署这个脚本**。

**修复**：`99touch` 内**一条 `exit` 都没有**（已用脚本断言 `^\s*exit\b` 计数为 0），失败只记日志。辅助函数用 `return 0` 并且只在函数内部。

### 缺陷 3：重新上传丢掉执行位，Xsession 直接跳过

`/etc/X11/Xsession` 的循环有 `if [ -x ... ]` 检查。我用 base64 上传后文件是 **644**；`chmod 755` 之后**又上传了一次**，执行位再次丢失。

结果：脚本存在、内容正确，但**根本没被执行** —— 表现为 `grep touch-cal /var/log/Xsession.log` **完全为空**，而同一目录的 `89xdgautostart.sh` 有输出（说明循环确实在跑）。

**修复**：每次上传后必须 `chmod 755`；已把这条写进 `board/README.md` 的部署步骤，并在 `board/boot/99touch` 头部注明。

### 缺陷 4（根因）：`/etc/pointercal.xinput` 被写入了退化标定

`/var/log/Xsession.log` 里有一行关键提示：

```
Using calibration data stored in /etc/pointercal.xinput
```

该文件内容（156 B，mtime 正好是我上一轮折腾触摸的时间）：

```
xinput set-int-prop "ADS7846 Touchscreen" "Evdev Axis Calibration" 32 2915 2915 2759 2662; xinput set-int-prop "ADS7846 Touchscreen" "Evdev Axes Swap" 8 0;
```

**这就是退化标定的来源**：`Xsession.d/30xTs_Calibrate.sh` 与 `30xinput_calibrate.sh` 在没有 `/etc/pointercal` 时会跑一次自动标定，而**当时触摸还不可用**，于是把垃圾值写进了这个文件。X 每次会话启动都从这里加载，于是：

- 我手动设的 `244` 在**下一次会话**又被覆盖回退化值
- 每帧都刷 `Divide by Zero in xf86ScaleAxis`（**70 条**）

**修复（两层）**：

1. **主层**：把 `/etc/pointercal.xinput` 改写为正确值，并保留原文件为 `/etc/pointercal.xinput.bad`：
   ```
   xinput set-int-prop "ADS7846 Touchscreen" "Evdev Axis Calibration" 32 0 4095 0 4095; xinput set-int-prop "ADS7846 Touchscreen" "Evdev Axes Swap" 8 0; xinput set-int-prop "ADS7846 Touchscreen" "Evdev Axis Inversion" 8 0 1;
   ```
   sha256 `ac12ce208d50718aee4fb5633dd5b687101434fba9bd08b15b4fdc7dd43a9f20`
2. **备份层**：`99touch` 排在 `ls -X` 顺序的最后（`30…` → `99touch`），无论前面怎么改，它最后都会把值纠正过来。

**这解释了为什么之前"手工设好、重启又坏"** —— 不是我的钩子没跑，而是跑的先后顺序与来源文件都在跟我作对。

## 3. 另外两处纠正

### 3.1 桌面不是 LXDE，是 XFCE

日志里是 `xfce4-session`、`xfsettingsd`、`x-session-manager`、`xfce4-session-WARNING`，还有 `/home/root/.cache/sessions/xfce4-session-Zynq-Tronlong:0`。

**我此前在 6 处文档里写成 "LXDE"，是错的**（应为 XFCE）。已逐处更正。

### 3.2 `/etc/X11/Xinit.d/` 对这条启动路径是无效的

- `xserver-nodm` 实际执行的是 `xinit /etc/X11/Xsession -- Xorg …`
- `/etc/X11/Xinit` 是**另一个**客户端脚本（末尾 `exec run-parts /etc/X11/Xinit.d`），**不被这条路径使用**
- `Xsession.d` 才是生效目录，且脚本被 **source**

所以 `Xinit.d/95touch` 是**惰性**的（保留无害，但别指望它）。真正起作用的是 `Xsession.d/99touch`。

## 4. 验收证据

| 内容 | 路径 |
|---|---|
| 自启（PL/fb0/风扇/dmesg 含 `fb0` 与 `100x30`） | `results/p16e-autostart-20261017/transcript.json` |
| 触摸属性（修复前：`244` 退化） | `results/p16e-touch-20261017/transcript.json` |
| 脚本 v1 手动成功 | `results/p16e-touch-manual-20261017/` |
| 脚本 v2（带 exit）在 X 启动时成功但会话被杀 | `results/p16e-xsession-log-20261017/` |
| X 未起（exit bug 复现） | `results/p16e-x-reboot2-20261017/`、`p16e-x-manual-start-20261017/` |
| 发现 `pointercal.xinput` 与执行位丢失 | `results/p16e-touchcal-log-20261017/`、`p16e-pointercal-20261017/` |
| 修正 `pointercal.xinput` | `results/p16e-pointercal-fixed-20261017/` |
| **最终重启验收** | **`results/p16e-touch-final-20261017/transcript.json`** |

最终验收读数：

```
$ pgrep -l X
1358 Xorg
$ DISPLAY=:0 xinput list-props 6 | grep -E '243|244'
	Evdev Axis Inversion (243):	0, 1
	Evdev Axis Calibration (244):	0, 4095, 0, 4095
$ grep -c 'Divide by Zero' /var/log/Xsession.log
0
$ grep touch-cal /var/log/Xsession.log | tail -3
touch-cal: calibration set: 0, 4095, 0, 4095
touch-cal: inversion set: 0, 1
```

## 5. 未验证

- **人工点击**：没有让用户实际点一个按钮来确认"指哪点哪"。属性正确 + 浮点告警归零是强证据，但**不等于点击可用**。
- `/etc/pointercal.xinput.bad` 是否会在下次自动标定时**再次被覆盖**：`30xinput_calibrate.sh` 只在缺 `/etc/pointercal` 时运行；`/etc/pointercal` 仍不存在，所以**理论上仍可能重跑**。本轮靠 `99touch` 兜底，但没有验证"自动标定重跑后仍能恢复"。

## 6. 教训（这一轮最值钱的部分）

1. **"没有 exit 的脚本必须真的没有 exit"** —— source 型钩子里两条 `exit` 就足以让整个桌面消失，而且报错只有一句 `connection to X server lost`，极难联想到是自己的脚本。
2. **上传后必须补执行位**，而 `-x` 检查会让"文件在、内容对、却没运行"变得静默。
3. **厂商的自动标定会写出垃圾值** —— 在触摸不可用时触发自动标定，等于把错误固化进配置文件，而且是**每次会话重新加载**。
4. **`--evidence` 不是装饰** —— 本轮之所以能一步步定位，全靠每次操作都落 transcript；而当初显示证据丢失，正是因为工具没有这个能力。
5. **我连续三次对外声称了"已验证"而实际没验证**（显示、自启、触摸）。这轮把三者的证据补齐，代价是多花了一整天。
