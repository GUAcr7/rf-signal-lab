"""Record the real native diagnostic and honest remaining integration dependencies."""
from datetime import datetime,timezone
import hashlib,json,re
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from p22_acquire_comparison import ROOT


def rel(path):return Path(path).resolve().relative_to(ROOT).as_posix()


def main():
    analysis=sorted(ROOT.glob('results/p27-analysis-*/report.json'))[-1]
    data=json.loads(analysis.read_text('utf-8'))
    readiness=sorted(ROOT.glob('results/p27-fpga-readiness-*/report.json'))[-1]
    ready=json.loads(readiness.read_text('utf-8'))
    acquisition=ROOT/data['acquisition_record']/'report.json'
    acquired=json.loads(acquisition.read_text('utf-8'))
    tests_log=ROOT/'results/p27-verification-20261018/pytest.log'
    tests=int(re.search(r'(\d+) passed',tests_log.read_text('utf-8'))[1])
    if acquired['status']!='capture_and_tx_cleanup_verified':raise RuntimeError('TX cleanup not accepted')
    if tests!=864:raise RuntimeError('expected full regression did not complete')
    meta=data['native_metadata'];check=data['assessment']
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p27-summary-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    times=np.array([r['refill_end_s'] for r in meta['timestamps']])
    corr=np.array([r['correlation'] if r['correlation'] is not None else np.nan for r in data['windows']])
    gaps=np.array([r['extra_advance_modulo_period'] if r['extra_advance_modulo_period'] is not None else np.nan for r in check['boundaries']])
    fig,axes=plt.subplots(2,1,figsize=(10,6),sharex=True,layout='constrained')
    axes[0].plot(times,corr,color='#197d83',linewidth=.8)
    axes[0].axhline(.99,color='#bb573d',linestyle='--',label='confidence threshold 0.99')
    axes[0].set(ylabel='Prefix/reference correlation',ylim=(.9895,1.0005),title='512 sparse RX1 DMA prefixes: known-source diagnostic')
    axes[0].legend(loc='lower left');axes[0].grid(alpha=.2)
    axes[1].plot(times[1:],gaps,'.',color='#197d83',markersize=3)
    axes[1].axhspan(-1,1,color='#90bebd',alpha=.15,label='integer-delay tolerance +/-1 raw sample')
    axes[1].set(ylabel='Signed modulo extra advance',xlabel='Host refill-completion time (s), not ADC timestamp')
    axes[1].legend(loc='lower left');axes[1].grid(alpha=.2)
    fig.text(.01,-.025,'Only 1.5625% of samples saved. Periodic reference cannot exclude whole-period losses or unobserved internal gaps.',fontsize=9)
    fig.savefig(out/'diagnostic.png',dpi=150,bbox_inches='tight');plt.close(fig)
    stamp=datetime.now(timezone.utc).isoformat()
    record=f'''# EXP-HW-019：快速接收诊断与新板构建条件

- 日期：2026-10-18；记录时间 {stamp}。
- 承接 [HW-018](EXP-HW-018-review-and-streaming.md)。本轮目标：扩大 RX1 诊断长度，验证快速接收/后落盘的方法，并核对合并 RF/display 的实际工具条件。
- 结论：**512 个 DMA 缓冲的稀疏诊断通过；完整持续录制与整机任务尚未完成。** 当前电脑可继续使用，XC7Z100 重建受当前工具支持/授权限制。

## 1. 原理、实现与黄金对照

原 iio_readdev 把完整数据写入文件。新 C 程序先分配小内存，快速 refill；每缓冲只取前 8192 个原始位置、每隔 8 点保留一个值，停止/释放 RX 后再保存。这样移走接收循环内的文件写入，但保存的只是诊断观测，不是完整记录。

每 DMA 65536 帧，只存 1024 对 I/Q，即 **1.5625%** 样本。没有抗混叠滤波；文件不能直接当作完整频谱、回放或 AI 数据集。源格式 le:S12/16>>0 的未定义高位被明确掩掉，并将 12 位信号正确符号扩展为 LE s16。

Python 黄金观察器遍历 8 种抽取相位，在原始采样坐标中匹配发送序列，不把源起点粗量化到 8 点整数倍。先用历史完整原始数据验证：四通道 16 窗仍检出 11 处跳跃，RX1 16 窗仍检出 0 处，起点与完整窗口法相差不超过 1 点。

新程序通过实际 C 的模拟 IIO 测试：精确抽取位置、正负 12 位值、16/512 上下限、格式/配置/BIST/版本错误、refill/步幅错误、资源释放及拒绝覆盖。新增匹配器有注入频偏、周期换行、抽取相位边界、噪声反例和已知跳跃测试。实际测试枚举相位 0/3/7 及周期末端；算法实现遍历全部 8 相位。

## 2. 编译与真实 ARM 验证

新板实际 libiio **0.20**、glibc **2.23**；不能沿用旧 P201 的 0.24/2.28 假设。复用已安装 ARM GCC8.3，编译 ARMv7/Cortex-A9 hard-float ELF，所需符号最高 GLIBC_2.4。无系统库替换、无重新安装工具链。

共用已归档 0.24 头文件中两版共有的 ABI；程序实际加载并严格检查 0.20，扫描格式、两通道 4 B/帧、I/Q 指针位置、refill 字节数全部检查。先做 16 缓冲**不发射** smoke，实际运行/保存/释放通过；随后才做已知源诊断。

## 3. 本轮上板实测

旧 P201 继续使用已验证的 BPSK 文件（数字单分量峰值 256）、TX gain −10 dB、端口 A；新板 RX1 manual/0 dB、A_BALANCED；双方 LO 2450 MHz、Fs 30.72 MS/s、RF BW 18 MHz。本轮没有写 RF 属性、没有重启或换 PL，只改了接收 scan mask。发射一次，原生 30 秒守卫、退出 0、buffer 释放及 DDS 零源读回通过；物理 RF 静默未测。

| 项 | 实测 |
|---|---:|
| 成功接收 DMA 缓冲 | {meta['blocks']} |
| 名义接收帧数（程序读回数） | {data['nominal_drained_samples']:,} |
| 对应名义样本时间 | {data['nominal_drained_duration_s']:.6f} s |
| 主机观测采集时间 | {meta['acquisition_s']:.9f} s |
| 接收搬运吞吐（含稀疏提取） | {data['observed_drained_MB_per_s']:.2f} MB/s |
| 停止后落盘时间 | {meta['post_capture_save_s']*1000:.3f} ms |
| 进程峰值 RSS | {meta['maxrss_kib']} KiB |
| 实际保存 I/Q 对数 | {data['actually_saved_samples']:,} |
| 实际保存字节 | {data['actually_saved_samples']*4:,} |
| 可信窗口 | {check['usable_windows']}/{check['total_windows']} |
| 检出非周期跳跃边界 | {check['detected_jump_count']}/{len(check['boundaries'])} |
| 待验证边界（弱/失败匹配） | {check['unverified_boundary_count']} |
| 相关度范围 | {np.nanmin(corr):.6f} ~ {np.nanmax(corr):.6f} |
| refill 中位 / p99 / 最大 | {data['refill_ms']['median']:.3f} / {data['refill_ms']['p99']:.3f} / {data['refill_ms']['max']:.3f} ms |
| 前缀提取中位 / p99 / 最大 | {data['prefix_extraction_ms']['median']:.3f} / {data['prefix_extraction_ms']['p99']:.3f} / {data['prefix_extraction_ms']['max']:.3f} ms |

![512 窗实测诊断](../../{rel(out/'diagnostic.png')})

**限定**：相比先前 16 缓冲 34.133 ms，本轮观测范围扩大 32 倍。但源仍以 131072 样本周期重复，整数延迟容差 ±1；整周期丢失不可见，缓冲未保存区内的情况也不可见。`lossless_proven=false`，本轮没有标为“长期无丢样通过”。这是接收搬运能力，不是完整落盘、FFT、AI 或显示吞吐。没有计算新的符号 BER/EVM，不把前缀相关度换成调制识别准确率。

分块回传、gzip SHA、原始 SHA/长度全部核验。保存的全部诊断样本已落电脑，不依赖板端 RAM 保留；完整 33,554,432 帧从未全量保存。

## 4. FPGA/屏幕合并条件：电脑可以用，当前工具不够

只读清点：RF 工程有 create_project.tcl、system_bd.tcl、顶层 HDL 与约束；显示压缩包有 148 个相关源成员。RF 脚本来自 Vivado 2017.4，不直接在 D 盘运行其带 -force 的创建脚本。

在独立 E 盘工作目录对原厂目标 `xc7z100ffg900-2` 做离线最小构建检查：Vivado 2021.1 返回 **get_parts=0**，XC7Z020 则能枚举。检查在创建/综合设计前退出 3，所以本轮**没有实测到许可证 checkout 阶段**，不能伪造为具体许可证服务报错。

[AMD 2021.1 官方支持表](https://docs.amd.com/r/2021.1-English/ug973-vivado-release-notes-install-license/Supported-Devices) 中 Standard 不含 XC7Z100，Enterprise 覆盖全部 Zynq-7000。因此下一步需要在**同一电脑**补齐合适的器件/版本支持及合法授权，再实际验证最小综合。无需更换电脑；现有原厂位流、ARM/Python 开发、真实采集不受此限制。

用户反馈老师/实验室当前没有现成授权。官方有[评估授权渠道](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/licensing-faq.html)和[高校计划](https://www.amd.com/en/products/software/adaptive-socs-and-fpgas/vivado/vivado-licensing-options.html)，但账号可取得的具体许可、有效期及与 2021.1 的兼容性尚未实际确认；不能承诺一定可直接用，也未替用户购买、申请或修改账户。

顺带纠正旧规划：“Zynq-7020 必然放不下”没有依据，旧工程 LUT 仅 22.46%；bitstream 文件更大也不能推出逻辑占用更多。两条已在原设计说明中更正并保留原稿备份。

## 5. 验收与证据

| 事项 | 判定 |
|---|---|
| 黄金观察器与旧完整数据对照 | 通过，复现 11/0 对照 |
| C 程序电脑模拟与 ARM 编译 | 通过 |
| 新板 0.20 ABI/格式与 16 缓冲 smoke | 通过 |
| 512 窗已知源稀疏诊断与回传 | 通过 |
| 长期完整无丢样 / 独立计数 | 待验证 |
| XC7Z100 重新综合、RF/display 合并 | 当前工具条件未满足 |
| 真实 AI、整机实时吞吐与延迟 | 未完成 |

全回归 **{tests} passed**。本轮新增 Python 匹配器和实际 C 模拟 IIO 检查，不把 Mock 结果当硬件结果。

- [分析报告](../../{rel(analysis)})、[逐步采集与 TX 清理](../../{rel(acquisition)})。
- [全部诊断回传记录](../../results/p27-chunk-transfer-20261018T125555Z/report.json)、[已回收诊断字节](../../results/p27-chunk-transfer-20261018T125555Z/prefixes512.bin)。
- [黄金对照](../../results/p27-observer-validation-20261018T125139Z/report.json)、[ARM 编译](../../results/p27-native-build-20261018T125138Z/report.json)、[真实 smoke](../../results/p27-smoke-20261018T125241Z/report.json)。
- [工具条件检查](../../{rel(readiness)})、[完整测试日志](../../{rel(tests_log)})。
- 源码：`embedded/arm_rx_diagnostic/arm_rx_diagnostic.c`、`src/rfsig/sparse_continuity.py`；本轮入口/设计记录备份 `results/p27-before-20261018/`。

## 6. 下一步依赖

1. 保留可靠的单 DMA **完整快照**采样接口；诊断前缀与原始完整样本分开，不将前缀文件喂给现有频谱/AI 入口。
2. 推进预分配缓冲/生产者与消费者分离，加入明确丢弃计数和队列积压，验证完整选定帧下的实际分析吞吐；若要宣称每点无丢失，再加入硬件计数或不重复源标记。
3. 不依赖 Vivado 的真实 AI 数据准备可继续：多随机源、多独立会话，记录 SNR 的取得依据，按源/会话划分；现有固定循环源和本次诊断数据不冒充独立数据集。
4. 获取适用于 XC7Z100 的工具/授权后，先复现 RF 和显示原厂工程，再处理版本升级、AXI 地址、时钟/复位/CDC、资源/时序及显示并行；不得烧写未验收的新位流。

本轮没有 FPGA RTL 或 AI 模型变更，相应资源/时序/量化指标不新增。板卡最终 RF 属性维持原验收配置，无活动 TX；串口已释放。
'''
    doc=ROOT/'docs/experiments/EXP-HW-019-memory-diagnostic-and-build-readiness.md'
    doc.write_text(record,encoding='utf-8',newline='\n')
    start=ROOT/'START-HERE.md'
    old=start.read_text('utf-8')
    notice=f'''# 从这里恢复项目工作

最新更新：{stamp}。先读 [HW-019](docs/experiments/EXP-HW-019-memory-diagnostic-and-build-readiness.md)。

- 已完成新板原生快速 RX1 稀疏诊断：512 缓冲约 1.09 秒，512/512 强匹配，511 个边界检出 0 处非周期跳跃；约 122.87 MB/s 接收搬运、4168 KiB 峰值 RSS。
- **只保存 1.5625% 诊断样本，没有完整录制，没有证明长期无丢样，也不是新 AI 数据集。** 下文 P26 完整快照结果保留有效范围。
- 全项目 **{tests} 项回归通过**。本轮一次 30 秒限时 BPSK 发射清理通过；未写 RF 属性/未重启，最终 RX 仍 manual/0 dB、LO 2450 MHz、Fs 30.72 MS/s、BW 18 MHz。
- 当前电脑可以继续开发。Vivado 2021.1 能枚举 XC7Z020，却找不到新板工程目标 XC7Z100；其重建需要合适的 Enterprise 支持与授权。用户目前无现成授权，官方评估渠道兼容性待核。原厂固件收发、ARM/Python、真实 AI 数据准备可继续。
- **不要重跑 P26 总结生成器覆盖本轮入口。** 最新机器状态以 TX-SOURCE-STATUS.json 的 HW-019 为准。

---

## 前轮完整快照基线（HW-018）
'''
    if '## 前轮完整快照基线（HW-018）' in old:
        old=old.split('## 前轮完整快照基线（HW-018）',1)[1]
    elif old.startswith('# 从这里恢复项目工作'):
        old=old.split('\n',1)[1]
    start.write_text(notice+old,encoding='utf-8',newline='\n')
    status_path=ROOT/'TX-SOURCE-STATUS.json';status=json.loads(status_path.read_text('utf-8'))
    status.update(updated=stamp,record=rel(doc),updated_note='HW-019: native sparse 512-buffer diagnostic; XC7Z100 tool support checked',
                  status='native_sparse_rx_diagnostic_pass; full_lossless_stream_real_ai_combined_display_pending',
                  python_tests=tests,python_tests_evidence=rel(tests_log),python_tests_note='Full 864-test regression, including actual native C against mock IIO.')
    status['RF_transmit_scope']='Whole historical count not re-audited. HW-018 added two bounded 30-second runs; HW-019 added one bounded 30-second BPSK run. No RF attributes changed in these runs. Native cleanup verified; physical silence remains unmeasured.'
    status['p27_native_diagnostic']={'analysis':rel(analysis),'acquisition':rel(acquisition),'status':'passed_with_limits',
        'buffers':512,'saved_sample_fraction':data['saved_sample_fraction'],'lossless_proven':False,'complete_stream_saved':False,
        'drain_MB_s':data['observed_drained_MB_per_s'],'maxrss_kib':meta['maxrss_kib'],'new_RF_runs':1,'RF_attributes_written':False,
        'diag_only_data':'results/p27-chunk-transfer-20261018T125555Z/prefixes512.bin'}
    status['new_board_build_readiness']={'evidence':rel(readiness),'status':'XC7Z100_not_available_in_current_tool',
        'part':'xc7z100ffg900-2','user_has_lab_license':False,'checkout_attempted':False,
        'same_PC_usable':True,'evaluation_license_compatibility':'not_yet_verified',
        'official_support':'https://docs.amd.com/r/2021.1-English/ug973-vivado-release-notes-install-license/Supported-Devices'}
    status_path.write_text(json.dumps(status,ensure_ascii=False,indent=2)+'\n',encoding='utf-8',newline='\n')
    print(doc);print(out)


if __name__=='__main__':main()
