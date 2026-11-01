# P34：合并位流生成成功 —— XC7Z100 授权阻塞的真相

> **P35审查更正（2026-10-21）**：构建能力结论成立；本文的DRC 58 Advisory并非独立CDC报告的58 Critical。原生DRC实际为AVAL-4=56、REQP-181=2。13ps保持余量是已声明工具模型内的结果，不能单凭它推断硬件必然失效，也不能替代缺失外部IO约束。旧部署包已停用，当前新TTL33构建及板卡状态见[本轮纠错记录](exp-hw-025-review-corrections-and-ttl.md)。下文保留原实验时间作用域。

- 日期：2026-10-20 晚（北京时间）。
- 背景：项目此前记录"XC7Z100 重建受当前工具支持/授权限制"（HW-019 §4、START-HERE 多轮），据此把"射频与屏幕同时工作"判为不可行。
- **本轮结论：那个判断是错的。授权问题是环境配置问题；合并位流现已成功生成。**
- 范围：纯电脑侧 Vivado 操作。**未上板、未烧写、未替换板上任何位流。**

## 1. 授权阻塞的真相

### 1.1 器件其实是可枚举的

用既有探针脚本重跑 Vivado 2021.1：

```
P27_Z100_PARTS xc7z100iffv900-2L ... xc7z100ffg900-1 xc7z100ffg900-2 ... (共 12 个)
P27_PART_COUNT 1
```

HW-019 当时记录的 `get_parts=0` 已经**不再成立** —— 器件数据在 10-18 的增量安装中已补齐。

### 1.2 真正的原因是授权文件找不到

```
WARNING: [Common 17-348] Failed to get the license for feature 'Synthesis' and/or device 'xc7z100'
ERROR:   [Common 17-345] A valid license was not found ...
```

两个叠加原因：

| 原因 | 证据 |
|---|---|
| 安装副本被清理掉了 | `C:\Users\project_user\AppData\Roaming\XilinxLicense\` **整个目录不存在**（EXP-HW-020 记录安装在此） |
| 环境变量指向别家授权 | `LM_LICENSE_FILE = D:\modelsim\LICENSE.TXT` |

原始下载件仍在：`E:\FPGA_Tools\Downloads\Xilinx.lic`（3,012 B）。

授权内容（只读核对）：

| 项 | 值 |
|---|---|
| 特性 | `Vivado_Enterprise_Package`、`Vivado_ML_Enterprise_Edition`、`Vivado_Simulation`、`ISE_Embedded_Edition` |
| 起始 | 17-Oct-2026 |
| 到期 | **17-dec-2026**（60 天评估） |
| 绑定 | `HOSTID=40c2ba523054`（本机） |

### 1.3 修复

只设一个用户环境变量，不动 ModelSim 配置：

```
XILINXD_LICENSE_FILE = E:\FPGA_Tools\Downloads\Xilinx.lic
```

**验证（`LM_LICENSE_FILE` 保持原值不变）**：

```
INFO: [Common 17-349] Got license for feature 'Synthesis' and/or device 'xc7z100'
Synthesis finished with 0 errors, 0 critical warnings and 0 warnings.
P27_SYNTHESIS_CAPABILITY_PASS
```

**所以之前的"授权限制"是配置问题，不是没有授权。**

## 2. 合并位流生成

### 2.1 已有布线基线

`E:\p30c-1019-174235\merged-route.dcp`（28,854,850 B，设计 `rf_display_top`，器件 `7z100-ffg900`）。

| 指标 | 值 |
|---|---:|
| WNS（建立） | **+0.449 ns** |
| WHS（保持） | **+0.013 ns** |
| 失败端点 | **0** |
| 报告结论 | `All user specified timing constraints are met.` |

资源：LUT **7.87%**、FF 6.93%、BRAM 1.66%、DSP 3.42% —— 余量极大。

### 2.2 本次生成的位流

```tcl
open_checkpoint E:/p30c-1019-174235/merged-route.dcp
write_bitstream -force .../rf_display_top.bit
```

```
P34_PART xc7z100ffg900-2
INFO: [Vivado 12-3199] DRC finished with 0 Errors, 24 Warnings, 58 Advisories
INFO: [Common 17-349] Got license for feature 'Implementation' and/or device 'xc7z100'
Bitstream compression saved 99035584 bits.
write_bitstream completed successfully
```

| 项 | 值 |
|---|---|
| 文件 | `E:\FPGA_Tools\Work\p34-bitstream-20261020\rf_display_top.bit` |
| 大小 | **5,037,020 B** |
| sha256 | `688475a33a284bb18ea9bcb32d19e694829e773a363e9db03bed42726b83ab67` |
| 压缩 | **`COMPRESS=TRUE`**（头部可见），压缩节省 99,035,584 bit ≈ 12.4 MB |
| 还原后 | ≈ **17.4 MB**，与原厂 `ad_fmcomms3_ebz_xc7z100.bit`（17,416,454 B）量级一致 → **确认是完整位流** |
| 耗时 | 48 s，峰值内存 2.97 GB |

### 2.3 DRC 警告内容（24 条，逐类）

| 规则 | 条数 | 含义 |
|---|---:|---|
| `REQP-1839` RAMB36 async control check | 20 | Block RAM 异步控制检查（读改写时序提醒） |
| `DPIP-1` Input pipelining | 2 | DSP 输入流水建议 |
| `RTSTAT-10` No routable loads | 1 | 180 条网络无负载（未连接信号） |
| `CHECK-3` rule limit reached | 1 | 报告条目上限提示 |

**0 Error、0 Critical Warning。** 58 条 Advisory 即 CDC 项。

## 3. 为什么现在仍然不能部署

位流存在 ≠ 可以烧。三项未闭合：

| 项 | 状态 | 风险 |
|---|---|---|
| **58 项 CDC** | 未审查收口（P33 进行中） | 跨时钟域结构可能在某些模式下失效 |
| **背光 TTC0 通道 0→2 修正** | 只在未综合的 `p32-pwm2-105934` 工程里 | 这个 DCP 是**修正前**的，背光仍抢系统计时源 |
| **WHS 余量 13 ps** | 极薄 | 保持时间贴极限，温度/电压漂移下可能失效 |

**所以本轮产出是"能力证明"，不是"可部署产物"。**

## 4. 对项目判断的修正

| 原判断 | 修正后 |
|---|---|
| "XC7Z100 重建受工具/授权限制，短期动不了" | **错**。授权有效到 2026-12-17，器件可枚举，综合与出位流均已跑通 |
| "射频与显示不能同时工作" | **只是当前部署状态**，不是能力边界。合并设计已布线、时序收敛、位流已生成 |
| "需要买 Enterprise 授权" | **不需要**，已有 60 天评估授权；只需设对环境变量 |

**真正剩下的是工程收尾，不是外部依赖。**

## 5. 下一步（按依赖，全部可做）

1. **CDC 审查收口** —— P33 三份文档在推进（sync_id 注册、dest_enabled 汇入、EOT 槽寿命）
2. **把 PWM2 背光修正并入** —— 在 `p32-pwm2-105934` 综合布线，再出位流
3. **复核 WHS 13 ps** —— 列出保持时间最紧的路径，判断是否需要额外流水
4. 上板：先只验显示（确认背光与显示正常），再验射频，最后验并行
5. 板载屏显示实时频谱/星座（复用已验收的 `panel_render` 布局，改为板上绘制）

## 6. 证据

| 内容 | 路径 |
|---|---|
| 器件枚举与授权通过 | `E:\FPGA_Tools\Work\p34-part-probe-20261020\probe4.log` |
| 位流生成日志 | `E:\FPGA_Tools\Work\p34-bitstream-20261020\write_bit.log` |
| 生成的位流 | `E:\FPGA_Tools\Work\p34-bitstream-20261020\rf_display_top.bit` |
| 时序报告 | `E:\p30c-1019-174235\merged-route-timing.rpt` |
| 资源报告 | `E:\p30c-1019-174235\merged-route-utilization.rpt` |
| 授权字段核对 | `E:\FPGA_Tools\Downloads\Xilinx.lic`（只读） |

---

# 追加：带背光修正的位流已构建（可部署候选）

上文第 2 节那个位流是**背光修正之前**的版本。本轮把 TTC0 通道 0 → 通道 2 的修正工程完整跑完，得到可部署候选。

## A1. 构建结果

工程 `E:\p32-pwm2-105934\project\combined.xpr`（本轮之前**从未综合过**，所有 run 都是 Not started）。

```
P34_STATUS   write_bitstream Complete!
P34_PROGRESS 100%
DRC finished with 0 Errors, 24 Warnings, 58 Advisories
```

| 项 | 值 |
|---|---|
| 位流 | `E:\p32-pwm2-105934\project\combined.runs\impl_1\rf_display_top.bit` |
| 大小 | **5,034,572 B**（修正前版本 5,037,020 B） |
| sha256（前 16） | `96c5d8f3a5fb8cd0` |
| 日志 | `E:\FPGA_Tools\Work\p34-pwm2-build-20261020\build.log` |

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
