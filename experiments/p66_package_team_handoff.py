"""Package the screen team's prompt, verified baseline, source, tests and references."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def digest(data):
    return hashlib.sha256(data).hexdigest()


def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT / 'exports' / ('tjc-screen-team-' + stamp)
    out.mkdir(parents=True, exist_ok=False)
    files = {}
    def add(path, target=None):
        path = Path(path)
        target = target or path.relative_to(ROOT).as_posix()
        files[target] = path.read_bytes()
    for folder in ('embedded/source_panel',):
        for path in (ROOT / folder).rglob('*'):
            if path.is_file():
                add(path)
    for name in (
        'configs/tjc-source-page.json', 'configs/tjc-source-screen.json',
        'src/rfsig/tjc_protocol.py', 'src/rfsig/__init__.py', 'src/rfsig/bpsk.py',
        'tests/test_tjc_protocol.py', 'tests/native/check_source_panel.py', 'tests/native/check_panel_wire.py',
        'docs/design/tjc-source-screen-20261025.md',
        'docs/experiments/EXP-P61-TJC-docs-20261025.md',
        'docs/experiments/EXP-P62-TJC-model-20261025.md',
        'docs/experiments/EXP-P63-source-panel-20261025.md',
        'docs/experiments/EXP-P65-COM10-control-20261025.md',
        'docs/handoff/RESUME-P63-20261025.md', 'docs/handoff/RESUME-P65-20261025.md',
        'docs/WORKFLOW-NEXT-20261024.md',
        'results/p63-tjc-protocol-tests-20261025.xml',
        'results/p63-final-20261025T053937Z/report.json',
        'results/p66-seed-20261025T134950Z/report.json',
        'results/p66-seed-20261025T134950Z/inspection.json',
        'results/p62-tjc-model-20261025T041434Z/TJC4827T143_011C_I_P20.pdf',
    ):
        add(ROOT / name)
    seed = ROOT / 'results/p66-seed-20261025T134950Z/official-T1-seed.HMI'
    if digest(seed.read_bytes()) != json.loads((seed.parent / 'report.json').read_text('utf-8'))['seed_sha256']:
        raise ValueError('Baseline HMI changed')
    add(seed, 'HMI/p201-source-BASELINE-NOT-FINISHED.HMI')
    for name in ('offline.png', 'ready.png', 'running.png'):
        add(ROOT / 'results/p63-page-preview-20261025T044959Z' / name, 'design-preview-NOT-SCREEN/' + name)
    installer = Path('E:/FPGA_Tools/Downloads/TJC-20261025T060628Z/USARTHMIsetup_latest.zip')
    installer_data = installer.read_bytes()
    if digest(installer_data) != 'e5f603313605af5727fb1342f6880b24ea7169f93f88f57527afee4122b9b07b':
        raise ValueError('Official installer changed')
    files['tools/USARTHMIsetup_latest.zip'] = installer_data
    files['requirements-screen-tests.txt'] = b'numpy\npytest\n'
    prompt = '''请作为本项目的串口屏模块开发助手，直接完成可编辑工程和可验证功能，并与队友配合操作实屏。

任务：旧P201开发板通过淘晶驰串口屏控制射频信号源。用户型号TJC4827T143 011C P20，480×272。官方编辑器目标TJC4827T143_011。不要将官方参考规格的_I_P20后缀自动等同实物。

先读00-READ-ME.md、embedded/source_panel/README.md、configs/tjc-source-page.json和configs/tjc-source-screen.json。

现状：已有纯C状态机、原生串口回包解析、Python协议编解码及测试；已有官方编辑器建立的基础HMI，但只有页面与一个基础触摸区域，绝非成品。编辑器里后来添加过按钮、文本、数字、定时器、变量模板，但它们未被确认保存，因此本包不把这些内存改动当成果。三个PNG只是设计预览。

按顺序完成：
1. 四类选择：TONE/BPSK/QPSK/16QAM；时长8～60秒，默认15秒；应用、开始、停止。布局和计划ID见JSON。
2. 显示选择、时长、连接和运行状态。上电OFFLINE，无自动发射；板端确认后才显示READY/RUNNING。
3. 核实页面和控件实际ID，弹起事件采用标准0x65回包与三个FF结尾，避免重复发送；实现必要字库、工程身份和新鲜心跳约定。
4. 官方模拟器检查按钮回包、状态下发与断线显示；用官方编辑器编译，保存日志。交付可编辑HMI、TFT、控件/协议清单、截图、下载步骤。
5. 界面完成后才对接板端真实UART/guard服务。复用现有状态机，确认停止、超时、断线停止和清理；不把不可信屏幕文本拼成系统命令。

首版预设固定：LO2450MHz，偏移+960kHz，Fs30.72MS/s，Rs240ksym/s，增益−10dB，峰值256。不得随意开放射频参数范围。

不要修改新板接收/AI/启动配置；不要复用旧板电脑调试终端作屏幕UART。没有实际接线与衰减审核，不发射RF；不格式化任何板卡启动卡。

每次保存实验记录。区分源码检查、官方编译、模拟器、实屏和RF验收；只凭编译通过不能宣称实屏已完成。需要人操作时给队友准确步骤。优先完成标准官方HMI工作流，不依赖未验证的跨型号第三方编译器。
'''
    files['01-PROMPT-FOR-AI.txt'] = prompt.encode('utf-8-sig')
    readme = '''# 串口屏模块队友交接包（2026-10-25）

把本包解压到一个新目录，不覆盖原项目。将01-PROMPT-FOR-AI.txt发给AI，队友配合操作编辑器和实屏。

## 已完成和未完成
- .NET3.5已在原电脑安装成功，官方编辑器主界面已正常打开。
- 本包HMI是已校验的基础快照：480×272、TJC4827T143_011、页面与一个bTone触摸区域；不是完整控制界面。
- 纯C控制/回包组件有历史测试和P201无IO自检证据，真实UART/guard适配层尚未实现。
- 未生成本阶段TFT、未下载实屏、未验收实体UART和屏控RF。
- 原电脑编辑器可能仍有未保存模板；已归档HMI不含这些未确认保存的改动。

## 文件说明
- HMI/：官方基础工程，建议另存新名字后开发。
- design-preview-NOT-SCREEN/：布局参考图，不能当成实屏证据。
- embedded/source_panel/：控制逻辑与协议解析C源码、自检工具和接口契约。
- configs/：页面/按钮ID计划、实物型号和电气核对边界。
- src/与tests/：Python协议和测试；__init__/bpsk仅为原包导入依赖，不是本模块开发目标。
- docs/：之前有用的设计、实验记录和恢复清单。部分历史相对链接指向完整项目，本包未全部包含，不代表这些环节已验收。
- results/：历史检查报告、官方参考规格、种子工程解析证据。规格PDF带_I_P20后缀，必须核对实物，不能按线色猜针序。
- tools/USARTHMIsetup_latest.zip：已从厂商取得并校验的官方安装包，供队友电脑需要时使用。
- MANIFEST.json：包内每个文件的字节数和SHA256。

## 原电脑软件入口
E:/FPGA_Tools/TJC-USARTHMI-20261025T112418Z/app/APPDIR/USART HMI.exe
工作目录应为APPDIR。原电脑.NET问题已解决，不要再次安装。队友电脑如缺.NET3.5，应按自身Windows版本启用系统组件，不套用原电脑缓存包。

## 可选离线检查
Python：安装requirements-screen-tests.txt后，在本包根目录设置PYTHONPATH=src，运行python -m pytest tests/test_tjc_protocol.py。
C：在有gcc的Linux/WSL环境编译panel_logic_check.c与panel_wire_check.c（C11、-Wall -Wextra -Werror，头文件在同目录）；各程序--selftest只做无IO检查。
原生回放检查脚本位于tests/native，需要把已编译程序与新的结果目录作为参数。它们不会操作板卡或发射RF。

## 交付目标
完整可编辑HMI、官方编译TFT、真实控件ID/串口协议表、编译/模拟器证据、实屏验证记录和下载说明。最后再与主项目对接板端服务。

厂商资料：http://wiki.tjc1688.com/
串口下载：http://wiki.tjc1688.com/start/create_project/create_project_9.html
SD下载：http://wiki.tjc1688.com/start/create_project/create_project_10.html
'''
    files['00-READ-ME.md'] = readme.encode('utf-8-sig')
    manifest = [dict(path=name, bytes=len(content), sha256=digest(content)) for name, content in sorted(files.items())]
    files['MANIFEST.json'] = (json.dumps(manifest, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    packed = out / 'TJC-screen-team-handoff.zip'
    with zipfile.ZipFile(packed, 'x', zipfile.ZIP_DEFLATED, compresslevel=3) as archive:
        for name, content in sorted(files.items()):
            archive.writestr(name, content)
    with zipfile.ZipFile(packed) as archive:
        if archive.testzip() is not None:
            raise ValueError('ZIP CRC failed')
        for row in manifest:
            content = archive.read(row['path'])
            if len(content) != row['bytes'] or digest(content) != row['sha256']:
                raise ValueError('Member verification failed')
    report = dict(status='verified_screen_team_handoff_ZIP_CRC_and_all_member_SHA',
        path=str(packed), bytes=packed.stat().st_size, sha256=digest(packed.read_bytes()),
        files=len(files), HMI_complete=False, HMI_compiled=False, TFT_downloaded=False,
        current_board_operations=False, live_unsaved_editor_changes_included=False)
    (out / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == '__main__':
    main()
