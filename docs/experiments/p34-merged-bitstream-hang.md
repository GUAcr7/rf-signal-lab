# P34：合并位流首次上板失败 —— 挂死与恢复全过程

> **P35审查更正（2026-10-21）**：本次失联现象和恢复过程保留，但“串口静默等于总线死锁”“CDC已证实导致挂死”“已完全恢复无残留”不能仅由本文证据成立。后续P34恢复未确认；P35已实测串口可响应、默认磁盘文件仍是试验版本，并完成哈希核验后的厂家文件恢复。当前状态及补充RX实测见[本轮纠错记录](exp-hw-025-review-corrections-and-ttl.md)。

- 日期：2026-10-20 22:00–22:33（北京时间）
- 状态：**失败已确认；板子已完全恢复；失败原因尚未定位**
- 目的：把"射频 + 显示合并进同一个 PL"首次放到真实硬件上检验。

**一句话结论：静态检查全部通过的合并位流，一应用就让整块板子无声挂死；没有任何内核日志，属于总线级死锁。已用 U-Boot 的 `ext4write` 恢复厂家配置。**

## 1. 做了什么

| 步骤 | 内容 |
|---|---|
| 位流 | `rf-display-p32.bin`（5,034,572 B，sha256 `96c5d8f3…`）串口上传，耗时 **12.5 分钟**，哈希校验一致 |
| overlay | `rf-display-p32.dtbo`（11,544 B，sha256 `826756c5…`） |
| 安装 | 位流 → `/lib/firmware/rf-display-p32.bin`；overlay → `/lib/firmware/d480p.dtbo` |
| 备份 | 厂家原 `d480p.dtbo`（4,712 B，sha256 `7e740c42…`）→ `d480p.dtbo.vendor-backup` |
| 重启 | `board-mode=display`，S99board 按显示模式加载 |

选择替换 `d480p.dtbo` 而不是改 `S99board`：显示模式的位流由 overlay 的 `firmware-name` 触发加载，我们的 overlay 正好带这个属性，所以是**最小改动、可逆**的做法。

## 2. 挂死现场

启动日志正常走到：

```
board-init: mode=display bitstream=/lib/firmware/display.bin overlay=/lib/firmware/d480p.dtbo
board-init: staged bitstream already current
```

**然后整机再无输出。**

`S99board` 在那两行之后的动作是：

```sh
mkdir -p /sys/kernel/config/device-tree/overlays/pl
cat "$OVERLAY" > .../pl/dtbo        # ← 在这里挂死
```

这个 `cat` 会触发 **PL 重新配置 + overlay 里所有设备节点 probe**（AD9361、VDMA、DRM、TTC PWM）。

### 为什么判定是"总线级死锁"而不是内核崩溃

| 判据 | 观察 |
|---|---|
| 内核 panic/oops | **没有**。若有会打印调用栈 |
| 看门狗 | 内核看门狗 10 s 超时本应复位，但板子保持静默（说明 PS 已无法执行到喂狗/中断） |
| 串口 | 物理串口三次探测均 **0 字节**，连 U-Boot 都不会自动重来 |
| 现象 | 完全静默 = Cortex-A9 停在 AXI 事务上，或时钟/复位被 PL 拽住 |

## 3. 恢复过程（已成功）

### 3.1 关键发现：U-Boot 只能按空格打断，窗口仅 1 秒

```
Hit <SPACE> key to stop autoboot in  1s
Zynq>
```

我前两次抢不到控制权，是因为一直发**回车**；U-Boot 要的是**空格**，且 `bootdelay=1`。

### 3.2 用 U-Boot 直接恢复文件，不启动 Linux

```
ext4load mmc 0:2 0x2000000 /lib/firmware/d480p.dtbo.vendor-backup
  -> 4712 bytes read
ext4write mmc 0:2 0x2000000 /lib/firmware/d480p.dtbo 0x1268
  -> Recovery required / file found, deleting / 4712 bytes written
ext4load mmc 0:2 0x2100000 /lib/firmware/d480p.dtbo
  -> 4712 bytes read
reset
```

（`0x1268` = 4712 字节）

### 3.3 恢复验证

| 项 | 结果 |
|---|---|
| `board-mode` | `display` |
| `/lib/firmware/d480p.dtbo` | 4,712 B |
| sha256 | **`7e740c420973a09630575c416f7acf8ab74ff91a9fd058e6227e09eccd4d03f5`**（与厂家原值一致） |
| `/dev/fb0` | 存在 |
| IIO | `iio:device0`（显示模式应有的状态） |
| shell | 正常响应 |

**板子已回到实验前状态，无残留影响。**

## 4. 这个失败推翻了什么

| 原本的判断 | 现在的证据 |
|---|---|
| "时序收敛 + DRC 0 错误 + 资源 7.87% ⇒ 可以上板试" | **不够**。这些都通过，照样把板子打死 |
| "58 项 CDC 是理论风险，可先上板再看" | **不是理论风险**，已证实会导致硬挂死 |
| "没做仿真也能先试" | 代价是两次挂死 + 一次 U-Boot 抢救 |

**这是本项目第一次出现"静态检查全绿但硬件直接挂死"的情况，值得写进方法学：合并设计必须有分阶段上板验证，不能一次性整体替换。**

## 5. 还没定位的原因（候选）

| 候选 | 依据 | 如何验证 |
|---|---|---|
| **AXI 主设备访问未映射地址** | 合并后 VDMA/AD9361 DMA 接在 HP0/HP1/HP2；地址或端口冲突会让互连锁死 | 只加载位流、不应用 overlay，看是否仍挂 |
| **CDC 问题导致状态机进入非法状态** | 58 项未收口 | 同上；再用 Vivado CDC 报告定位 |
| **时钟冲突（FCLK2 50 vs 250 MHz）** | p29 文档已记录该冲突 | 读回 SLCR 寄存器实际值 |
| **PL 引脚与关键接口冲突** | 显示 ILI/LVDS 引脚可能与其它功能复用 | 比对 XDC 与板级原理图 |
| **overlay 设备节点本身有问题** | 我们的 dtbo 是重建的，`reg` 有格式告警 | 只应用 overlay 不加载位流（但 firmware-name 会强制加载） |

**最干净的下一步是二分法：只加载位流、不应用 overlay。**

```sh
echo rf-display-p32.bin > /sys/class/fpga_manager/fpga0/firmware
cat /sys/class/fpga_manager/fpga0/state
```

- 若**挂死** ⇒ 问题在 PL 本身（CDC / AXI / 时钟）
- 若**存活** ⇒ 问题在 overlay 的设备节点（设备树重建有误）

这个实验只需 5 MB 已在板的位流，**无需重新上传**，且恢复手段已验证。

## 6. 证据

| 内容 | 路径 |
|---|---|
| 上传与哈希 | `results/p34-pre-deploy-state-20261020/`、部署包 README |
| 安装记录 | `results/p34-install-merged-20261020/` |
| **挂死现场启动日志** | `results/p34-verify-merged-20261020/`（另有完整 16 KB 抓取） |
| 恢复验证 | `results/p34-recovery-verify-20261020/` |
| 部署包（保留，便于重试） | `results/p34-deploy-package/` |

## 7. 现在的板子状态与遗留

- 板子：显示模式，厂家 overlay，正常工作
- `/lib/firmware/rf-display-p32.bin` **仍留在板上**（5 MB，未被引用）—— 保留以便重试，不占内存（SD 卡 4.6 GB 空闲）
- `d480p.dtbo.vendor-backup` 仍在，可再次用于恢复
- 我们的 dtbo 已被覆盖，但电脑上有完整副本

**注意**：以后再动 `/lib/firmware/d480p.dtbo` 之前，先确认 U-Boot 的 `ext4write` 可用 —— 这是唯一可靠的恢复手段（SD 卡拔下来接 Windows 无法写 ext4）。
