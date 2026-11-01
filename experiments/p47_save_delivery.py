"""Seal the portable learning delivery; does not inspect or operate hardware."""
import argparse
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import shutil
import sys
import xml.etree.ElementTree as ET
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from host.rf_learning_kit.data_api import load_kit


def sha(path):
    with path.open('rb') as stream:return hashlib.file_digest(stream,'sha256').hexdigest()
def read(path):return json.loads(path.read_text('utf-8'))
def rel(path):return path.resolve().relative_to(ROOT.resolve()).as_posix()
def write(path,value):path.write_text(json.dumps(value,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('build','gui','tests'):parser.add_argument('--'+name,type=Path,required=True)
    args=parser.parse_args();build=read(args.build);gui=read(args.gui);kit=Path(build['directory'])
    if (build['status']!='passed_portable_real_RF_kit_and_all_DMA_replays'
        or build['board_operations'] or not build['extracted_to_different_Unicode_path_verified']
        or not build['standalone_reference_came_from_extracted_kit'] or not build['all_ZIP_members_SHA_verified']):
        raise ValueError('complete portable package acceptance required')
    manifest,records=load_kit(kit)
    if sha(kit/'manifest.json')!=build['manifest_sha256'] or sha(Path(build['archive']['path']))!=build['archive']['sha256']:
        raise ValueError('distribution bytes changed')
    for name,item in build['inputs'].items():
        if sha(Path(item['path']))!=item['sha256']:raise ValueError('original P46 evidence changed: '+name)
    for path in (ROOT/'host/rf_learning_kit').iterdir():
        if path.suffix in ('.py','.md') and sha(path)!=sha(kit/path.name):raise ValueError('distributed code differs from checked source')
        if path.suffix=='.cmd' and path.read_bytes().replace(b'\r\n',b'\n')!=(kit/path.name).read_bytes().replace(b'\r\n',b'\n'):
            raise ValueError('distributed launcher differs')
    preview=read(Path(build['preview_report']));standalone=read(Path(build['standalone_report']))
    for reviewed in (preview,standalone):
        rows=reviewed['rows']
        if (len(rows)!=16 or {(r['key'],r['block_zero_based']) for r in rows}!={(k,b) for k in records for b in range(4)}
            or any(r['frames']!=64 or r['state']!='finished' for r in rows)):raise ValueError('not every DMA replay ended correctly')
    if (gui['status']!='passed_Tk_event_loop_timer_pause_and_snapshot' or gui['backend'].lower()!='tkagg'
        or gui['timer_frames']<2 or gui['board_operations'] or gui['AI_inference']
        or not Path(gui['golden_reference_module']).resolve().is_relative_to(kit.resolve())):raise ValueError('actual distributed GUI check missing')
    exported=Path(gui['exported_snapshot']);snapshot=read(exported/'report.json')
    if sha(exported/'analysis.npz')!=snapshot['analysis_sha256'] or snapshot['hardware_contacted'] or snapshot['ai_connected']:
        raise ValueError('GUI snapshot changed or has wrong scope')
    suites=list(ET.parse(args.tests).getroot().iter('testsuite'))
    passed=sum(int(x.get('tests','0')) for x in suites)
    if passed<8 or any(int(x.get(k,'0')) for x in suites for k in ('failures','errors','skipped')):raise ValueError('final controls tests not all passing')
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p47-delivery-%Y%m%dT%H%M%S%fZ');out.mkdir(exist_ok=False)
    (out/'executed.py').write_bytes(Path(__file__).read_bytes());shutil.copyfile(args.tests,out/'tests.xml')
    launcher=ROOT/'run-rf-learning-demo.cmd'
    launcher.write_bytes(('@echo off\r\nsetlocal\r\ncall "%~dp0'+rel(kit).replace('/','\\')+'\\run-demo.cmd" %*\r\nexit /b %errorlevel%\r\n').encode('ascii'))
    record='docs/experiments/EXP-P47-learning-kit.md';resume='docs/handoff/RESUME-P47-20261022.md'
    current=dict(status='portable_real_RF_learning_kit_and_offline_demo_delivered',updated_utc=now.isoformat(),
        report=rel(out/'report.json'),directory=str(kit.resolve()),archive=build['archive'],launcher=rel(launcher),record=record,resume=resume,
        reports={k:dict(path=rel(path),sha256=sha(path)) for k,path in vars(args).items()},
        records=4,DMA_buffers=16,raw_original_bytes=4194304,decoded_complex_samples=1048576,
        controller_tests_passed=passed,all_DMA_replays_verified=True,actual_Tk_event_loop_verified=True,
        extracted_package_independent_of_project_files=True,board_operations=False,AI_inference=False,
        independent_ML_benchmark_eligible=False,hardware_state_last_verified_by='p46_current',hardware_state_not_rechecked_this_phase=True)
    (ROOT/record).write_text(f'''# P47：真实数据学习包与一键离线回放

日期：2026-10-22（北京时间）。用户同意先完成队员数据包和离线演示；本轮只操作电脑文件，不连接板卡、串口或射频接口，不重启或修改任何固件。没有新增真实采集、实屏验收或AI结果。

## 输入与转换

父证据是P46采集/回传/质量报告，路径和SHA逐项见`{rel(args.build)}`。原始16个完整DMA块、4MiB打包RX1 I/Q逐项校验后保留原字节；按le:S12/16>>0只取低12位再符号扩展。分别输出4种源（单音、BPSK、QPSK、16QAM）的int16 `[4,65536,2]` 与complex64 `[4,65536]`，合计1048576复数点。I/Q与原ADC码值逐点完全相等，不归一化、不滤波、不扁平拼接未知间隔。

数据包含采样率30.72MS/s、LO2450MHz、BW18MHz、RX manual0dB、TX−10dB、数字峰值256、种子/周期/源SHA、软件refill时间和逐块已知参考质量。index.csv每行对应一个DMA块；原始采集、回传、质量报告及黄金分析模块副本随包保存。标签来自发送配置，ai_prediction为空；同源循环窗口仅用于学习/调试，不划分训练/测试。

## 交付

- 本机入口：`{rel(launcher)}`；包内入口：`{rel(kit/'run-demo.cmd')}`。
- 队员分享ZIP：`{rel(Path(build['archive']['path']))}`，{build['archive']['bytes']/1024/1024:.2f}MiB，SHA256 `{build['archive']['sha256']}`。
- 中文说明：`{rel(kit/'README.md')}`；读取示例：example_read.py；预览：包内previews/。

当前电脑可直接双击入口。其他电脑完整解压后需要Python及NumPy/Matplotlib/Tk；setup.cmd可首次安装依赖，之后离线运行。本包不是免Python安装的exe。运行环境已记录并固定本次验证依赖版本。

## 回放口径与检查

界面提供信号选择、DMA块选择、开始/暂停、重新播放、全频段切换及PNG/NPZ/JSON导出；一块64个1024点分析帧，播放到末尾自动停止，切块/切类清空旧曲线与瀑布图。块内时间轴不跨未知DMA缺口；名义采样时间与GUI播放速度独立。PSD用counts²/Hz，功率不是dBm，99% ROI能量宽度不是经过验证的目标带宽。界面醒目标记已保存数据和已知发送标签，未运行AI。

全部16块在分发副本和另一个含空格/中文的临时解压路径分别完成有限回放，读取示例成功；独立解压检查确认黄金参考模块来自包内，不依赖原项目源码。ZIP CRC与全部成员SHA通过。

最终8项控制器/完整性测试通过：`{rel(args.tests)}`，覆盖码值/复数一致性、损坏文件拒绝、重写NPZ哈希后仍与原始码值复核、拒绝冒充独立ML数据集、路径越界、暂停/结束/复位、切块切类清历史、导出原始帧。最初测试误读analysis.json（实际导出名report.json），已改正测试，原失败XML `results/p47-controls-and-integrity-20261022.xml`保留；程序导出协议没有因此修改。

交付保存脚本首次从experiments目录直接执行时未把项目根目录加入模块搜索路径，导入host失败且尚未写入交付状态；改为显式添加根目录后执行。该失败没有打开端口或修改板卡。

实际通过Windows分发run-demo.cmd启动Tk图形窗口，自动计时播放{gui['timer_frames']}帧、暂停、导出截图及数据后自动关闭：`{rel(args.gui)}`。这验证图形事件循环和自动回调，不声称人工鼠标操作或新板实体屏验收。截图/数据SHA后验通过。

## 当前边界与后续

原始P46证据未修改，硬件启动/收发/屏幕状态仍以P46最后一次实读为准，本轮没有重新探测当前通电或连接情况。P46历史0xFF、质量波动根因、更多冷启动/长稳、时序、真实独立AI数据集仍开放。本轮完成的是学习/演示工具，不增加真实独立样本或AI准确率。

下次先读`{resume}`。队员可立即读取数据、练习分析并使用离线演示；推进AI前先设计不同源种子和独立真实采集会话，再做按会话划分的训练/验证/测试。小屏单位改进属于后续板端任务，本轮没有部署。
''',encoding='utf-8')
    (ROOT/resume).write_text(f'''# P47恢复入口（2026-10-22）

本轮已完成真实数据学习包和离线回放，仅操作电脑，未接触板卡。

1. 当前电脑双击根目录`{rel(launcher)}`；或包内run-demo.cmd。信号/采集块切换后点开始，播放结束用重新播放；导出写包内exports/。
2. 分享队员ZIP `{rel(Path(build['archive']['path']))}`。先完整解压；README.md是中文说明，example_read.py提供最小读取例子。另一台电脑第一次需Python和依赖，安装后可完全离线使用。不要只复制cmd或在ZIP内部双击。
3. 首次读取先跑load_kit校验manifest、原始码值和NPZ。数组保留4块边界；不要flatten后声称连续采样，也不要把同一个循环源窗口随机分成训练/测试。
4. 主证据 `{rel(args.build)}`，图形窗口测试 `{rel(args.gui)}`，最终测试 `{rel(args.tests)}`；交付回执 `{rel(out/'report.json')}`。results不在Git，直接读文件系统。
5. 如需继续板端工作，先读[硬件恢复清单](RESUME-P46-20261022.md)和p46_current，只读识别实际boot、进程、guard及DMA状态，不假设本轮重新验证了连线/通电，不重放旧boot或热卸驱动/装PL。
6. 下一步主线是独立真实RF数据与AI；小屏单位改进可以另做短任务。当前包标签来自已知发送，不是已完成AI推理。
''',encoding='utf-8')
    root=read(ROOT/'TX-SOURCE-STATUS.json')
    root.update(status=current['status'],authoritative_current_field='p47_current',updated=now.isoformat(),record=record,
        updated_note='P47 host-only portable RF learning kit and offline replay delivered; hardware state remains the P46 last verified baseline',
        status_note='软件交付看p47_current；板卡最后实读看p46_current。本轮未重查硬件，不新增AI/采集验收。',p47_current=current)
    write(ROOT/'TX-SOURCE-STATUS.json',root);write(ROOT/'results/p47-active.json',current)
    start=ROOT/'START-HERE.md';history=ROOT/now.strftime('START-HERE-BEFORE-P47-%Y%m%dT%H%M%SZ.md');history.write_bytes(start.read_bytes())
    start.write_text(f'''# 从这里恢复项目工作

**当前软件入口：P47（2026-10-22）真实数据包与一键离线回放已交付。** 先读[实验记录]({record})、[恢复清单]({resume})和TX-SOURCE-STATUS.json的p47_current。当前电脑双击`{rel(launcher)}`；队员分享包`{rel(Path(build['archive']['path']))}`，先解压再按中文README运行。

包含单音/BPSK/QPSK/16QAM共16个原始DMA块、4MiB原始打包IQ及逐点一致的NPZ、参数/标签/索引/校验/读取示例。离线界面可选信号/采集块，播放波形、频谱、瀑布图并导出。8项控制器/完整性检查、全部DMA有限回放、异地解压运行、实际Tk计时播放/暂停/保存通过。没有运行AI，数据仅用于学习/调试，不能冒充独立训练/测试集。

**硬件最后实读仍以P46为准，本轮没有连接或重查板卡。** 继续硬件前先读[P46恢复清单](docs/handoff/RESUME-P46-20261022.md)和p46_current，重新识别实际boot、wrapper/进程/DMA。不照搬上次通电状态，不热卸驱动或绑定中装PL。

P46真实已知源质量/单音写屏及P45受控冷启动实体显示结论保留；AI、更多独立会话/长稳及历史异常根因仍开放。小屏单位改进本轮未部署。results被gitignore排除，须直接读文件系统。

上一入口原文：[历史快照]({rel(history)})。当前交付回执：`{rel(out/'report.json')}`。
''',encoding='utf-8')
    inputs={str(p.relative_to(ROOT)):sha(p) for p in (ROOT/'host/rf_learning_kit').iterdir() if p.is_file()}
    inputs.update({str(Path(__file__).resolve().relative_to(ROOT)):sha(Path(__file__)),
        'experiments/p47_build_learning_kit.py':sha(ROOT/'experiments/p47_build_learning_kit.py'),
        'tests/test_rf_learning_kit.py':sha(ROOT/'tests/test_rf_learning_kit.py')})
    write(out/'report.json',dict(status='passed_P47_portable_RF_learning_delivery_saved',current=current,source_files_sha256=inputs,
        launcher_sha256=sha(launcher),documents_sha256={name:sha(ROOT/name) for name in (record,resume,'START-HERE.md')},
        board_operations=False,raw_P46_inputs_unchanged=True))
    print(out);print('passed_P47_portable_RF_learning_delivery_saved')


if __name__=='__main__':main()
