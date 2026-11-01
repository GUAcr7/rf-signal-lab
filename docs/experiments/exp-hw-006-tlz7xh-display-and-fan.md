# EXP-HW-006：TLZ7xH-EVM 屏幕点亮与风扇常开（含开机自启）

> ## ⚠️ 证据缺口声明（2026-10-17 独立审查后追加，请先读）
>
> **本文关于"显示"与"开机自启"的验收，证据没有归档。**
>
> 当时是通过 `experiments/p15_serial_read.py` 在串口上直接读的，而那个工具**不写 transcript 文件**。所以内核里的 `xilinx-drm ... fb0: frame buffer device`、`Console: switching to colour frame buffer device 100x30`、以及重启后的 `state=operating` / `/dev/fb0` / `gpio914=direction out`，**只存在于对话记录，没有落地证据文件**。
>
> 已逐目录核查 `results/p15-newboard-*/`：仅 `p15-newboard-pl-state-20261017/transcript.json` 出现过 `[drm] Initialized`，那是**加载显示位流之前**的早期探测，不含 `fb0`，不能作为显示成功的证据。
>
> 因此本文 §1.4 的"验收读数"与 §3.3 的"重启验证"应读作**已观察、待归档**，按项目证据约定等价于"未归档、待补"。**不得对外宣称这两项已验收。**
>
> 补齐办法见 §11：下次上电时用带 `--evidence` 的工具一次跑完并落盘。

- 日期：2026-10-17。
- 承接 [EXP-HW-005](exp-hw-005-tlz7xh-bringup.md)（板卡识别与 AD9361 接收链打通）。
- 本轮目标：①让屏幕出画面；②让风扇可控；③两者都做成**开机自动**。
- 验收标准（事先定好）：①屏幕有可判读的画面（不是只有背光）；②风扇按文档方式可控；③**断电重启后不依赖人工操作**即可恢复。
- 本轮性质：**修改了板上的 `/lib/firmware/` 与 `/etc/rcS.d/`**。这是本轮区别于前几轮只读探测的地方，所有改动都有备份与回滚步骤（第 6 节）。

## 1. 屏幕：已点亮

### 1.1 为什么之前是黑的

`fpga0/state` 为 `unknown` —— **PL 未配置**。LCD 的数据线全部来自 PL 引脚，没有位流就没有任何东西驱动它们，屏幕只有背光。

板上随附的 `/lib/firmware/system_wrapper.bin` 是 **AD9361 射频设计**，`pl.dtbo` 里只有 `ad9361-phy` / `cf-ad9361-lpc` / `axi-dmac`，**没有任何显示节点**。所以"装了射频位流"和"屏幕亮"是互斥的。

### 1.2 显示 demo 的组成（来自 `Demo.zip`）

| 文件 | 大小 | 作用 |
|---|---:|---|
| `axi_video_display_demo_xc7z100.bin` | 3,346,176 B | 显示位流（VDMA + VTC + CLK Wizard + LCD/HDMI 输出） |
| `axi-video-display-480p.dtbo` | 4,712 B | 800×480 overlay，**内含 `firmware-name = "system_wrapper.bin"`，应用即自动加载位流** |
| `axi_vdma.sh` | 1,562 B | 裸 VDMA 寄存器配置（DRM 官方路径之外的备用手段） |
| `video_timing_config.sh` | 2,518 B | CLK Wizard + VTC 时序（备用手段） |
| `ttc_pwm_backlight.sh` | 187 B | 背光（备用手段） |

**overlay 的关键片段**：

```dts
fragment@0 { target = <&fpga_full>; __overlay__ { firmware-name = "system_wrapper.bin"; }; };
fragment@1 { target = <&amba>; __overlay__ { axi_vdma_0 / clk_wiz_0 / v_tc_0 / xilinx_drm / ttc0_pwm }; };
fragment@2 { target-path = "/"; __overlay__ { lcd_bl: backlight { compatible = "pwm-backlight"; ... }; }; };
```

`xilinx_drm` 里声明了 `xlnx,connector-type = "VGA"`、`xlnx,pixel-format = "argb8888"`、VDMA 作为 plane。

### 1.3 点亮步骤（已实测）

```sh
# 1. 用显示位流替换 system_wrapper.bin（overlay 会按这个名字加载）
cp /tmp/display.bin /lib/firmware/system_wrapper.bin
cp /tmp/display480p.dtbo /lib/firmware/d480p.dtbo

# 2. 重启（让 PL 回到未配置状态，避免在 ad9361 驱动仍绑定时重配 PL）
reboot

# 3. 应用 overlay —— 这一步会顺带加载位流
mount -t configfs none /sys/kernel/config
mkdir -p /sys/kernel/config/device-tree/overlays/pl
cat /lib/firmware/d480p.dtbo > /sys/kernel/config/device-tree/overlays/pl/dtbo
```

内核日志（成功判据）：

```
fpga_manager fpga0: writing system_wrapper.bin to Xilinx Zynq FPGA Manager
fpga_manager fpga0: Found swapped sync word
xilinx-vdma 43000000.dma: Xilinx AXI VDMA Engine Driver Probed!!
Console: switching to colour frame buffer device 100x30
xilinx-drm amba:xilinx_drm: fb0:  frame buffer device
[drm] Initialized xilinx_drm 1.0.0 20130509 on minor 0
pwm-cadence f8001000.ttc_pwm: PWM 0 has clock source 0 at 111111115 Hz
backlight supply power not found, using dummy regulator
```

### 1.4 验收读数

| 项目 | 值 | 意义 |
|---|---|---|
| `fpga0/state` | `operating` | 位流已配置 |
| `/dev/fb0` | 存在 | 帧缓冲 |
| `/dev/dri/card0` | 存在 | DRM 设备 |
| `fb0/virtual_size` | **800,960** | 宽度 800 = 面板原生分辨率 |
| `fb0/bits_per_pixel` | **32** | ARGB8888，与 overlay 的 `argb8888` 一致 |
| `fb0/stride` | **3200** | = 800×4，无额外填充 |
| `Console: ... 100x30` | — | 800/8 = 100 列，480/16 = 30 行，**时序与分辨率吻合** |
| `backlight/max_brightness` | **8**，当前 **8** | 背光已满 |

**物理现象**（用户确认）：把 framebuffer 整片填 `0xFF`（1,536,000 字节 = 800×480×4）后，**屏幕整片变白**。这是端到端判据：像素真的走到了面板上。

### 1.5 附带打通的东西

`cat /sys/kernel/debug/gpio` 里出现：

```
 gpio-960 ( |ads7846_pendown ) in hi IRQ
```

**`ads7846` 就是 XPT2046 电阻触摸控制器** —— 触摸中断引脚已注册，说明 `TL-70RESLCD-B2` 的触摸链路也跟着 overlay 一起起来了。**触摸尚未做功能验证**，只确认了驱动绑定。

## 2. 风扇：已可控且可常开

### 2.1 硬件依据

- 原理图第 9 页（`JTAG/KEY/SRST/LED/FAN`）：`J3`（Molex 22-23-2031，3pin）为风扇座，电源取自 `VDD_12V_MAIN`，经 **`Q7`（PMOS `DMP4051LK3-13`）** 开关，由 **`Q5`（`MMBT3904`）** 驱动。
- 原理图第 1 页修订记录：`Q8 is changed to NMOS instead of Transistor`、`Modify Q8 to MOSFET symbol` —— 说明这一块被改过，注意以当前版本为准。
- 硬件说明书第 26 节：**`J3` 为散热器风扇电源接口，3pin，12V 供电**；且
  > 风扇电路及风扇接口**不支持调速功能**，不建议使用 PWM 模式控制风扇开关电路。
  > 评估底板采用 **PS_MIO8_500** 控制风扇，MIO8 与 BANK 501 电平配置有关。
- 测试手册 1.4 节给出完整步骤（**C21 引脚 = MIO8 = gpio 914**）：
  ```sh
  echo 914 > /sys/class/gpio/export
  echo out > /sys/class/gpio/gpio914/direction
  echo 0 > /sys/class/gpio/gpio914/value   # 风扇停止
  echo 1 > /sys/class/gpio/gpio914/value   # 风扇转动
  ```

### 2.2 执行结果与一个必须注意的坑

按手册执行时，**必须先设方向再写值**：

```
echo 914 > /sys/class/gpio/export          # ok
echo 1 > /sys/class/gpio/gpio914/value     # -sh: echo: write error: Operation not permitted
                                           # 因为导出后默认 direction = in
echo out > /sys/class/gpio/gpio914/direction   # ok
echo 1 > /sys/class/gpio/gpio914/value     # ok（无报错）
```

**但 `cat value` 仍然读回 0**，`/sys/kernel/debug/gpio` 也显示 `gpio-914 ( |sysfs ) out lo`。

**这个读回值不可当作"风扇没转"的依据**：Zynq 的 `value` 反映引脚实际电平（DATA_RO），而 MIO8 驱动的是 `MMBT3904` 基极（经 1K 电阻），基极会把引脚钳在约 0.7 V 附近，低于 3.3 V bank 的 VIH 门限，于是被判成低——但晶体管已经导通。

**判据只能用物理现象**：用户确认风扇已转。

`gpiochip906` 的 `base = 906`、`label = zynq_gpio`、`ngpio = 118`，故 `gpio914 = 906 + 8 = MIO8`，映射正确。

### 2.3 为什么需要开机自启

GPIO 的 `export` / `direction` / `value` 全是**运行时状态**，掉电或重启后 MIO8 复位为输入低电平，风扇停。**"设一次就永久生效"是不成立的。**

## 3. 开机自启：`/etc/rcS.d/S99board`

### 3.1 位置选择依据

- `/proc/1/comm` = `init`（BusyBox sysvinit）
- `/etc/rc.local` **不存在**
- `/etc/init.d/rcS` 末尾是 `exec /etc/init.d/rc S`，即按序执行 `/etc/rcS.d/S*`
- 原本最后一项是 `S55bootmisc.sh`

因此新增 `/etc/rcS.d/S99board`，排在已有脚本之后。

### 3.2 脚本做什么

1. 挂 `configfs`（若未挂）
2. 若 `overlays/pl` 不存在，应用 `/lib/firmware/d480p.dtbo` → 自动加载显示位流
3. 导出并驱动 `gpio914`，风扇开

脚本 1,596 B，sha256 `c9a5b2649d6f3af592cc3b8a5aa606d3e7c1f2b1bea935cb02ec38270ba8a514`，已 `chmod 755`。

### 3.3 重启验证（无人干预）

`reboot` 后 50 秒检查，全部通过：

| 检查项 | 结果 |
|---|---|
| `fpga0/state` | **`operating`** |
| `/dev/fb0` | 存在 |
| `gpio914/direction` | **`out`** |
| `overlays/pl` | 存在 |

**即：断电重启后屏幕自动出画面、风扇自动转，不需要人工敲任何命令。**

## 4. 当前板卡状态（重要：射屏与射频互斥）

`/lib/firmware/` 现在是：

| 文件 | 大小 | 内容 |
|---|---:|---|
| `system_wrapper.bin` | 3,346,176 B | **显示位流**（当前生效） |
| `sw-ad9361.bak` | 17,416,348 B | **AD9361 射频位流备份** |
| `d480p.dtbo` | 4,712 B | 800×480 显示 overlay |
| `pl.dtbo` | 8,201 B | AD9361 overlay（原厂） |

**开机默认进显示模式，AD9361 不可用。**

## 5. 切回射频模式的方法（待验证）

```sh
# 1. 先停掉开机自启，否则重启又回到显示模式
mv /etc/rcS.d/S99board /etc/rcS.d/S99board.off

# 2. 还原 AD9361 位流
cp /lib/firmware/sw-ad9361.bak /lib/firmware/system_wrapper.bin

# 3. 重启后加载射频位流并应用射频 overlay
echo system_wrapper.bin > /sys/class/fpga_manager/fpga0/firmware
mount -t configfs none /sys/kernel/config
mkdir -p /sys/kernel/config/device-tree/overlays/rf
cat /lib/firmware/pl.dtbo > /sys/kernel/config/device-tree/overlays/rf/dtbo
iio_info -s          # 应重新出现 ad9361-phy 与 cf-ad9361-lpc
```

**本节的步骤是按已验证的机制组合出来的，尚未实际执行过一次完整往返。** 执行前应先记录当前可工作状态，便于回滚。

## 6. 改动清单与回滚

| 改动 | 位置 | 回滚 |
|---|---|---|
| 显示位流覆盖 | `/lib/firmware/system_wrapper.bin` | `cp /lib/firmware/sw-ad9361.bak /lib/firmware/system_wrapper.bin` |
| 新增显示 overlay | `/lib/firmware/d480p.dtbo` | `rm` |
| 新增开机脚本 | `/etc/rcS.d/S99board` | `rm /etc/rcS.d/S99board` |
| 新增脚本源与备份 | 本机 `tmp/new-board-xilinx-review/fan-boot/S99board` | — |

**未改动**：`pl.dtbo`、U-Boot、内核、设备树源、拨码开关、`boot.scr`。

## 7. 传输方法（3.3 MB 经串口）

板上没有 `uudecode`，只有 `base64`；控制台还会回显，且 tty 是 canonical 模式（行长上限约 4096，实测按 76 字符分行安全）。做法：

1. 先 `stty -echo` 关回显（否则流量翻倍）
2. `echo READY_FOR_DATA; base64 -d > <目标>`，等出现就绪标记再开始送
3. 按 76 字符分行、限制速率约 9 KB/s（无硬件流控，超速会丢字节）
4. 结尾送换行 + `Ctrl-D` 触发 EOF
5. 用 `sha256sum` 校验

实测：**4,520,273 线字节 / 8.3 分钟**，sha256 与 PC 侧一致。工具：`experiments/p15_serial_send.py`。

**先拿一个 1,562 B 的真实文件做冒烟测试**再传大文件，这个顺序省掉了"传 8 分钟才发现机制有 bug"的风险。

## 8. 证据

| 内容 | 路径 |
|---|---|
| 传输前板卡状态 | `results/p15-newboard-preload-20261017/` |
| 位流加载（第一次错误方式 + 正确方式） | `results/p15-newboard-load-pl-check-20261017/`（含 `\xff` 被当文件名、state 为 `firmware request error` 的记录）、`p15-newboard-load-pl2-20261017/`（正确方式，`state = operating`） |
| AD9361 overlay 应用（射频链路） | `results/p15-newboard-overlay-apply-20261017/` |
| 显示 overlay 应用（本文件第 1 节） | 串口记录见本轮会话；关键内核日志已抄录于 1.3 |
| 原理图风扇电路文本 | `tmp/new-board-xilinx-review/schematic-text/page09.txt` |
| 开机脚本源 | `tmp/new-board-xilinx-review/fan-boot/S99board` |
| 显示 demo 原始文件与 dtsi | `tmp/new-board-xilinx-review/display-demo/` |

## 9. 待做

| 项目 | 说明 |
|---|---|
| 切回射频模式的完整往返验证 | 第 5 节步骤尚未实际跑通一次 |
| 触摸功能验证 | 驱动已绑定，未测触点坐标 |
| **屏幕显示实时频谱 / 星座** | 现在只是控制台文字与纯色填充；真正的 UI 要在 PS 上画图（DRM 或 fb0），素材与绘图程序尚无 |
| 射频与显示同时工作 | 需要自己综合一份合并 PL 设计；两个官方位流互斥（见 [新板审查](../design/new-board-tlz7xh-evm-review-20261017.md) 第 5 节） |

---

# 追加：屏幕已跑起 X11 桌面，触摸已修好并持久化

## A. 屏幕的实际状态（比预期更好）

加载显示位流后，屏幕上不是只有控制台文字，而是**完整的 XFCE 桌面**（X11）：

- 桌面图标：`Home`、`File System`、`Trash`
- 首次启动弹出面板配置对话框：`Welcome to the first start of the panel`
- 说明 `xserver-nodm` 在 runlevel 5 自动起了 X，整条链路（PL 位流 → xilinx_drm → fb0 → X → XFCE）都是通的

## B. 触摸：从"不能用"到"方向正确"

### B.1 关键判据先后搞错两次，都是我的测试方法问题

| 我的结论 | 实际 | 错在哪 |
|---|---|---|
| "触摸没产生任何事件" | **有事件** | 用 `od` 读字符设备，`od` 有输出缓冲，几十字节不 flush，`timeout` 又直接杀进程 |
| "可能是排线没接" | **接好了** | 笔中断 `gpio-960` 按下时确实由 `hi` 变 `lo` |
| "轴向交换了" | **没有交换** | 从点击数据的原始跨度反推（X 跨 1552、Y 跨 2723）得出的推断是错的；用户实测"左右正常"才是准的 |

**正确做法**：`timeout 15 dd if=/dev/input/event0 bs=16 count=8 | od -An -v -tx1` —— `dd` 精确读固定字节数，读到就退出，不依赖缓冲刷新。

### B.2 触摸一直是好的，坏的是 X 的标定

```
Evdev Axis Calibration (244):  2915, 2915, 2759, 2662
                               min_x  max_x  min_y  max_y
```

- X 轴：min == max == 2915 → **宽度为 0**
- Y 轴：min 2759 > max 2662 → **负宽度**

这种退化区间归一化时除以零/负数，指针位置发散。`/etc/pointercal` 不存在、`/etc/X11/xorg.conf.d` 也不存在，所以 X 用的是 evdev 派生的坏默认值。

### B.3 修复

```sh
DISPLAY=:0 xinput set-prop 6 244 0 4095 0 4095   # Evdev Axis Calibration
DISPLAY=:0 xinput set-prop 6 243 0 1             # Evdev Axis Inversion: X 正常，Y 反相
```

**用属性编号而不是属性名**：属性名含空格，经 PowerShell 5.1 的原生参数转引号会把它拆开（实测被拆成 `Axis` 和 `Calibration 0 4095 0 4095` 两条命令）。

### B.4 持久化（关键，否则一重启就丢）

`xinput set-prop` 是运行时状态。两个钩子各放一份：

| 文件 | 作用 | 大小 |
|---|---|---:|
| `/etc/X11/Xinit.d/95touch` | 随 X 启动执行（排在厂家 `89xTs_Calibrate` 之后） | 1,423 B |
| `/etc/X11/Xsession.d/99touch` | 若走 Xsession 路径也生效 | 1,423 B |

两份 sha256 相同：`3ab650136f39e678f8d647ca33af3c22978df7af70ba80f2cbe668b8dad53637`，均 `chmod 755`。

脚本用**设备名**匹配（`ADS7846 Touchscreen`）而不是属性编号，并先轮询等待设备出现，最多 10 秒。

**为什么不用 `xorg.conf.d` 的 InputClass**：那里写错选项可能导致 X 起不来；放在 Xinit.d 里失败最多是触摸没配好，X 照常启动。

### B.5 厂家预留的机制

- `/etc/X11/Xinit.d/89xTs_Calibrate`：若 `/etc/pointercal` 不存在且有 `TSLIB_TSDEVICE`，调用 `/usr/bin/run-calibrate.sh` 做交互标定
- `/etc/X11/Xsession` 第 27 行：`SYSSESSIONDIR=/etc/X11/Xsession.d`
- Qt 手册确认：**PL 端程序负责 LCD 显示与触摸控制管脚配置**，加载 dtbo 后应生成 `/dev/fb0` 与 `/dev/input/touchscreen0`（两者都已生成）

厂家路线是 **tslib + Qt**（`-plugin tslib`），不是 X11 evdev。本板跑的是 XFCE，所以走 evdev 这条路需要自己补标定。

## C. 重启后应自动恢复的三件事

| 功能 | 机制 | 已验证 |
|---|---|---|
| 显示（800×480 X11 桌面） | `/etc/rcS.d/S99board` 应用 `d480p.dtbo` → 自动加载显示位流 | ✅ 重启过一次并确认 `state=operating`、`/dev/fb0` 存在 |
| 风扇 | 同脚本驱动 `gpio914` | ✅ 同一轮重启确认 `direction=out` |
| **触摸方向修正** | `/etc/X11/Xinit.d/95touch` + `Xsession.d/99touch` | ⚠️ **尚未经过重启验证**（本轮结束前用户要断电） |

**C 表最后一项是本轮未闭环的地方**：脚本内容、权限、sha256 都核对过，也手工执行过（`DISPLAY=:0 sh /etc/X11/Xinit.d/95touch` 无报错，反相值确认为 `0, 1`），但**没有在真正重启后验证它是否被执行**。下次开机第一件事就是检查这一点。

## D. 证据

| 内容 | 路径 |
|---|---|
| 触摸原始事件解码 | `tmp/new-board-xilinx-review/tap-dump.txt`、`drag-dump.txt`、`diag-dump.txt` |
| 解码器 | `experiments/p15_decode_touch.py`（支持 `--trace` 逐样本打印） |
| 触摸持久化脚本源 | `tmp/new-board-xilinx-review/fan-boot/99touch` |

---

## 11. 下次上电一次补齐的证据采集脚本（2026-10-17 审查后新增）

**目标**：用一次上电把"显示、自启、触摸持久化"三项的证据全部落盘，避免再出现"看到了但没归档"。

### 11.1 采集命令（每一步都带 `--evidence`，会写 transcript.json）

```powershell
$P = "C:\Users\project_user\Documents\Codex\2026-09-09\2026-fpga-fmql30tai-fpai-python-c\outputs\rf-signal-lab"
$S = "$P\experiments\p15_serial_read.py"

# A. 开机后立即可查：自启是否生效
& python $S --port COM9 --evidence "$P\results\p16e-autostart-20261017" `
  "cat /sys/class/fpga_manager/fpga0/state" `
  "ls /dev/fb0" `
  "cat /sys/class/gpio/gpio914/direction" `
  "cat /sys/kernel/config/device-tree/overlays/pl/status" `
  "dmesg | grep -E 'xilinx-drm|fb0|Console: switching' | tail -6"

# B. 触摸：先验驱动与属性，再验反相是否被 Xinit.d 钩子设上
& python $S --port COM9 --evidence "$P\results\p16e-touch-20261017" `
  "cat /proc/bus/input/devices | grep -A4 ADS7846" `
  "DISPLAY=:0 xinput list --short" `
  "DISPLAY=:0 xinput list-props 6 | grep -E '243|244'"

# C. 触摸原始事件（dd 精确读，不用 od+timeout）
& python $S --port COM9 --evidence "$P\results\p16e-touch-raw-20261017" `
  "timeout 20 dd if=/dev/input/event0 bs=16 count=32 | od -An -v -tx1"
```

### 11.2 三项验收判据

| 项 | 判据 | 对应目录 |
|---|---|---|
| 自启 | `state=operating`、`/dev/fb0` 存在、`gpio914/direction=out`、`dmesg` 里有 `fb0: frame buffer device` 与 `100x30` | `p16e-autostart-*` |
| 触摸持久化 | `xinput list-props 6` 里 **243 = `0, 1`**（Y 反相）且 **244 = `0, 4095, 0, 4095`** | `p16e-touch-*` |
| 触摸数据 | `dd` 输出 ≥ 2 个完整样本（32 字节），含 `ABS_X`/`ABS_Y`/`ABS_PRESSURE` | `p16e-touch-raw-*` |

**只有这三项都落盘，才能把 §1.4、§3.3 与 C 表最后一项从"待补"改成"已验证"。**

### 11.3 顺带要补的（同一个上电窗口做完，省一次开机）

1. **模式往返**：`board-mode rf` → reboot → 采集 → `board-mode display` → reboot → 采集（两次都要 `--evidence`）
2. **旧板五步恢复**：按 [START-HERE](../../start-here.md) 的五步清单逐条执行并留证
3. **新板真实 I/Q**：切 rf 模式后 `iio_readdev -b 4096 -s 65536 cf-ad9361-lpc > /tmp/seg.bin`，再取回并做格式统计
