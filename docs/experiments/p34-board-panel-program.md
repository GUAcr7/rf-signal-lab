# P34：板端自绘面板程序 —— 分析第一次真正跑在板子上

- 日期：2026-10-20 深夜（北京时间）。
- 背景：此前所有渲染都在电脑侧完成，板子只做 `gunzip > /dev/fb0`。任务①要的是板子自己画，所以分析必须上板。
- **本轮结果：板端 C 程序已跑通，输出与 numpy 独立实现逐位一致；实测每帧 2.34 ms。**
- 范围：板子在**显示模式**，数据来自文件，不是实时射频。

## 1. 程序做了什么

`embedded/arm_panel/arm_panel.c`：

1. 读入交错 int16 I/Q（可指定通道数，RX1 用 ch0/ch1）
2. 加 Hann 窗
3. **原地基-2 FFT**（N=1024，自己实现，无外部 DSP 库）
4. 多帧平均成功率谱，归一化成 dB
5. 直接 `mmap` `/dev/fb0` 绘制：标题、dB 网格、频谱曲线、峰值标记线、指标块
6. **自测每帧耗时**并打印

字模由 `experiments/p34_make_font.py` 用 PIL 生成 8×12 位图（94 字形）导出 `font8x12.h`，板端只做位块拷贝 —— 避免在 C 里手写字形表。

## 2. 正确性：与 numpy 交叉验证

同一份数据（8192 对 I/Q），板端与 `experiments/p34_arm_panel_reference.py`：

| 指标 | 板端 | Python 参考 | 一致 |
|---|---:|---:|---|
| frames used | 8 | 8 | ✓ |
| pairs | 8192 | 8192 | ✓ |
| peak | **106.2 dB** | 106.232469 dB | ✓ |
| 峰值偏移 | **+33.0 bins** | +33.0 bins | ✓ |
| RMS | **203.0** | 203.029020 | ✓ |

**板端手写的 FFT、窗、平均、峰值检测与 numpy 算法逐位吻合到打印精度。**

## 3. 时间预算：实测每帧 2.34 ms

```sh
./arm_panel iq-8192.bin 4 8 60      # 60 帧
iterations=60 mean_frame_ms=2.344 worst_frame_ms=3.498 fps=426.63
```

| 项 | 值 |
|---|---:|
| 平均每帧（8×1024 点 FFT + 整屏 800×480 重绘） | **2.344 ms** |
| 最差每帧 | 3.498 ms |
| 等效帧率 | 426.63 fps |

**结论：计算与绘制不是瓶颈。** 30 fps 的预算是 33 ms，这里有 **14 倍余量**。真正的时间会花在 ADC 采集与搬运上，不在分析和画图上。

这也说明"实时"在算力上完全可行，卡点只在"射频与显示能否同时"（PL 合并位流）。

## 4. 编译与部署

| 项 | 值 |
|---|---|
| 工具链 | `arm-linux-gnueabihf-gcc 8.3.0`（`E:\FPGA_Tools\ARM-GNU-A-8.3-2019.03\attempt-2\`） |
| 产物 | 22,848 B，**ELF32 ARM EXEC** |
| 依赖 | 仅 `libc.so.6`、`libm.so.6` |
| 最高符号 | **GLIBC_2.4**（板子 2.23，安全） |
| 部署 | base64 上传到 `/root/arm_panel`，`chmod 755`，哈希校验一致 |

编译过程中修掉两个真实错误：

1. **`-std=c99` 下 `clock_gettime`/`CLOCK_MONOTONIC` 不可见** —— 需要 `_POSIX_C_SOURCE 200809L`，否则是编译错误不是警告
2. **`ROW` 宏传了 4 个参数**（我写了 `"%d of %d"` 加两个值）—— 改为先 `snprintf` 再按 3 参数调用

## 5. 现在还不能做什么

| 项 | 原因 |
|---|---|
| **实时射频输入** | 显示模式没有 AD9361；rf 模式没有 `/dev/fb0`。需合并位流上板 |
| 连续采集不丢样 | 仍是整文件读入内存（示例 8192 对） |
| 星座图 | 本轮只做频谱；解调上板是下一步 |
| 触摸交互 | 未做 |

**代码里已留好替换点**：`load_iq()` 换成 libiio 采集即可，采集写法照搬项目里已上板验证的 `arm_rx_diagnostic.c`（dlopen 加载 libiio，兼容 0.20/0.24）。

## 6. 证据

| 内容 | 路径 |
|---|---|
| 板端源码 | `embedded/arm_panel/arm_panel.c` |
| 字模 | `embedded/arm_panel/font8x12.h`（生成器 `experiments/p34_make_font.py`） |
| numpy 参考实现 | `experiments/p34_arm_panel_reference.py` |
| 参考数值 | `results/p34-arm-panel/reference.json` |
| 输入子集 | `results/p34-arm-panel/iq-8192.bin`（65,536 B，sha256 `d3ed8ebf…`） |
| 首次运行 | `results/p34-arm-panel-run-20261020/` |
| 帧缓冲结果 | `results/p34-arm-panel-fb-20261020/`（哈希由 `a6e4301a…` 变为 `95e1f018…`） |
| **60 帧计时** | **`results/p34-arm-panel-timing-20261020/`** |
