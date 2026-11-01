# 2026-10-21 16:20 任务完成情况检测

- 检测人：本次会话（P34 那一线）
- 触发：用户要求"检测当前任务的完成情况"
- 方式：**实测**，不是复述记录。板子串口、固件哈希、测试套件、别人新写的文档都重新核对。

## 1. 板子当前实际状态（本次实测）

| 项 | 实测值 |
|---|---|
| 串口 | **可响应**（与 START-HERE 里"COM8 无回应"不同，那是 16:14 的旧状态） |
| boot_id | `58d8ed5c-2d12-49e1-a221-3ca78a6aca75`（**新**，与 P36 的 `1263532f…` 不同） |
| uptime | 检测时 83 秒 → **板子 16:21 左右刚重启过** |
| 模式 | `rf` |
| `fpga_manager` | `operating` |
| IIO | **只有 `iio:device0`（xadc）** |
| `/dev/fb0` | 不存在（rf 模式正常） |

### 固件哈希（全部为厂家原值，无残留）

| 文件 | sha256 | 判定 |
|---|---|---|
| `ad9361.bin` | `65b44449b074bd1f497c1989ca0ee3a519fba5bfe5554eb04b06e4de9cf2950a` | ✅ 厂家 RF 位流 |
| `system_wrapper.bin` | 同上（rf 模式 staging 结果） | ✅ 正常 |
| `display.bin` | `12566368…`，3,346,176 B，前缀 `ff ff…` | ✅ 厂家显示位流 |
| `d480p.dtbo` | `7e740c420973a09630575c416f7acf8ab74ff91a9fd058e6227e09eccd4d03f5` | ✅ 厂家 |
| `pl.dtbo` | `434855ac…` | ✅ 厂家 |

**结论：文件层面是干净的厂家状态，昨晚那次未完成的恢复实际上已经由后续会话补齐。**

### 但射频 bring-up 失败

```
board-init: mode=rf bitstream=/lib/firmware/ad9361.bin overlay=/lib/firmware/pl.dtbo
fpga_manager fpga0: Found swapped sync word
board-init: fabric operating after explicit bitstream load
ad9361 spi32765.0: ad9361_probe : enter (ad9361)
ad9361 spi32765.0: ad9361_probe : Unsupported PRODUCT_ID 0xFF
board-init: overlay applied: /lib/firmware/pl.dtbo (attempt 1)
board-init: FAILED: incomplete PHY/ADC/DDS; hot removal disabled; reboot required
```

这是项目已记录的**冷启动间歇 `0xFF` 故障**（约 1/4 概率），不是新问题。固件正确、位流已加载，只是这次 probe 撞上了。

**处理：普通重启一次即可**（项目规矩：禁止热卸载/热重绑）。

## 2. 新发现的实质问题：4 MiB 完整采集已丢失

P36 在板上保存了完整 4 MiB 返回缓冲：

- `raw_bytes = 4,194,304`、`raw_sha256 = 8eec20a1…`
- 板端路径 `/tmp/p36-full-032307/iq-packed.bin.gz`（1,725,989 B）
- 电脑只回传 **15/53 块**

**本次实测：该目录不存在，且 `/tmp` 挂在 `tmpfs 448M /var/volatile`。**

板子重启（本次检测时 uptime 仅 83 秒）后 tmpfs 被清空，**那份完整采集不可恢复**，电脑侧只剩前缀 15 块（约 28.5%）。

### 这是流程缺陷，不是偶发事故

| 问题 | 后果 |
|---|---|
| 完整采集写在 `/tmp`（内存盘） | 重启即毁，而回传需要数分钟、可能中断 |
| 回传程序中断后无自动重试 | 中断就只能靠人重来，而源文件此时已不存在 |

**修正建议（下次采集前必须做）**：完整 IQ 落盘到持久分区（`/root/` 或独立数据目录），再回传；回传中断后从持久副本续传。

## 3. 完成度评估

### 已上板实测通过（有原始证据）

| 项 | 证据 |
|---|---|
| TTL33/PWM2 合并 PL + 无 firmware 设备节点，**同一次干净启动**初始化 AD9361 / DRM / VDMA / PWM2 | `results/p35-once-merged-20261021T030101Z/` |
| 显示几何回读：可见 800×480、虚拟 800×960、32bit、stride 3200 | `p36-display-readback-20261021T030850Z/` |
| 8 轮 RX 取消/重建，每轮 2 次有效 refill | `p33-rx-cancel-board-20261021T031013Z/` |
| 有限 RX 配置（30.72 MS/s、18 MHz、2450 MHz、manual 0 dB） | `p35-finite-rx-prep-20261021T030951Z/` |
| 板端分析 + 绘制到帧缓冲（分析约 3.44 ms、CPU 绘制约 3.50 ms） | `p36-panel-snapshot-20261021T031301Z/` |
| 可见区字节导出并归档为 `screen.png`（**framebuffer 回读，非物理照片**） | `p36-file-archive-20261021T031834Z/` |
| 16×65536 帧完整缓冲在板端保存，采集耗时 0.0354 s | `p36-full-rx-board-20261021T032307Z/` |

### 已构建但未上板

| 项 | 状态 |
|---|---|
| 像素时钟溢出修复候选 M16.5/D2/O25 | **未生成、未综合、未上板** |
| P35 显式加载设备树候选 `rf-display-p35-explicit.dts` | 电脑 FDT 已验证，上板未验证 |

### 未通过 / 未做

| 项 | 说明 |
|---|---|
| **完整连续 IQ 归档** | 该次采集已丢失；`lossless_proven=false`、`continuous_ADC_timeline_verified=false` |
| **物理像素时钟** | 软件报 33 MHz 不能证明硬件一致；32 位时钟率溢出诊断成立，修复未做 |
| 物理屏幕验证 | 只有 framebuffer 回读，没有实测照片/示波器测量 |
| CDC、外部 IO 时序 | 仍开放 |
| 冷启动 `0xFF` | 本次又复现一次，未根治 |
| 旧内核驱动卸载缺陷 | 未修复 |
| 真实 AI 数据集 | 未做 |
| 触摸交互 | 未做 |
| 旧板 RAM 发射包 | 未恢复 |

## 4. 项目健康度

| 指标 | 值 |
|---|---|
| Python 测试 | **938 passed**（昨天 885，今日 +53） |
| 文档链接 | 待复查 |
| 板子可用性 | 硬件正常；RF 需重启一次清 `0xFF` |

## 5. 对昨天结论的修正（接受审查方意见）

我在 P34 记录里写过"PL 完全正常、CDC 已排除、唯一坏设备树"。审查方认为**证据不足已撤回**，本次检测同意：

- P36 的同启动成功用的是一组**不同的**位流（TTL33，移除了未用 LVDS 分支、初始像素 33 MHz）**和**一个不同的设备节点路径（显式装 PL + 无 firmware-name overlay）
- 同时也改变了加载路径，因此**不能唯一归因**旧挂死
- 正确表述应为："旧挂死的根因仍未确定；新的 TTL33 路径在同启动下可用"

## 6. 建议的下一步（按价值排序）

1. **普通重启板子**，恢复 RF（清 `0xFF`）
2. **改掉完整 IQ 落盘位置**（tmpfs → 持久分区），再做一次完整采集并归档 —— 否则"完整连续 IQ"永远无法验收
3. **做 M16.5/D2/O25 时钟修复候选**：先只读核对 BD/primitive/DRP 初值，再综合布线，单次干净启动后回读寄存器验证
4. 物理显示验证（拍一张真实屏幕照片即可补上这一项）
5. CDC / 外部 IO 时序审查
