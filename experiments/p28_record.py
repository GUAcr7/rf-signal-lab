"""Publish the verified tool-setup milestone without promoting RF/AI claims."""
from datetime import datetime, timezone, timedelta
import hashlib
import json
import os
from pathlib import Path
import shutil

ROOT = Path(__file__).resolve().parents[1]


def read(path):
    return json.loads(path.read_text('utf-8-sig'))


def relative(path):
    return path.resolve().relative_to(ROOT).as_posix()


def main():
    upgrade_path = ROOT / 'results/p28-device-upgrade-20261018T141010Z/report.json'
    target_path = ROOT / 'results/p28-target-verification-20261018T141412Z/report.json'
    installed_path = ROOT / 'results/p28-license-install-20261018T140518Z/report.json'
    upgrade, target, installed = map(read, (upgrade_path, target_path, installed_path))
    log = target_path.with_name('stdout.txt').read_text('utf-8', errors='replace')
    license_path = Path(os.environ['APPDATA']) / 'XilinxLicense/Xilinx.lic'
    digest = hashlib.sha256(license_path.read_bytes()).hexdigest()
    if (upgrade['status'] != 'official_incremental_upgrade_completed' or
            upgrade['completion']['exit_code'] != 0 or target['status'] != 'target_synthesis_verified' or
            target['exit_code'] != 0 or not target['old_z020_part_visible'] or
            "Got license for feature 'Synthesis' and/or device 'xc7z100'" not in log or
            digest != installed['sha256'] or digest != target['license_sha256']):
        raise RuntimeError('tool acceptance incomplete; refusing to update project status')
    now = datetime.now(timezone.utc)
    stamp = now.strftime('%Y%m%dT%H%M%SZ')
    backup = ROOT / 'results' / ('p28-before-' + stamp)
    backup.mkdir(exist_ok=False)
    documents = ['START-HERE.md', 'TX-SOURCE-STATUS.json', 'README.md',
                 'docs/implementation-guide.md', 'docs/handoff/RESUME-20261018.md']
    for name in documents:
        source = ROOT / name
        destination = backup / name
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    doc = ROOT / 'docs/experiments/EXP-HW-020-vivado-enterprise-setup.md'
    if doc.exists():
        shutil.copy2(doc, backup / doc.name)
    doc.write_text(f'''# EXP-HW-020：Enterprise 试用授权安装与 XC7Z100 工具验证

- 日期：{now.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M:%S')}（北京时间）。
- 承接 [HW-019](EXP-HW-019-memory-diagnostic-and-build-readiness.md) 的工具阻塞。**授权安装、增量补装及 XC7Z100 最小综合已通过；射频/显示合并工程尚未完成。**

## 实际操作

1. 用户在 AMD 官方站点生成并下载 Enterprise 60 天试用节点许可证。原件仍在 `E:/FPGA_Tools/Downloads/Xilinx.lic`；仅核对字段，不改动签名内容。
2. 核对本机主机名与板载网卡；绑定 NIC 为 `40c2ba523054`。许可证包含 `Vivado_ML_Enterprise_Edition`、Enterprise package、Simulation 等特征，版本上限 2027.10，到期 **2026-12-17**。
3. 安装到 Windows VLM 明示的默认路径 `{license_path.as_posix()}`。源码与安装副本 SHA256 一致：`{digest}`。VLM 刷新后显示 Synthesis、Implementation 等节点授权和到期日。
4. 安装后初查仍找不到 XC7Z100；器件目录只有 Z007/Z010/Z012/Z014/Z015/Z020/Z030 系列。这是尚未安装该器件数据，不能误判为下载的许可证失效。
5. 备份原安装记录和安装配置，复用 E 盘已解压的 2021.1 完整离线安装包，通过原厂 `xsetup.bat -b Add` 管理员增量升级为 ML Enterprise，仅选择 Zynq-7000；不安装驱动，不更改工程文件或板卡。
6. 安装器退出 0，日志写明完成成功；器件目录新增 Z035/Z045/Z100 及对应工业级数据。新启动 Vivado 2021.1，精确目标 `xc7z100ffg900-2` 可枚举，最小直连端口工程成功综合并保存 DCP；实际日志记录获取并释放 Synthesis/xc7z100 许可。

## 证据与验收

| 事项 | 结果及证据 |
|---|---|
| 本机绑定与许可证字段 | 通过；[安装记录](../../{relative(installed_path)}) |
| Windows VLM 识别 | 通过；[管理器截图](../../{relative(upgrade_path.parent / 'license-manager-recognized.png')})；截图拍于清理重复副本前，同一证书条目曾重复列出 |
| 原厂增量安装 | 通过；[安装报告与前后目录](../../{relative(upgrade_path)})、[安装输出](../../{relative(upgrade_path.parent / 'upgrade.stdout.txt')}) |
| 新板 XC7Z100 精确型号 | 通过；[验证报告](../../{relative(target_path)})、[原始综合日志](../../{relative(target_path.parent / 'stdout.txt')}) |
| 原 XC7Z020 型号保留 | 通过：`get_parts xc7z020clg400-2` 可见；本轮没有重新编译旧板完整工程 |
| 最小综合产物 | [DCP](../../{relative(target_path.parent / 'probe-synth.dcp')})、[最小设计资源报告](../../{relative(target_path.parent / 'probe-utilization.rpt')})；不是项目资源占用 |
| 正式 RF/display 工程、实现、时序与位流 | 待验证；未执行、未生成项目新位流 |
| 板卡、串口、射频操作 | 本轮均未操作 |

## 过程修正与边界

- 第一次许可证保护解析把注释中的 `HOSTID=...;` 尾随标点算进绑定值，校验在复制前停止；修正为仅解析 INCREMENT 指令。正式安装记录保留实际签名文件哈希。
- 早期曾将同一许可证复制到用户 `.Xilinx` 目录；随后按 Windows 管理器路径导入，并仅清理本轮创建且字节一致的重复副本，备份在 E 盘工作目录，原始下载和默认安装副本均保留。
- 图形 `xsetup.exe` 启动器未提供可用 CLI 输出，改用官方 `bin/xsetup.bat`；管理员帮助明确列出 Add。ConfigGen 的配置输出和原配置备份保留；新增安装配置在独立 E 盘目录，未凭界面标题推断安装完成。
- 本轮不修改信号处理、AI 或项目 FPGA RTL，不新增算法验收。最小直连设计仅检查器件数据与许可，不是项目功能模块，不能替代后续模块 TestBench、完整工程实现与资源/时序验收。上轮 864 项 Python 测试结果保留，本轮没有冒称重新运行该回归。

## 恢复与下一步

- Vivado 仍为 `E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat`，许可证已持久安装；重启电脑不需要重新申请。已有工具窗口需重启后才能看到新增器件。试用到期后需取得新的有效授权。
- 不重装工具、不更换板卡固件；下一步先在独立工作副本复现原厂 RF 和显示工程。RF BD 源来自 2017.4，需按实际 IP 升级结果处理，不能跳过版本迁移验证直接合并或烧写。
- 合并后再核对 AXI 地址、时钟/复位、CDC、约束、资源和时序；取得新位流只代表可编译，仍须分别验收真实接收、屏幕和并行运行。
- 完整持续录制、长期无丢样、真实 AI 和整机延迟/吞吐仍是独立未完成项，HW-019 的稀疏数据限制全部保留。

原厂依据：[2021.1 增量添加器件](https://docs.amd.com/r/2021.1-English/ug973-vivado-release-notes-install-license/Adding-Additional-Tools-and-Devices?contentId=NtQne7O2nYjRY9wVu4KUEw)、[原厂批量安装](https://docs.amd.com/r/2021.1-English/ug973-vivado-release-notes-install-license/Running-the-Installer)。
本轮入口备份：`{relative(backup)}/`；所有采样证据仍在原位置。许可证不复制到项目 Git 文件中。
''', encoding='utf-8', newline='\n')
    state_path = ROOT / 'TX-SOURCE-STATUS.json'
    state = read(state_path)
    state.setdefault('build_readiness_before_p28', state.get('new_board_build_readiness'))
    state.update(updated=now.isoformat(), updated_note='HW-020: Enterprise evaluation installed; Z100 data added; exact-target synthesis verified',
                 record=relative(doc), status='native_sparse_rx_diagnostic_pass; XC7Z100_toolchain_verified; full_lossless_stream_real_ai_combined_display_pending')
    state['new_board_build_readiness'] = dict(evidence=relative(target_path), status='XC7Z100_minimal_synthesis_verified',
        part=target['part'], tool=target['tool'], same_PC_usable=True, checkout_attempted=True,
        evaluation_license_compatibility='verified_via_Vivado_2021.1_exact_target_synthesis',
        license_type='node_locked_60_day_evaluation', license_expiration='2026-12-17', license_path=str(license_path),
        license_sha256=digest, upgrade_evidence=relative(upgrade_path), user_has_lab_license=False,
        rf_display_integration_verified=False, bitstream_generated=False)
    state['p28_tool_setup'] = dict(record=relative(doc), license_install=relative(installed_path), upgrade=relative(upgrade_path),
        synthesis=relative(target_path), board_operations=False, full_python_regression_rerun=False)
    state_path.write_text(json.dumps(state, ensure_ascii=False, indent=2) + '\n', encoding='utf-8', newline='\n')
    start = ROOT / 'START-HERE.md'
    text = start.read_text('utf-8')
    header = '# 从这里恢复项目工作\n'
    if text.startswith(header):
        text = text[len(header):]
    start.write_text(header + f'''
最新工具进度：{now.astimezone(timezone(timedelta(hours=8))).strftime('%Y-%m-%d %H:%M')}（北京时间）。先读 [HW-020]({relative(doc)})。

- 已安装 Enterprise 节点试用授权（到期 **2026-12-17**），复用 E 盘离线包增量补齐 Zynq-7000；Vivado 2021.1 已对 **XC7Z100FFG900-2** 成功进行最小综合，实际许可获取/释放通过，原 XC7Z020 可枚举。工具阻塞已解除。
- 本轮没有操作板卡、串口或射频；未构建/烧写项目新位流。下一步独立复现 RF/display 原厂工程并验证版本迁移，再做合并。
- HW-019 采样基线继续有效：只保留 1.5625% 诊断样本；长期完整无丢样、真实 AI、射频与显示并行及系统吞吐仍未完成。864 项测试是上轮结果，本轮未重跑。
- 不重跑 P26/P27 总结生成器覆盖本轮工具状态；`TX-SOURCE-STATUS.json` 已指向 HW-020。

## HW-019 接收诊断基线（以下工具待办由 HW-020 更新）
''' + text, encoding='utf-8', newline='\n')
    for name, link in (('README.md', 'docs/experiments/' + doc.name),
                       ('docs/implementation-guide.md', 'experiments/' + doc.name),
                       ('docs/handoff/RESUME-20261018.md', '../experiments/' + doc.name)):
        path = ROOT / name
        text = path.read_text('utf-8')
        title, body = text.split('\n', 1)
        note = f'\n2026-10-18 工具更新：[HW-020]({link}) 已完成 Enterprise 试用授权安装、Zynq-7000 增量补装和 XC7Z100 精确型号最小综合。到期 2026-12-17；当前电脑可继续。下文授权/器件待办为历史状态，RF/display 合并及其上板仍未完成。\n'
        path.write_text(title + '\n' + note + body, encoding='utf-8', newline='\n')
    print(doc)
    print(backup)


if __name__ == '__main__':
    main()
