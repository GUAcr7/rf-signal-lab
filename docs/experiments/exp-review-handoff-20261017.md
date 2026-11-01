# 提交审查：2026-10-17 新板接入与任务②收尾

- 日期：2026-10-17 傍晚。
- 提交人：主执行工程师（本会话）。
- 审查人：独立审查与规划助手。
- **冻结版本**：以本文件列出的文件为准；本文件之后不再改动这些文件，如需修改会另开记录。
- 工作目录：`outputs/rf-signal-lab`（下文路径均相对此目录）。

---

## 1. 从哪读起（三份，按顺序）

| 顺序 | 文件 | 为什么先读 |
|---|---|---|
| 1 | `START-HERE.md` | 入口已改写：新板在顶部，旧板发射侧在其后 |
| 2 | `docs/design/NEW-BOARD-RESUME.md` | 新板的全部可操作结论：开机检查、持久化清单、模式切换、操作坑 |
| 3 | 本文 | 逐项列出"哪些已验证、哪些没有、哪些结论被推翻" |

## 2. 本轮新增/改写的文件（按类别，附作用）

### 2.1 文档

| 文件 | 字节 | 内容 |
|---|---:|---|
| `START-HERE.md` | — | 顶部改写：新板优先，并标注"本振偏置"结论已推翻 |
| `docs/design/NEW-BOARD-RESUME.md` | 6,853 | **新板接续说明**（收工点） |
| `docs/design/new-board-tlz7xh-evm-review-20261017.md` | 11,773 | 新板资料审查：与旧板差异、射频/显示互斥的引脚级论证 |
| `docs/design/new-board-power-on-card.md` | 7,411 | 上电接线操作卡（①–⑦ 编号，配标注图） |
| `docs/experiments/EXP-HW-005-TLZ7xH-bringup.md` | 13,445 | 板卡识别、位流加载、AD9361 接收链打通 |
| `docs/experiments/EXP-HW-006-TLZ7xH-display-and-fan.md` | 16,229 | 屏幕点亮、风扇控制、开机自启、触摸修正 |
| `docs/experiments/EXP-P13-OBW.md` | 11,524 | 99% 占用带宽：数字域 vs 仪器端 |
| `docs/experiments/EXP-P13-POWER.md` | 7,480 | 相对功率：数字幅度步进法 |
| `docs/experiments/EXP-TX-001.md` | 15,495 | 追加 §5.2 撤回块（本振偏置结论） |
| `docs/experiments/EXP-TX-002.md` | 12,735 | 追加 §3.1 撤回块 |

### 2.2 代码

| 文件 | 变更 |
|---|---|
| `src/rfsig/bandwidth.py` | 新增 `rrc_occupied_bandwidth_hz()`（升余弦 99% 包容带宽的闭式解） |
| `tests/test_bandwidth.py` | 新增 22 项测试（数值积分互证 + 4 个手算边界 + 单调性 + 非法参数） |
| `experiments/p13_measure_obw.py` | 改为使用 `src/` 的实现（删掉脚本内重复副本） |
| `experiments/p13_rrc_obw_crosscheck.py` | 闭式解 vs 数值积分独立对照 |
| `experiments/p13_marker_grid_analysis.py` | 复现"12.5 kHz 标记网格量化"的论证 |
| `experiments/p13_prepare_power_steps.py` | 生成 512/256/128 三档幅度波形 |
| `experiments/p14_*.py` | 新板资料 PDF 文本/插图提取、接线图标注、区域裁剪 |
| `experiments/p15_*.py` | 串口工具链（识别、命令、读取、上传、触摸事件解码）、原理图风扇电路检索 |

### 2.3 证据（`results/`，**已被 `.gitignore` 排除**）

`results/p15-newboard-*/` 共 17 个目录，每个含 `transcript.json`（串口原文）。
`results/p13-obw-*/`、`results/p13-pwr-*/`、`results/p13-session2-obw-*/` 为任务②的照片与报告。

**注意**：`.gitignore` 里有 `results/*`，所以这些证据不在版本控制里。若审查需要，请直接读文件系统。

## 3. 结论分级（请按这一栏核对，不要按正文的措辞核对）

### 3.1 已验证（有可复现证据）

| 结论 | 证据位置 | 验证方式 |
|---|---|---|
| 新板器件是 **XC7Z100** | `results/p15-newboard-bitstream-hash-20261017/` | 板上 `system_wrapper.bin` 与资料 `ad_fmcomms3_ebz_xc7z100.bin` sha256 **逐字节相同**；且加载时 PCAP 校验通过（`state=operating`） |
| 新板系统跑在 **SD 卡**上 | `results/p15-newboard-storage-20261017/` | `mmcblk0` 的 `device/type` = `SD`，`root=/dev/mmcblk0p2` |
| AD9361 接收链可用 | `results/p15-newboard-overlay-apply-20261017/`、`p15-newboard-iio-check-20261017/` | `AD936x Rev 2 successfully initialized`；`iio_info -s` 列出 4 个设备 |
| 显示链路可用 | `EXP-HW-006` §1.3/§1.4 | `state=operating`、`/dev/fb0`、`800×480×32 stride 3200`、控制台 `100x30`、用户确认整片白 |
| 风扇可控 | `EXP-HW-006` §2 | 手册 §26 + 测试手册 1.4；用户确认物理转动 |
| 显示+风扇开机自启 | `EXP-HW-006` §3.3 | **重启过一次**，`state=operating`、`/dev/fb0` 存在、`gpio914/direction=out` |
| 三类调制 99% 占用带宽 | `results/p13-obw-20261017T044735Z/obw.json` | 数字域与解析理论差 ≤1%；仪器端与数字域差 ≤1.08% |
| 相对功率线性 | `results/p13-power-steps-20261017T052904Z/report.json` | 512/256/128 三档，累计 12 dB 偏差 0.002 dB |
| 测试全绿 | 本机 `.venv` | 689 passed |

### 3.2 **未验证**（请重点审查这一栏）

| 项目 | 状态 | 风险 |
|---|---|---|
| **触摸修正是否在重启后自动生效** | 脚本已装（`/etc/X11/Xinit.d/95touch`、`/etc/X11/Xsession.d/99touch`，sha256 `3ab65013…`），**手工执行通过，但没在重启后验证** | 若两个钩子目录都没被 X 调用，回来触摸会恢复成反向 |
| 射频模式 ↔ 显示模式的完整往返切换 | 步骤在 `NEW-BOARD-RESUME.md` §3 按已验证机制**组合**而成，**没跑过一次** | 切过去可能起不来 |
| 触摸精度 | 用户反馈"方向对了"，未做四点标定量化 | 边缘可能点不到 |
| 屏幕显示实时频谱/星座 | 当前只有 XFCE 桌面，**没有任何自绘 UI** | 任务①的展示层还是空的 |
| 射频与显示同时工作 | 两个官方位流互斥，需要自己综合合并设计 | 引脚零冲突（64 vs 53），但资源与时序未验证 |

### 3.3 已被推翻的结论（**必须按新的写**）

| 旧结论 | 状态 | 依据 |
|---|---|---|
| 本振偏置 **+2.5 kHz / 1.02 ppm** | **撤回** | 那是 Span 10 MHz / 801 点 = 12.5 kHz 标记网格的量化假象；零偏置即可复现全部三个"证据"。复算脚本 `experiments/p13_marker_grid_analysis.py` |
| 修正后的说法 | 射频中心与理论一致到 **±5 kHz（±2 ppm）** | 三次仪器 OBW 中心读数 −1.829/−4.767/−0.262 kHz，峰峰跨度 4.5 kHz，估计器本身有 kHz 级噪声 |
| `Rs×(1+β)=324 kHz` 是 99% 带宽 | **错** | 那是支撑宽度；99% 包容带宽是 **279,998 Hz**，差 13% |
| 频谱仪可区分三类调制 | **错** | 三者占用带宽实测差仅 1.08%；区别在相位，必须收 IQ |

## 4. 我在本轮判断失误的地方（请复核我是否已正确更正）

| 错误 | 性质 | 是否已更正 |
|---|---|---|
| 凭记忆写出 qpsk/qam16 的 sha256 | 伪造数据 | 已改为"从清单读 + 从字节重算 + 断言一致" |
| "触摸没产生事件" | 测试方法错：`od` 有缓冲，`timeout` 直接杀进程 | 已在 `EXP-HW-006` §B.1 记录，改用 `dd bs=16 count=N` |
| "可能排线没接" | 未测就推断；笔中断实际正常 | 同上 |
| "轴向交换了" | 从跨度比例反推，用户实测"左右正常"证伪 | 同上 |
| "仪器衰减不补偿" | 目测格线代替标记读数 | 已在 `EXP-P13-POWER` §5 记录 |
| fpga_manager 用 `cat bin > firmware` | 该属性要文件名不要内容 | 已在 `EXP-HW-005` §B.1 记录 |

## 5. 建议审查方式

1. **先只看 3.1 / 3.2 / 3.3 三张表**，逐条对照正文，确认分级没错。
2. 重点攻击 3.2：那五项是本轮的真实缺口，尤其是"触摸重启后是否生效"和"模式切换"。
3. 抽查 3.1 里任一条，用 `results/` 下的 `transcript.json` 原文核对——**不要只信文档里的转述**。
4. 检查 `src/rfsig/bandwidth.py` 的闭式解：手算 `fraction=(1-β)=0.65` 应为 `(1-β)Rs=156,000`，`fraction=1.0` 应为支撑 `324,000`。
5. 若认为 3.3 的撤回不成立，请给出反例——**推翻我需要证据，不是意见**。

## 6. 我没动过的东西（范围声明）

- **旧板 P201 的任何射频参数**：25 次发射的日志全部 `rf_settings_written=false`
- **新板的 `pl.dtbo`、U-Boot、内核、设备树源、拨码开关、`boot.scr`**
- `D:\xilinx` 与 `D:\AD9361` 下**任何文件**（只读，提取物写在 `tmp/`）
- 本轮唯一写入板卡的地方：`/lib/firmware/{system_wrapper.bin,d480p.dtbo,sw-ad9361.bak}`、`/etc/rcS.d/S99board`、`/etc/X11/Xinit.d/95touch`、`/etc/X11/Xsession.d/99touch`

## 7. 可再现性

`tmp/new-board-xilinx-review/` 下 88 个文件（手册提取文本、插图、裁剪图、标注图、脚本源）**都可以由脚本重新生成**：

```powershell
.venv\Scripts\python.exe experiments\p14_extract_xilinx_docs.py      # PDF 文本
.venv\Scripts\python.exe experiments\p14_extract_board_figures.py    # 手册插图
.venv\Scripts\python.exe experiments\p14_crop_board.py               # 区域裁剪
.venv\Scripts\python.exe experiments\p14_annotate_board.py           # 接线标注图
.venv\Scripts\python.exe experiments\p15_find_fan_circuit.py         # 原理图风扇电路
```

因此审查不必依赖 `tmp/` 的现存副本，可自行重跑并与文档中的数值对照。
