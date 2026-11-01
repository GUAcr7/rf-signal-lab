"""Publish only completed integration evidence; preserve all prior entry points."""
from datetime import datetime,timezone
import hashlib
import json
import math
from pathlib import Path
import re
import shutil

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def latest(prefix,expected):
    paths=sorted((ROOT/'results').glob(prefix+'*/report.json'))
    if not paths:raise RuntimeError('missing evidence '+prefix)
    path=paths[-1];report=json.loads(path.read_text('utf-8'))
    if report['status']!=expected:raise RuntimeError('latest stage not accepted: '+str(path)+' '+report['status'])
    return path,report


def timing(path):
    text=path.read_text('utf-8')
    match=re.search(r'WNS\(ns\).*?\n\s*-+[^\n]*\n\s*((?:[-.0-9]+\s+){11}[-.0-9]+)',text,re.S)
    if not match:raise RuntimeError('timing summary not parsed')
    values=match[1].split()
    result=dict(wns_ns=float(values[0]),tns_ns=float(values[1]),setup_failing_endpoints=int(values[2]),
        setup_total_endpoints=int(values[3]),whs_ns=float(values[4]),ths_ns=float(values[5]),
        hold_failing_endpoints=int(values[6]),hold_total_endpoints=int(values[7]),wpws_ns=float(values[8]),
        tpws_ns=float(values[9]),pulse_width_failing_endpoints=int(values[10]),pulse_width_total_endpoints=int(values[11]))
    if not all(math.isfinite(v) for v in result.values()):raise RuntimeError('non-finite timing metric')
    if any(result[k]<0 for k in ['wns_ns','whs_ns','wpws_ns']):raise RuntimeError('constrained timing slack violated')
    if any(result[k]!=0 for k in ['tns_ns','ths_ns','tpws_ns','setup_failing_endpoints','hold_failing_endpoints','pulse_width_failing_endpoints']):
        raise RuntimeError('constrained timing failed')
    if 'All user specified timing constraints are met.' not in text:raise RuntimeError('timing acceptance marker absent')
    return result


def bus_skew(path):
    text=path.read_text('utf-8')
    summary=text.split('\n1. Bus Skew Report Summary\n--------------------------\n',1)[1]
    summary=summary.split('\n2. Bus Skew Report Per Constraint\n',1)[0]
    rows=re.findall(r'^\s*(Slow|Fast)\s+([-.0-9]+)\s+([-.0-9]+)\s+([-.0-9]+)\s*$',summary,re.M)
    if not rows:raise RuntimeError('bus skew summary absent')
    slacks=[float(row[3]) for row in rows]
    if not all(math.isfinite(v) and v>=0 for v in slacks):raise RuntimeError('bus skew requirement failed')
    return dict(reported_constraints=len(rows),worst_slack_ns=min(slacks),failing_constraints=0)


def main():
    active=json.loads((ROOT/'results/p30-active-build.json').read_text('utf-8'));work=Path(active['work'])
    synth_path,synth=latest('p30-synth-','passed')
    route_path,route=latest('p30-implement-','passed')
    if route['created_utc']<=synth['ended_utc']:raise RuntimeError('route predates final synthesis')
    graph_path,graph=latest('p30-graph-verification-','passed')
    vtc_path,vtc=latest('p30-vtc-test-','passed')
    if sha(Path(vtc['source']))!=vtc['source_sha256']:raise RuntimeError('VTC model changed after simulation')
    gpio_path,gpio=latest('p30-gpio-test-','passed')
    tx_path,tx=latest('p30-tx-file-verification-','RAM_files_eight_checksums_nine_waveforms_and_inspect_verified')
    raw_path,raw=latest('p30-smoke-archive-','fresh_sparse_bytes_boot_identity_and_release_verified')
    sources_path,sources=latest('p29-source-verification-','passed')
    route_text=(route_path.parent/'merged-route-methodology.rpt').read_text('utf-8')
    if re.search(r'TIMING-(4|27)\s*\|?\s*Critical Warning',route_text):raise RuntimeError('primary clock methodology fault remains')
    metrics=timing(route_path.parent/'merged-route-timing.rpt')
    skew=bus_skew(route_path.parent/'merged-route-bus-skew.rpt')
    route_status=(route_path.parent/'merged-route-status.rpt').read_text('utf-8')
    nets={name:int(value) for name,value in re.findall(r'# of ([A-Za-z ]+?)\.+\s*:\s*(\d+)\s*:',route_status)}
    if nets.get('nets with routing errors')!=0 or nets.get('fully routed nets')!=nets.get('routable nets'):
        raise RuntimeError('routing incomplete or errors present')
    before=ROOT/'results'/('p30-before-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));before.mkdir(exist_ok=False)
    for name in ['START-HERE.md','README.md','TX-SOURCE-STATUS.json','docs/handoff/RESUME-20261019.md','docs/design/rf-display-integration-20261019.md']:
        file=before/name;file.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(ROOT/name,file)
    out=ROOT/'results'/('p30-delivery-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    artifacts=[]
    for name in ['merged-synth.dcp','merged-route.dcp','merged-bd.tcl','create.tcl','combined_bd.tcl','clock-source.tcl','synth.tcl','implement.tcl','audit.tcl']:
        source=work/name;target=out/name;shutil.copy2(source,target)
        artifacts.append(dict(file=name,sha256=sha(target),bytes=target.stat().st_size))
    for folder in ['hdl','constraints']:
        shutil.copytree(work/folder,out/folder)
        for file in (out/folder).rglob('*'):
            if file.is_file():artifacts.append(dict(file=file.relative_to(out).as_posix(),sha256=sha(file),bytes=file.stat().st_size))
    bd=work/'project/combined.srcs/sources_1/bd/system/system.bd';shutil.copy2(bd,out/'system.bd')
    artifacts.append(dict(file='system.bd',sha256=sha(out/'system.bd'),bytes=bd.stat().st_size))
    for source in (ROOT/'experiments').glob('p30_*.py'):
        target=out/'tools'/source.name;target.parent.mkdir(exist_ok=True);shutil.copy2(source,target)
        artifacts.append(dict(file=target.relative_to(out).as_posix(),sha256=sha(target),bytes=target.stat().st_size))
    for source in [ROOT/'fpga/tb/tb_vtc_runtime.sv',ROOT/'fpga/tb/tb_rf_display_gpio.sv']:
        shutil.copy2(source,out/source.name);artifacts.append(dict(file=source.name,sha256=sha(source),bytes=source.stat().st_size))
    cdc=(route_path.parent/'merged-route-cdc.rpt').read_text('utf-8')
    critical={rule:int(count) for rule,count in re.findall(r'^(CDC-\d+)\s+Critical\s+(\d+)\s',cdc,re.M)}
    check_text=(route_path.parent/'merged-route-check-timing.rpt').read_text('utf-8')
    check_counts={key:int(count) for key,count in re.findall(r'checking (\w+) \((\d+)\)',check_text)}
    if any(check_counts.get(key)!=0 for key in ['no_clock','unconstrained_internal_endpoints','multiple_clock','generated_clocks','loops','latch_loops']):
        raise RuntimeError('internal clock/timing coverage failed')
    evidence=dict(synthesis=str(synth_path),route=str(route_path),graph=str(graph_path),vtc=str(vtc_path),gpio=str(gpio_path),tx_restore=str(tx_path),sparse_rx=str(raw_path),vendor_sources=str(sources_path))
    report=dict(status='merged_PL_routed_offline_verified_not_released',created_utc=datetime.now(timezone.utc).isoformat(),
        work=str(work),project=active['project'],evidence=evidence,route_timing=metrics,bus_skew=skew,route_nets=nets,check_timing=check_counts,
        CDC_critical_by_rule=critical,CDC_critical_total=sum(critical.values()),bitstream_generated=False,new_design_programmed=False,
        RF_transmitted_this_round=False,FPGA_RF_display_simultaneous_hardware_verified=False,artifacts=artifacts,
        bundle_scope='Review and checkpoint archive; depends on retained P29 ADI IP/tool environment; not a portable project or deployable firmware',
        unresolved=['external IO timing','ADI CDC/reset/clock topology','dynamic display clock/VDMA/TPG/kernel integration','cold-start intermittent PRODUCT_ID','long-term lossless recording and real AI'])
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    (ROOT/'results/p30-latest-delivery.json').write_text(json.dumps(dict(report=str(out/'report.json')),indent=2)+'\n',encoding='utf-8')
    rel=lambda path:path.relative_to(ROOT).as_posix()
    links='\n'.join(f'- [{name}]({"../../"+rel(Path(path))})' for name,path in evidence.items())
    doc=f'''# EXP-HW-022：射频与显示合并候选、时钟纠错及重新上电恢复

日期：2026-10-19。承接 [HW-021](EXP-HW-021-vendor-migration-and-reconnect.md)。本轮包含下午离线构建和晚间用户重新上电后的恢复；原始文件保留各自 UTC 时间戳。

**合并工程已完成完整综合与布局布线，尚未生成/加载新位流，不代表射频和屏幕已经同时上板。** 当前仍运行原厂 RF 固件。完整无丢样、真实 AI 与整机显示验收仍未完成。

## 实际完成

| 项目 | 结果与范围 |
|---|---|
| 第三份合并工程 | 精确器件 XC7Z100FFG900-2，单一 PS7；RF、VDMA、VTC、TPG、时钟、触摸、地址与 IRQ 已连接；59 个层级单元的初始框图验证通过 |
| 完整综合 | 所有模块解析，无未解析黑盒；初次 LUT 24,471 / 8.82%，FF 41,086 / 7.41%。最终资源以最终报告为准 |
| 保存后的图结构核对 | {len(graph['checks'])} 项通过，包含 EMIO64、UART1 MIO12/13、SPI0/1、HP0/1/2、跨域互连、7 个外设窗口与中断位；不是板上总线事务测试 |
| GPIO 原生仿真 | 352 次映射检查通过，覆盖逐位、方向、RF 输出、触摸及随机输入 |
| VTC 6.2 原生模型仿真 | 实际加密 IP 模型、AXI 读写与读回；800×480 两个完整帧，每帧384000像素、480行、每行800有效像素，1535次行周期检查通过 |
| 最终布线时序 | WNS {metrics['wns_ns']:+.3f} ns、WHS {metrics['whs_ns']:+.3f} ns；TNS {metrics['tns_ns']:.3f}、THS {metrics['ths_ns']:.3f}。仅覆盖已有约束 |
| 总线偏斜与布线 | {skew['reported_constraints']}项bus-skew约束均通过，最小余量{skew['worst_slack_ns']:.3f}ns；{nets['fully routed nets']}条需布线网络全部完成，routing errors=0 |
| 时钟/内部覆盖 | no_clock={check_counts.get('no_clock')}，unconstrained_internal_endpoints={check_counts.get('unconstrained_internal_endpoints')} |
| 原厂源保护 | 原始资料与 1235 项源检查通过，11 项约束引用无异常；D盘资料未改 |
| 重新上电 RX | 新 boot_id=`b638a03f-2638-4288-b663-9b8c86e58c7e`，本次 attempt 1 成功；按已验证配置恢复 RX1 manual/0dB、LO2450MHz，Fs30.72MS/s、BW18MHz |
| 新 RX 自检与回收 | 16 DMA缓冲，0.034245817秒，2通道；只保留1.5625%稀疏数据，65536字节，板端/电脑SHA一致；缓冲释放。不是完整数据或已知信号/AI验收 |
| 旧板恢复 | boot_id=`{tx['boot_id']}`；RAM包8项校验、9份波形文件检查、只读inspect通过，无发射、无RF配置写入 |

VTC 仿真采用加速像素时钟，配置完成/跨域稳定后门控闲置 AXI 时钟。它不能替代33MHz像素时钟、真实面板、TPG、VDMA、触摸或整条视频链测试。原厂480p配置为800×480、HTOTAL1056、VTOTAL528、像素时钟标值33000kHz；60为标称刷新标签，按33MHz与总像素计算约59.19Hz，未实测。

## 纠错与保留的失败证据

1. **导出的重建脚本缺少AXIS自动推导参数。** 按已综合基线XCI恢复两份转换器各14项接口属性，保留TKEEP/TLAST/TUSER等信号；没有用全零或删除接口绕过。第一次失败保留在`p30-create-20261019T093658Z`。
2. **ADI接口库误推导显示数据为FIFO总线。** 仅在副本的两个模块数据端口补充`X_INTERFACE_IGNORE`。去掉标注后与原厂逻辑文本一致，版权保留。依据[AMD UG994](https://docs.amd.com/r/en-US/ug994-vivado-ip-subsystems/Inferring-Control-Signals-in-a-RTL-Module)。本轮一次GUI解释器创建错误、一次已存在连接重复错误及一次内部Tcl读取错误分别留档；最终重建/审计通过，不掩盖失败。
3. **旧XDC含不支持的if/unset。** 最初出现Designutils 20-1307，条件检查不能当有效门禁。改为纯声明约束，把唯一层级、唯一主时钟和严格/2关系检查移至实际构建Tcl，完整重综合通过。旧XDC/DCP保存在`results/p30-xdc-correction-20261019T100001Z/`。
4. **ClockWiz把PS内部时钟当成外部输入，重新定义主时钟。** 首次布线虽WNS+0.480/WHS+0.013，却有TIMING-4/TIMING-27，不能通过发布。改`PRIM_SOURCE=No_buffer`，保持频率和MMCM比例，重新生成/综合/布线；最终报告不再含这两项严重告警。初次DCP/BD/报告在`results/p30-clock-source-preparation-20261019T133005Z/`。
5. **未使用外部TDD输入原来悬空。** 合并顶层接零，不冒充外部TDD同步实现；该相关CDC关键路径消失。当前FDD用途可继续，未来外部TDD需重做同步与测试。
6. **VTC测试编写中的启动/寄存器错误。** 首次宏传参未展开、缺glbl、寄存器偏移写错均在仿真中暴露。按留存的[Xilinx 2021.1驱动](https://raw.githubusercontent.com/Xilinx/embeddedsw/xlnx_rel_v2021.1/XilinxProcessorIPLib/drivers/vtc/src/xvtc_hw.h)核对后修正。1080p长仿真曾限时/主动停止，未写成通过；最后按实际800×480目标验收。
7. **旧板恢复兼容性。** P21 SHA256SUMS仍有CRLF，先拒绝，再仅在新恢复包生成LF清单并与P21记录哈希核对，原文件未改。上传字节校验通过，但BusyBox tar不支持-z；保留失败报告，复用已上传文件，用gzip解压、核对解压字节SHA，再用普通tar继续，未重复上传或修改固件。

## 还不能宣称完成的内容

- 外部时延仍缺：{check_counts.get('no_input_delay')}个输入、{check_counts.get('no_output_delay')}个输出。布线通过只覆盖已约束路径。未用零时延、放宽周期或新增false path作修复。
- 最终CDC仍有{sum(critical.values())}项Critical：{critical}。原59项的分类是56项DMA、2项时钟MUX、1项TDD；当前TDD项消失，其余不能凭上游代码来源免审。FIFO握手/复位、BUFR→BUFGCTRL拓扑和DRC异步RAM控制仍需审查，DRC规则可能截断显示数量。
- 候选PS配置仍不是当前完整FSBL初始化的证明。原理图第10页及内核pinmux均确认调试UART为MIO12/13，第9页风扇为MIO8；运行时IO-standard与预编译PS-init还存在差异，不盲写寄存器修复。
- 本次冷启动成功与上午三次0xFF失败都保留；间歇启动根因未解决，不再称每次必失败，也不因一次成功称已修复。
- 真实VTC运行时覆写已在仿真验证，但实际ClockWiz动态配置、TPG/VDMA/DRM及目标TTL屏幕还未合并上板。LVDS/HDMI模式不能借TTL结果验收。
- 未新增已知源发射、长期无丢样、真实AI准确率或绝对频率/功率标定。864项Python回归是前轮结果；本轮以工具实际构建、RTL仿真、87项结构检查和板端恢复为验证。

## 恢复与下一步

1. 当前工程`{active['project']}`；构建/重建说明见[合并说明](../../fpga/integration/README.md)。最终DCP是检查存档，不能直接当作可部署固件。
2. 新板当前rf，屏幕黑屏符合原厂互斥模式。旧板临时目录`{tx['remote_directory']}`；native工具在`stage/arm/arm-tx-source`，后续限时发射只选`bundle/`三份峰值256波形。`stage/waveforms`六份只是兼容检查，并非重新批准其发射功率。
3. 优先完成剩余CDC/复位、外部IO时延及实际内核/设备树契约，再设计可回滚的临时加载；不覆盖BOOT.BIN/FSBL或原厂固件。
4. 上板分开验收：目标800×480显示→已知源RF→二者并行→ARM指标显示。长期采集/AI独立验收。

## 原始证据

{links}
- [最终交付清单](../../{rel(out/'report.json')})
- [重新上电日志](../../results/p30-reconnect-20261019T132135Z/report.json)
- [载板原理图提取与页图](../../results/p30-schematic-20261019T093956Z/report.json)
- [原厂800×480配置](../../results/p30-display-profile-20261019T100223Z/report.json)
- [VTC主参考留存](../../results/p30-primary-reference-20261019T095413Z/report.json)

`results/`被gitignore排除，保存项目时需连同此目录及E盘工作副本备份。没有删除或改写原始采样；停止前正常结束实验并sync/关机，旧板RAM临时文件下次仍需恢复。
'''
    record=ROOT/'docs/experiments/EXP-HW-022-rf-display-integration.md';record.write_text(doc,encoding='utf-8',newline='\n')
    entry=f'''# 从这里恢复项目工作

最新进度：2026-10-19，先读 [HW-022](docs/experiments/EXP-HW-022-rf-display-integration.md) 与[恢复清单](docs/handoff/RESUME-20261019.md)。

- RF与显示已经合并为第三份工程，完整综合/布线通过；No_buffer与纯XDC两次时钟纠错已验证，最终WNS{metrics['wns_ns']:+.3f}ns、WHS{metrics['whs_ns']:+.3f}ns。尚未生成/加载新位流，板上仍是原厂RF模式。
- {len(graph['checks'])}项结构核对、352次GPIO仿真、实际VTC 800×480两帧仿真通过；原厂源检查1235项通过。外部IO时延、{sum(critical.values())}项CDC Critical、复位/设备树和实际显示仍待验收。
- 晚间重新上电后，新板本次attempt1成功；RX配置已恢复，16缓冲只接收自检与稀疏字节回传通过。旧板RAM工具恢复、8项包/9份波形检查通过；本轮未发射。
- 冷启动间歇0xFF仍未定位；长期无丢样、真实AI、RF/显示同时上板及整机指标未完成。
- 不重跑旧P26/P27/P29总结覆盖本入口。results被gitignore排除，需直接保存文件系统。

历史入口已原样备份在 `{rel(before)}/START-HERE.md`，按需追溯，不用历史状态覆盖当前结论。
'''
    (ROOT/'START-HERE.md').write_text(entry,encoding='utf-8',newline='\n')
    status_path=ROOT/'TX-SOURCE-STATUS.json';status=json.loads(status_path.read_text('utf-8'))
    status.update(updated=report['created_utc'],updated_note='HW-022: merged PL synthesis/route and bounded simulations verified; not deployed',
        status=report['status'],record=rel(record),historical_field_note='Fields outside p30_integration retain historical scope; current boot identities and RAM paths are in p30_integration. No new RF transmission in HW-022.')
    status['p30_integration']=dict(delivery=rel(out/'report.json'),evidence={k:rel(Path(v)) for k,v in evidence.items()},
        route_timing=metrics,bus_skew=skew,route_nets=nets,external_timing_missing=check_counts,CDC_critical=sum(critical.values()),
        new_design_programmed=False,RF_transmitted_this_round=False,tx_recovery_directory=tx['remote_directory'],
        tx_boot_id=tx['boot_id'],rx_boot_id=raw['expected_boot_id'])
    status_path.write_text(json.dumps(status,indent=2,ensure_ascii=False)+'\n',encoding='utf-8',newline='\n')
    resume=f'''# 恢复清单：2026-10-19（HW-022）

先读[本轮记录](../experiments/EXP-HW-022-rf-display-integration.md)，当前电脑工程在 `{active['project']}`。

1. 每次重新上电先枚举端口并认板。本次旧COM9/pzp201 boot=`{tx['boot_id']}`；新COM8/Zynq-Tronlong boot=`{raw['expected_boot_id']}`。串口一次一个拥有者。
2. 新板本次rf模式、attempt1成功。检查PHY/ADC/DDS三个名字及RX属性后继续，不把一次成功当间歇启动故障已修复；保留失败日志。
3. 当前RX1 manual/0dB、LO2450MHz、Fs30.72MS/s、BW18MHz、A_BALANCED。已存16缓冲稀疏诊断，保留率1.5625%；完整IQ/AI入口不能直接使用稀疏文件。
4. 旧板本次恢复在`{tx['remote_directory']}`，stage/arm为原生守卫，bundle/为峰值256三调制。8项包与9份波形检查通过；没有新发射。下次断电后目录丢失，先恢复并重读boot_id；不发送stage/waveforms旧幅度源。
5. FPGA当前为离线合并候选。最终布线WNS{metrics['wns_ns']:+.3f}/WHS{metrics['whs_ns']:+.3f}ns，但外部IO/CDC/复位及实际显示仍待验收；不生成或烧写新固件、不替换BOOT.BIN/FSBL来碰运气。
6. 继续顺序：CDC与实际IO契约→目标TTL显示的时钟/设备树/驱动→可回滚临时加载方案→显示、RF、并行分项验收→持续采集和真实AI。
7. 构建步骤见[合并说明](../../fpga/integration/README.md)。No_buffer与纯声明XDC已写入最新准备脚本，不重复调用历史纠错脚本。不要同时跑多个Vivado项目操作。

电脑上的源码、DCP、日志和数据均已保存。停止前先结束实验，再sync/正常关机；RAM临时程序需下次恢复。results被gitignore排除，备份需包含它及E盘工作副本。
'''
    (ROOT/'docs/handoff/RESUME-20261019.md').write_text(resume,encoding='utf-8',newline='\n')
    for name in ['README.md','docs/design/rf-display-integration-20261019.md']:
        path=ROOT/name;old=path.read_text('utf-8')
        link='docs/experiments/EXP-HW-022-rf-display-integration.md' if name=='README.md' else '../experiments/EXP-HW-022-rf-display-integration.md'
        notice=f'> 2026-10-19 HW-022更新：[射频与显示合并记录]({link}) 已完成离线完整综合/布线及GPIO/VTC有限仿真；未生成/加载新位流，外部IO时延与CDC/复位、实际屏幕并行仍待验收。下文较早的“尚未合并”等状态只作历史依据。\n\n'
        path.write_text(notice+old,encoding='utf-8',newline='\n')
    print(out);print(record)


if __name__=='__main__':main()
