"""Publish evidence-bound P29 records only after the independent builds/audit finish."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil

ROOT = Path(__file__).resolve().parents[1]
RECORD = 'docs/experiments/EXP-HW-021-vendor-migration-and-reconnect.md'


def latest(pattern, expected='passed'):
    paths = sorted((ROOT / 'results').glob(pattern + '/report.json'))
    if not paths:
        raise RuntimeError('missing ' + pattern)
    path = paths[-1]
    data = json.loads(path.read_text('utf-8'))
    if data['status'] != expected:
        raise RuntimeError(f'{path}: {data["status"]}')
    return path, data


def rel(path):
    return path.relative_to(ROOT).as_posix()


def utilization(path):
    text = path.read_text('utf-8', errors='replace')
    output = {}
    for label in ['Slice LUTs', 'Slice Registers', 'Block RAM Tile', 'DSPs', 'Bonded IOB']:
        match = re.search(r'\|\s*' + re.escape(label) + r'\*?\s*\|\s*([0-9.]+)\s*\|', text)
        if match:
            output[label] = float(match[1])
    if len(output) != 5:
        raise RuntimeError('resource report layout changed')
    return output


def quality(path, mode, prefix=None):
    prefix = prefix or f'{mode}-synth'
    text = (path.parent / f'{prefix}-check-timing.rpt').read_text('utf-8')
    checks = {name: int(n) for name, n in re.findall(r'checking (\w+) \((\d+)\)', text)}
    timing = (path.parent / f'{prefix}-timing.rpt').read_text('utf-8')
    match = re.search(r'WNS\(ns\).*?\n\s*[-\s]+\n\s*([+-]?[0-9.]+)\s+([+-]?[0-9.]+)\s+\d+\s+\d+\s+([+-]?[0-9.]+)', timing)
    if not match:
        raise RuntimeError('timing report layout changed')
    return dict(synthesis_only=True, WNS_ns=float(match[1]), TNS_ns=float(match[2]), WHS_ns=float(match[3]),
                checks=checks, post_route_timing_verified=False, hardware_function_verified=False)


def cdc_summary(path):
    text = path.read_text('utf-8')
    return {rule: dict(severity=severity, count=int(count)) for rule, severity, count in
            re.findall(r'^(CDC-\d+)\s+(Info|Warning|Critical)\s+(\d+)\s', text, re.M)}


def main():
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    rf_path, rf = latest('p29-rf-synth-*')
    display_path, display = latest('p29-display-synth-*')
    upgrade_path, upgrade = latest('p29-display-upgrade-*')
    package_path, package = latest('p29-package-*')
    sources_path, sources = latest('p29-source-verification-*')
    audit_path, audit = latest('p29-audit-*')
    capture_path, capture = latest('p29-smoke-archive-*', 'raw_bytes_and_final_board_identity_verified')
    integration_path, integration = latest('p29-integration-audit-*', 'planning_only_not_integrated')
    patch_path, patch = latest('p29-hls-patch-install-*', 'additive_vendor_patch_installed_hash_verified')
    ps_boot_path, ps_boot = latest('p29-ps-boot-baseline-*', 'read_only_comparison')
    clock_path, clock = latest('p29-display-clock-20*')
    clock_test_path, clock_test = latest('p29-display-clock-test-*')
    ps_read_path, ps_read = latest('p29-ps-readback-*', 'selected_registers_read_only_archived')
    ps_generated_path, ps_generated = latest('p29-ps-generated-comparison-*', 'selected_register_comparison_only')
    active = json.loads((ROOT / 'results/p29-active-build.json').read_text('utf-8'))
    work = Path(active['work'])
    stats = {name: utilization(path.parent / f'{name}-synth-utilization.rpt') for name, path in [('rf', rf_path), ('display', display_path)]}
    checks = {name: quality(path, name) for name, path in [('rf', rf_path), ('display', display_path)]}
    clock_checks = quality(clock_path, 'display', prefix='display-clock')
    assert clock_checks['checks']['no_clock'] == 0 and clock_checks['checks']['unconstrained_internal_endpoints'] == 0
    cdc = dict(rf=cdc_summary(audit_path.parent/'rf-compiled-cdc.rpt'),
               display=cdc_summary(clock_path.parent/'display-clock-cdc.rpt'))
    out = ROOT / 'results' / ('p29-delivery-' + stamp)
    out.mkdir(exist_ok=False)
    backup = ROOT / 'results' / ('p29-before-' + stamp)
    backup.mkdir(exist_ok=False)
    changed = ['START-HERE.md', 'TX-SOURCE-STATUS.json', 'README.md', 'docs/implementation-guide.md',
               'docs/design/new-board-tlz7xh-evm-review-20261017.md']
    for name in changed:
        target = backup / name
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(ROOT / name, target)
    evidence = {name: rel(path) for name, path in [('rf_synthesis', rf_path), ('display_synthesis', display_path),
        ('display_upgrade', upgrade_path), ('adi_package', package_path), ('sources', sources_path),
        ('compiled_audit', audit_path), ('rx_readback', capture_path), ('integration', integration_path),
        ('hls_vendor_patch', patch_path), ('boot_package_comparison', ps_boot_path),
        ('display_clock_refinement', clock_path), ('display_clock_self_check', clock_test_path),
        ('PS_readback', ps_read_path), ('PS_generated_comparison', ps_generated_path)]}
    report = dict(created_utc=now.isoformat(), status='independent_builds_verified_with_release_gaps',
                  work=str(work), part='xc7z100ffg900-2', tool='Vivado 2021.1', evidence=evidence,
                  display_project=active.get('display_short_project', str(work / 'display-v3/axi_video_display.xpr')),
                  resources=stats, synthesis_timing=checks, RF_transmitted=False,
                  refined_display_clock_timing=clock_checks, cdc_summary=cdc,
                  new_bitstream_programmed=False, project_bitstream_generated=False,
                  RF_display_integrated=False, display_functional_upgrade_verified=False,
                  real_AI_verified=False, lossless_stream_verified=False,
                  python_regression_rerun=False, previous_python_regression_passed=864,
                  board_mode='rf', old_TX_package_restored=False,
                  board_operations=['documented old-board login', 'one factory overlay rebind after startup failure',
                                    'restore previously reviewed RX manual/0dB/2450MHz profile',
                                    'receive-only sparse 16-buffer smoke and checksum readback',
                                    'read-only ten SLCR words; no register writes'],
                  source_hash_validation=sources['status'], backup=rel(backup))
    # Archive final DCPs with their reports so the compile evidence is not only
    # an external work-folder reference. These are NOT programmable bitstreams.
    for mode in ['rf', 'display']:
        shutil.copy2(work / f'{mode}-synth.dcp', out / f'{mode}-synth.dcp')
    shutil.copy2(work/'display-clock-reviewed.dcp', out/'display-clock-reviewed.dcp')
    (out / 'report.json').write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    rows = '\n'.join(f'| {mode} | {int(s["Slice LUTs"])} | {int(s["Slice Registers"])} | {s["Block RAM Tile"]:g} | {int(s["DSPs"])} | {checks[mode]["WNS_ns"]:+.3f} | {checks[mode]["WHS_ns"]:+.3f} |' for mode, s in stats.items())
    links = '\n'.join(f'- {name}：[原始报告](../../{path})。' for name, path in evidence.items())
    document = f'''# EXP-HW-021：重连恢复与 RF/显示独立原厂工程迁移

- 日期：2026-10-19；截止 {now.astimezone().strftime('%H:%M:%S %z')}。
- 结论：**两份 XC7Z100 独立工程已在 Vivado 2021.1 完成综合；没有完成合并、布局布线时序验收或新位流上板。**
- 本轮未发射射频。保留 D 盘原件、失败尝试和前轮真实 RF 证据；没有修改信号处理/AI 算法或自研 RTL。
- 被测版本为现有未提交工作区；各阶段归档实际 Tcl/脚本哈希、原厂源清单与编译日志，不用一个不含这些未提交文件的 HEAD 冒充被测提交。

## 板卡重新连接后的实测

1. 枚举并按 Linux 身份确认旧 COM9=PZSDR P201、新 COM8=TLZ7xH-EVM。旧板已重启回到 getty，先用已记录的默认账号登录；仅见 banner 的早期识别启发式曾返回 false，之后实际 uname/命令返回码确认登录成功。重连证据在 `results/p29-reconnect-20261019T081632Z/` 与 `results/p29-board-status-20261019T081712Z/`。
2. 新板 `/etc/board-mode=rf`，但只有 XADC。完整启动日志显示 AD9361 在 **真实 attempt 1/2/3 都读出 PRODUCT_ID 0xFF，最终退出失败**。因此前轮未覆盖的实际重试/耗尽分支今天确实发生；它没有自动恢复成功。证据：`results/p29-rf-startup-diagnosis-20261019T081802Z/report.json`。
3. 保存位流/overlay/启动脚本信息后，只重绑定一次原厂 `pl` overlay，未换位流、未重启。即时检查过早曾返回未就绪；后续日志与独立检查确认 PHY、ADC、DDS 均出现。**只能判定这次开机后可恢复，不能宣布冷启动问题已修复。** 证据：`results/p29-rf-rebind-20261019T081902Z/` 与 `results/p29-rf-rebind-check-20261019T081930Z/`。
4. 备份运行属性后，仅恢复此前已验证的 RX `manual / 0 dB / LO 2450 MHz`，读回 Fs 30.72 MS/s、BW 18 MHz、A_BALANCED。没有写 TX 或改变采样率。证据：`results/p26-rx-profile-restore-20261019T082645Z/report.json`。
5. 复用已验证的 ARM 原生程序，16 DMA 缓冲接收/释放通过，搬运 1,048,576 帧，保存 16,384 帧，约 0.03424 s；**只保留 1.5625% 稀疏诊断样本，来源未知，不是新已知源链路/AI/无丢样验收**。电脑回收到 65,536 B，SHA256 `{capture['raw']['sha256']}` 与板端一致。
6. 最后再次确认两板身份、旧板无活动 TX、新板 RF 三设备检查通过。串口已释放。旧 TX 临时包本轮未恢复；不能直接运行昨日 `/tmp` 路径。风扇 gpio914 读 0 是既有读回限制，不能据此断定停转。

启动日志还存在 EXT4/FAT 非正常卸载恢复信息；未对已挂载文件系统运行修复工具。关机继续按既有 sync/正常关机流程，诊断字节现已存电脑。

## 迁移实施与纠错

- 独立 E 盘目录：`{work.as_posix()}`。只提取新板显示工程子目录及 ADI 源码，不修改 D 盘包。
- RF `system_bd.tcl` 的 2017.4 版本声明在副本改为 2021.1 后，仍必须实际生成 IP、验证 BD 和完整综合，不能把更改版本号当兼容证明。
- 初次 ADI 封装失败：旧 helper 按绝对路径重排已被 packager 登记为相对路径的 XDC。适配为按规范路径复用文件并用存储名称重排；保留 XDC 原内容和 SCOPED_TO_REF。随后 **11 个 IP 全部封装通过**。
- 独立源核验覆盖 {sources['checked_files']} 个初始文件记录。D 盘原件/压缩包哈希不变，RF 副本 HDL/XDC 与原件相同；显示手写源核验 {sources['display_handwritten_sources_checked']} 项，无改动。11 项 XDC/TTCL 引用全部存在，无同 fileset 重复项，AD9361 的 5 个 XDC 作用域保留。IP 元数据/生成目录允许按工具重建，逐项变化有存档。
- 显示首轮错误地升级互连内部 xbar/auto_pc，验证拒绝；改为只从顶层 IP 升级。v2 BD 验证通过后门禁退出 32，保留 22 项关键元数据差异供审查。最终 v3 只允许已检查的精确差异，PS7/外设窗口不漂移，结构验收通过。
- 一次显示打开遇到安装目录 Tcl 读取错误，原始失败保留；RF 综合结束后单独重试成功。根因未证实，后续重任务串行执行，不据此修改安装文件。
- 显示第一轮综合遇到明确的 Windows 长路径错误 `IMPL 213-66`，导致后续找不到 TPG 模块；没有删掉 TPG 或改功能。完整复制到短路径 `E:/p29d-1019`，源文件哈希一致，只重置失败 TPG 和顶层运行后重试。原始失败在 `results/p29-display-synth-20261019T084313Z/`，复制清单在 `results/p29-short-display-20261019T085219Z/`。
- 短路径重试进一步暴露 `core_revision 2610191655` 超出 32 位有符号整数的 Y2K22 故障。按 AMD AR76960，从官方文档附件 API 下载 3988 B 补丁 ZIP，记录下载 URL/哈希并检查内容；用工具自带 Python 安装，读回确认 Vivado 与 Vitis_HLS 两处补丁文件均与下载字节一致，原 `automg.tcl` 哈希不变。**未修改系统时间、许可证、工程算法或工具原脚本**；只添加官方补丁与安装日志。补丁后新进程实际重试综合，不能仅凭安装脚本退出 0 判定成功。
- 显示升级包含 Clocking Wizard 5.4→6.0、VTC 6.1→6.2、TPG 7.0→8.1；**8 项 VTC 默认参数及新增端口的功能影响尚未上板/仿真核验**，已记录门禁标识。

## 完整综合结果与验收边界

| 独立工程 | LUT | 寄存器 | BRAM Tile | DSP | 综合 WNS/ns | 综合 WHS/ns |
|---|---:|---:|---:|---:|---:|---:|
{rows}

这是独立原厂工程，不包含项目 FFT/AI/合并链路。资源不能直接相加作为合并后的实测数。

- RF 综合：no_clock=0、unconstrained_internal_endpoints=0，但 **7 个输入、10 个输出缺接口时延约束**；综合 WHS 为负，不能称为时序通过。个别 IP 的 OOC 日志有时钟分组查询警告，主工程综合退出 0 不会消除这些记录。
- 保持时间以布局布线后结果为准；本轮没有用放宽周期或删除约束使报告变绿。`audit` 保存 DRC、CDC、IO、时钟与时钟交互报告；这些报告是后续修复输入，不等于所有检查通过。
- 显示的具体约束/CDC/DRC 数量见原始审查报告与机器报告。最终 DCP 已随 [交付记录](../../{rel(out / 'report.json')}) 存电脑；DCP 不是可烧写位流。
- RF CDC 汇总有 **59 条 Critical、1775 条 Warning**；显示补充时钟后仍有 2 条 CDC Warning。它们是结构工具发现项，不自动等同于实际硬件失效；但未逐项审查设计意图与已有例外前不能豁免或称 CDC 通过。DRC 基线 RF 为 17 条 Warning/56 条 Advisory，显示为 40 条 Warning/2 条 Advisory，没有把报告生成退出 0 写成零问题。
- 本轮未创建新的自研 RTL 功能模块，适用验证是原厂设计的迁移/完整综合/报告审查。将来新增/合并自研 RTL 仍需项目规定的自检 TestBench；本轮不冒称模块功能仿真通过。
- 上轮 **864 passed** 保持为历史回归；本轮未改算法，未重跑或虚报新的全回归数量。

## 已修复的显示二分频时钟模型

检查发现原厂 `parity_flag` 翻转触发器的输出被用作 LVDS 时钟，但缺派生时钟声明。先对原厂未改 RTL 与原生 UNISIM BUFG 模型运行自检：**35 个完整二分频周期、3 次异步复位、74 个有效输入周期通过**；范围仅为时钟/复位，不包含完整 RGB 映射与面板电气。

新增 `fpga/constraints/display_lvds_half_clock.xdc` 与 `fpga/tb/tb_display_half_clock.sv`，把约束加入短路径工程副本并完整重综合。实际像素时钟周期 **6.734 ns**，派生时钟 **13.468 ns**；没有改主时钟周期或删除路径。**no_clock 21→0，unconstrained_internal_endpoints 65→0**。

补充后的综合 WNS={clock_checks['WNS_ns']:+.3f} ns，WHS={clock_checks['WHS_ns']:+.3f} ns；56 个输出仍缺外部时延。保持时间变差反映原先漏检的路径被纳入分析，不能回删约束掩盖它。`display-clock-reviewed.dcp` 保留新结果，原 `display-synth.dcp` 保留修补前基线，尚未布局布线/上板。

## 合并规划与未完成工作

[合并核对表](../design/rf-display-integration-20261019.md) 已给出地址/DDR 端口/时钟/PS 配置依赖。静态检查共有 {len(integration['ps7_parameter_deltas'])} 项双方显式 PS 参数值不同，显式引脚分配直接重复为 0；缺省字段、隐式差分负脚、IO bank 电压仍须另查。

两套资料中预编译 `fsbl.elf` 和 `BOOT.BIN` 分别逐字节相同；源码包根 `ps7_init.c` 已提取供审查，但没有据此认定它就是预编译 ELF 的构建输入，也尚未识别当前实际启动分区内的 BOOT 字节。此结果支持保留已工作的启动链，不能支持从 RF 的通用 PS 配置重新生成启动包。

另对新板 10 个 SLCR 字做了只读采集，没有写寄存器。与两份 IP 生成的 PS-init 掩码比较：显示匹配 **5/10**，RF 匹配 **2/9**（另一字未写，不能判匹配）。显示 4 个 FCLK 控制字匹配，但若干 MIO 不匹配；Linux 可在启动后修改这些寄存器，不能从这个局部对照推导完整启动初始化。RF 使用 SPI1，触摸使用 SPI0；EMIO[0] 与 RF[46:32]/[47:48] 的规划已核对源码，合并仍需验证驱动位号和新顶层。

优先顺序：①以实际新板启动配置核对 PS7、MIO 电气、串口、64 位 RF EMIO、FCLK；②确认显示 IP 升级行为与约束；③在第三份副本合并 RF/显示并校验地址、中断、时钟/复位、CDC；④实现与时序/IO 验收；⑤保留原厂回滚路径后分别验证接收、屏幕、并行运行。

冷启动 0xFF 根因、长期完整无丢样、真实 AI 数据/模型与整机延迟/吞吐仍未完成。旧真实三调制有限快照证据继续保留；今天的接收烟测不能替代它或扩展结论。

## 原始证据与复现

{links}

复现顺序：`p29_prepare_build.py` → `p29_patch_adi.py` → `p29_run_vivado.py package` → `rf` → `p29_prepare_migration.py` → `display-upgrade` → `rf-synth`。显示使用短路径候选与已核验官方 HLS 补丁再运行 `display-synth` → `audit`；当前短路径恢复指针在 `results/p29-active-build.json`，不要覆盖它后直接在长路径重跑。重型 Vivado 阶段依次运行；不在 D 盘原件运行 `-force` 创建。`p29_verify_sources.py` 与 `p29_integration_audit.py` 为只读离线核验。安装补丁脚本拒绝覆盖已有补丁，已经安装后不重复安装。

时钟补充复现：`p29_display_clock_test.py` → `p29_prepare_clock_refinement.py` → `p29_run_vivado.py display-clock`；约束已经加入后不重复 add/reset，先查当前工程。普通显示重综合无需重置已成功的 TPG。若要重现修补前基线，使用已归档 DCP 或未加本轮 XDC 的副本，不冒用当前工程输出。

本轮入口备份：`{rel(backup)}/`。`results/` 被 Git 忽略，备份项目时必须包含它及 E 盘工作源，不能只依赖 git diff。

工具依据：[AMD upgrade_bd_cells](https://docs.amd.com/r/en-US/ug835-vivado-tcl-commands/upgrade_bd_cells)、[AMD Y2K22 官方修复](https://docs.amd.com/r/en-US/76960/Solution)、[ADI 2021_r1 IP 约束源](https://github.com/analogdevicesinc/hdl/blob/hdl_2021_r1/library/axi_ad9361/axi_ad9361_constr.xdc)。没有照抄其他载板的引脚或凭空填写板级时延。
'''
    (ROOT / RECORD).write_text(document, encoding='utf-8', newline='\n')
    state = json.loads((ROOT / 'TX-SOURCE-STATUS.json').read_text('utf-8'))
    state.update(updated=now.isoformat(), updated_note='HW-021: receiver recovered; independent RF/display synthesis passed; merge/timing/hardware gates remain',
                 status='independent_RF_display_synthesis_verified; integration_and_release_gates_pending', record=RECORD)
    state['p29_vendor_migration'] = report
    state['new_board_build_readiness'].update(status='independent_RF_display_synthesis_verified_with_gaps',
        evidence=rel(out / 'report.json'), rf_display_integration_verified=False, bitstream_generated=False)
    state['new_board']['current_mode'] = 'rf (2026-10-19 readback; factory overlay recovered after boot retries exhausted)'
    state['board_runtime_asof_20261019'] = dict(evidence=rel(capture_path), old_TX_active=False,
        old_TX_temporary_package_restored=False, new_RX_profile='manual/0dB/2450MHz/30.72MSps/18MHz/A_BALANCED',
        cold_start_issue_resolved=False, actual_boot_retry_attempts_2_and_3_exercised=True,
        all_three_boot_attempts_failed=True, postboot_factory_overlay_rebind_recovered=True,
        RX_native_binary='/tmp/p27-rx-diag-082709', serial_ports_released=True)
    (ROOT / 'TX-SOURCE-STATUS.json').write_text(json.dumps(state, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    entry = (ROOT / 'START-HERE.md').read_text('utf-8')
    tail = entry[entry.index('## HW-019'):]
    (ROOT / 'START-HERE.md').write_text(f'''# 从这里恢复项目工作

最新进度：2026-10-19。先读 [HW-021]({RECORD}) 与 [恢复清单](docs/handoff/RESUME-20261019.md)。

- XC7Z100 的 RF、显示原厂工程已分别在 Vivado 2021.1 完整综合通过；不是最小玩具工程。D 盘原件未改，E 盘副本与 DCP/日志已保存。
- **尚未合并、未布局布线验收、未烧写新位流。** RF 外部时延约束、综合保持时间和显示 IP 升级行为仍待处理；PS7/MIO/EMIO/FCLK 差异见 [合并核对表](docs/design/rf-display-integration-20261019.md)。
- 显示漏建的二分频时钟已用原生仿真及重综合修补：no_clock 21→0、内部未约束 65→0；仍有外部时延/保持时间和 RF CDC 待验收，不把修补结果当时序通过。
- 新板本次启动三次 AD9361 0xFF 都失败；一次开机后原厂 overlay 重绑定恢复。冷启动根因未解决。RX 已恢复 manual/0dB/2450MHz，16 缓冲只接收烟测及稀疏字节回收通过；未发射。
- 旧板登录恢复，但重启后的 TX 临时包尚未重传，不能直接复用昨日 `/tmp` 路径。当前两串口均释放，新板仍 rf；黑屏符合现有互斥位流。
- 长期完整无丢样、真实 AI、RF/显示并行与整机吞吐仍未完成。864 项回归是上轮结果，本轮未重跑。
- 不重跑 P26/P27 旧总结生成器覆盖入口。`results/` 被 Git 忽略，须连同原始证据保存。

以下为历史进度，仅在上面的新状态未覆盖范围内参考。

{tail}''', encoding='utf-8', newline='\n')
    resume = f'''# 恢复清单：2026-10-19

先读 [HW-021](../experiments/EXP-HW-021-vendor-migration-and-reconnect.md)。

1. 枚举串口、核验两板身份；今天旧 COM9、新 COM8。串口不能被两个程序同时占用。旧板重新上电后需登录，不能直接在 getty 发送 Linux 命令。
2. 新板检查 rf 模式及三类 IIO 名称。今天真实启动三次失败，开机后单次原厂 overlay 重绑定并等待设备初始化后恢复；保留启动原始日志，不将即时未就绪当最终结果。不盲目改 GPIO、反复烧写或把重试耗尽说成已修复。
3. 重新读回 RX 属性；本轮恢复的是 manual/0dB、LO2450MHz、Fs30.72MS/s、BW18MHz、A_BALANCED。重启会重置运行属性。风扇 gpio914 的 value=0 已知不可靠。
4. 旧 TX `/tmp` 包本轮未重传，启动任何发射前按 [上一轮恢复清单](RESUME-20261018.md) 上传、8 项哈希、inspect、6 支 check、最新 boot_id 与原有限时守卫全部核验。不能因用户说连接好就推断 TX 条件已恢复。
5. 本轮原生接收程序位于新板 `/tmp/p27-rx-diag-082709`；重启后用既有 `p27_smoke.py` 重新上传/校验。今天只接收烟测原始字节已回电脑：`{rel(capture_path.parent)}/prefixes.bin`，仅诊断用途。
6. FPGA 副本在 `{work.as_posix()}`。RF xpr=`rf/runs/ad-fmcomms3-ebz-xc7z100.xpr`；最终显示构建副本=`{active.get('display_short_project', str(work / 'display-v3/axi_video_display.xpr'))}`。长路径 v3 和 v1/v2 保留用于失败/差异证据；不要在长路径重跑触发 HLS 路径限制，不要把 v2 的退出 32 忽略。
7. 优先处理 [合并核对表](../design/rf-display-integration-20261019.md) 中的 PS 基线/时钟与显示升级/约束，再在第三份副本集成。不要直接覆盖 BOOT.BIN/FSBL、原厂位流和 overlay 配对。
   当前短路径副本已加入 `p29_lvds_half_clock.xdc`：无时钟/内部未约束项清零，但显示 WHS=-1.221ns、56个输出时延缺项，RF CDC Critical 待审查。两份 PS-init 与局部实测都非完整一致，不盲目生成新的启动链。
8. 新增 RTL 必须有自检 TestBench；生成新位流前完成实现/CDC/IO/时序，之后分项验收真实 RX、显示、并行运行。没有证明长期无丢样或真实 AI。

本机源码、DCP、日志和稀疏数据均已存盘；断电会丢运行会话/部分 RAM 临时文件，不会丢电脑工程。停止实验时先停止接收/限时发射，保存结果，再 sync/正常关机。板上未保存的临时程序需下次恢复。
'''
    (ROOT / 'docs/handoff/RESUME-20261019.md').write_text(resume, encoding='utf-8', newline='\n')
    for name, link in [('README.md', RECORD), ('docs/implementation-guide.md', 'experiments/' + Path(RECORD).name),
                       ('docs/design/new-board-tlz7xh-evm-review-20261017.md', '../experiments/' + Path(RECORD).name)]:
        path = ROOT / name
        text = path.read_text('utf-8')
        heading, rest = text.split('\n', 1)
        prefix = f'\n\n2026-10-19 更新：[HW-021]({link}) 已完成新板接收恢复和 RF/显示独立完整综合；原厂源未改、未烧写新位流。合并、接口约束/时序、显示升级功能及冷启动可靠性仍待验收。旧工具阻塞现已解除；下文早期“待授权/找不到器件”为历史状态。\n'
        if name == 'README.md':
            rest = re.sub(r'最新推进：\[HW-019\].*?\n\n', '前轮采样基线：[HW-019](docs/experiments/EXP-HW-019-memory-diagnostic-and-build-readiness.md)，512 缓冲稀疏诊断；真实 AI、完整无丢样和独立显示共存尚未完成。\n\n', rest, count=1, flags=re.S)
        path.write_text(heading + prefix + rest, encoding='utf-8', newline='\n')
    print(out)


if __name__ == '__main__':
    main()
