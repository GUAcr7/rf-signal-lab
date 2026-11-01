"""Seal an offline-only UART branch and preserve failures; never deploy."""
import argparse,hashlib,json,zipfile
from datetime import datetime,timezone
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def read(p):return json.loads(p.read_text('utf-8'))
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
def main():
    p=argparse.ArgumentParser()
    for name in ('candidate','validation','route','tool','review'):p.add_argument('--'+name,type=Path,required=True)
    args=p.parse_args();reports={k:v.resolve() for k,v in vars(args).items()};values={k:read(v) for k,v in reports.items()}
    if any(v['board_operations'] for v in values.values()):raise ValueError('offline-only evidence required')
    route=values['route'];tool=values['tool']
    review=values['review']
    if review['route_sha256']!=sha(args.route) or review['deployable'] or not review['routed_UART_pads_checked']:raise ValueError('honest route audit required')
    if not route['status'].startswith(('completed_','failed_')):raise ValueError('build still active')
    if tool['status']!='passed_seven_PTY_two_production_refusals_and_ARM_build_not_board_test':raise ValueError('tool incomplete')
    for k in ('candidate','validation','route'):
        value=values[k]
        for f,digest in value.get('files_sha256',value.get('saved_files_sha256',{})).items():
            if sha(reports[k].parent/f)!=digest:raise ValueError('archived evidence changed '+f)
    manifest=read(ROOT/'fpga/vendor-baseline/source-manifest.json')
    pristine=[]
    for row in manifest['files']:
        f=ROOT/'fpga/vendor-baseline'/row['relative_path']
        if sha(f)!=row['sha256']:raise ValueError('vendor original changed')
        pristine.append(f)
    if not all(sha(ROOT/f)==digest for f,digest in tool['inputs_sha256'].items()):raise ValueError('UART tool input changed')
    binary=ROOT/tool['binary']
    if sha(binary)!=tool['binary_sha256']:raise ValueError('ARM binary changed')
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p201-uart-checkpoint-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    stats=route.get('run_stats',{})
    current=dict(status='offline_UART_candidate_saved_not_deployed',updated_utc=now.isoformat(),
        reports={k:dict(path=v.relative_to(ROOT).as_posix(),sha256=sha(v)) for k,v in reports.items()},
        full_build_status=route['status'],run_stats=stats,deployable=False,route_review=review,
        board_operations=False,physical_UART_tested=False,screen_compatibility_confirmed=False,
        main_hardware_checkpoint='P51',main_hardware_state_rechecked=False,
        candidate_TX=dict(header='J19',pin=5,package_pin='E17',IOSTANDARD='LVCMOS33'),
        candidate_RX=dict(header='J19',pin=6,package_pin='E18',IOSTANDARD='LVCMOS33'),
        tests=dict(candidate_guards=10,Linux_PTY=7,production_refusals=2),
        original_vendor_files_verified=len(pristine),checkpoint=(out/'report.json').relative_to(ROOT).as_posix(),
        next_tasks=['Review full timing/CDC/IO evidence and inherited baseline issues',
            'Compare current boot/kernel UART clock/reset init; decide whether FSBL rebuild is actually needed',
            'Prepare recoverable startup candidate; verify console/controller identity without external peripheral',
            'Verify physical board revision, pin orientation and voltage before TX/RX loopback',
            'Verify external peripheral model/logic voltage/GND and protocol before connection'])
    record=ROOT/'docs/experiments/EXP-P201-UART-CANDIDATE-20261024.md'
    with record.open('a',encoding='utf-8') as f:
        f.write('\n## 本轮结束状态\n\n完整构建状态：`'+route['status']+'`；主报告：`'+reports['route'].relative_to(ROOT).as_posix()+'`。时序运行统计：`'+json.dumps(stats,ensure_ascii=False)+'`。完成布线不等于全部时序/CDC和接口验收通过；本轮不批准部署，不生成/写入新的启动镜像。10项候选输入保护、7项PTY、2项正式程序拒绝测试通过，ARM工具已构建。原厂'+str(len(pristine))+'个输入最终SHA核对未变。\n\n串口分支检查点：`'+current['checkpoint']+'`，ZIP逐文件SHA/CRC核验。主线P51硬件验收和比赛任务顺序不替换，本轮没有读取或改变板卡当前状态。继续先读本记录、`results/p201-uart-active.json`及完整报告，不把“候选已实现”解释成“针脚现在能用”。\n')
    write(ROOT/'results/p201-uart-active.json',current)
    files=set(pristine)
    for folder in ('embedded/p201_uart','tests/native','src/rfsig'):
        for f in (ROOT/folder).glob('*'):
            if f.is_file() and (folder=='embedded/p201_uart' or 'p201' in f.name):files.add(f)
    for f in (ROOT/'experiments').glob('p201_*.py'):files.add(f)
    files.update([ROOT/'tests/test_p201_uart_candidate.py',ROOT/'results/p201-uart-final-guards-20261024.xml',record,ROOT/'START-HERE.md',ROOT/'results/p201-uart-active.json',ROOT/'docs/experiments/EXP-P201-UART-20261024.md'])
    for path in reports.values():files.update(f for f in path.parent.rglob('*') if f.is_file())
    files.update(f for f in (ROOT/'results/p201-uart-docs-20261023T162127Z').rglob('*') if f.is_file())
    rows=[dict(path=f.relative_to(ROOT).as_posix(),bytes=f.stat().st_size,sha256=sha(f)) for f in sorted(files)]
    write(out/'manifest.json',rows)
    archive=out/'checkpoint.zip'
    with zipfile.ZipFile(archive,'x',compression=zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in rows:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','CHECKPOINT-MANIFEST.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip():raise ValueError('ZIP CRC failure')
        for row in rows:
            b=z.read(row['path'])
            if len(b)!=row['bytes'] or hashlib.sha256(b).hexdigest()!=row['sha256']:raise ValueError('ZIP member differs')
    write(out/'report.json',dict(status='passed_offline_UART_branch_checkpoint_CRC_and_SHA',files=len(rows),all_member_SHA_verified=True,
        board_operations=False,deployable=False,archive=dict(path=archive.relative_to(ROOT).as_posix(),bytes=archive.stat().st_size,sha256=sha(archive)),current=current))
    print(out/'report.json');print(current['status'])
if __name__=='__main__':main()
