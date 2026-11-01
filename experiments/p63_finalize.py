"""Verify P63 evidence and freeze a recoverable increment; no board operations."""
from datetime import datetime,timezone
import hashlib,json,re,sys,xml.etree.ElementTree as ET,zipfile
from pathlib import Path
from urllib.parse import unquote
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from rfsig.board_session import require_tx_off,require_rx_control
def read(p):return json.loads(p.read_text(encoding='utf-8'))
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def rel(p):return p.resolve().relative_to(ROOT.resolve()).as_posix()
def write(p,v):p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')

def main():
    evidence={
        'logic_build':'results/p63-panel-build-20261025T053407Z/report.json',
        'wire_build':'results/p63-wire-build-20261025T053407Z/report.json',
        'logic_board':'results/p59-p63-logic-selftest-20261025T053529035086Z/report.json',
        'wire_board':'results/p59-p63-logic-selftest-20261025T053555795179Z/report.json',
        'preview':'results/p63-page-preview-20261025T044959Z/report.json',
        'final_status':'results/p59-status-20261025T053621996072Z/report.json',
        'protocol_tests':'results/p63-tjc-protocol-tests-20261025.xml'}
    data={k:read(ROOT/v) for k,v in evidence.items() if v.endswith('.json')}
    for kind in ('logic','wire'):
        build,board=data[kind+'_build'],data[kind+'_board']
        if not build['status'].startswith('passed_') or not board['status'].startswith('passed_P63_'):
            raise ValueError(kind+' incomplete')
        if sha(ROOT/board['build_report'])!=board['build_sha256']:raise ValueError('Build binding changed')
        if board['ARM_sha256']!=build['ARM_sha256'] or board['ARM_selftest']!=build['selftest']:
            raise ValueError('Board selftest does not match build')
        if sha(ROOT/build['ARM_binary'])!=build['ARM_sha256']:raise ValueError('Binary changed')
        if not all(build['checks'].values()):raise ValueError('Build ABI check failed')
        for name,wanted in build['inputs_sha256'].items():
            if sha(ROOT/name)!=wanted:raise ValueError('Input changed: '+name)
        for side in ('before_TX','after_TX'):require_tx_off(board[side])
        if board['before_TX']['boot_id']!=board['after_TX']['boot_id'] or board['before_TX']['RF']!=board['after_TX']['RF']:
            raise ValueError('Board identity/config changed')
        if not board['serial_closed'] or board['RF_transmissions'] or board['screen_UART_opened']:
            raise ValueError('Unexpected board effects')
    logic=data['logic_build'];wire=data['wire_build']
    if len(logic['contracts']['cases'])!=25 or logic['selftest']['checks']!=26 or wire['selftest']['checks']!=145:
        raise ValueError('Expected check counts changed')
    if wire['contracts']['valid_frames']!=438:raise ValueError('Wire corpus changed')
    state=data['final_status']
    if state['status']!='passed_P59_status' or not state['serial_closed']:raise ValueError('Final status incomplete')
    require_tx_off(state['boards']['TX']);require_rx_control(state['boards']['RX'],running=False)
    for kind in ('logic','wire'):
        if data[kind+'_board']['after_TX']['boot_id']!=state['boards']['TX']['boot_id']:raise ValueError('TX boot changed')
    cases=list(ET.parse(ROOT/evidence['protocol_tests']).getroot().iter('testcase'))
    if len(cases)!=17 or any(c.findall('failure') or c.findall('error') for c in cases):raise ValueError('Protocol regression incomplete')
    documents=[ROOT/'START-HERE.md',ROOT/'docs/WORKFLOW-NEXT-20261024.md',
        ROOT/'docs/design/tjc-source-screen-20261025.md',ROOT/'docs/experiments/EXP-P63-source-panel-20261025.md',
        ROOT/'docs/handoff/RESUME-P63-20261025.md',ROOT/'embedded/source_panel/README.md']
    links=0
    for doc in documents:
        for target in re.findall(r'\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
            if re.match(r'^[A-Za-z]+:',target) or target.startswith('#'):continue
            path=(doc.parent/unquote(target.split('#')[0])).resolve()
            if not path.exists():raise ValueError('Broken link: '+rel(doc)+' -> '+target)
            links+=1
    parents=[]
    for name in ('results/p59-checkpoint-20261025T030227Z/report.json',
                 'results/p61-tjc-integration-20261025T034600Z/report.json',
                 'results/p62-model-record-20261025T041700Z/report.json'):
        p=ROOT/name;r=read(p);archive=r['archive']
        if sha(ROOT/archive['path'])!=archive['sha256']:raise ValueError('Parent increment changed')
        parents.append(dict(report=name,report_sha256=sha(p),archive=archive))
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p63-final-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    summary=dict(status='passed_P63_component_and_P201_selftests_not_physical_screen_RF',
        created_utc=datetime.now(timezone.utc).isoformat(),
        evidence={k:dict(path=v,sha256=sha(ROOT/v)) for k,v in evidence.items()},
        control_scenarios=25,random_events=800,control_selftest_checks=26,
        wire_valid_corpus_frames=438,wire_selftest_checks=145,protocol_regression_tests=17,
        screen_UART_deployed=False,HMI_compiled=False,TFT_downloaded=False,RF_transmissions_this_phase=0,
        board_effects='Two known P201 RAM helpers via debug console, no persistent writes/PL/reboot',
        final_hardware=dict(TX_boot=state['boards']['TX']['boot_id'],RX_boot=state['boards']['RX']['boot_id'],
            TX_stopped=True,RX_stopped=True,serial_closed=True,powered_off=False),
        local_markdown_links_verified=links,parent_checkpoints=parents,
        next='UART deployment gates and actual interface/model match, then HMI and guarded IO adapter')
    write(out/'evidence-summary.json',summary)
    files=set(documents+[out/'evidence-summary.json'])
    for folder in (ROOT/'embedded/source_panel',):
        files.update(p for p in folder.rglob('*') if p.is_file())
    files.update(ROOT/v for v in ('configs/tjc-source-page.json','configs/tjc-source-screen.json',
        'src/rfsig/tjc_protocol.py','tests/test_tjc_protocol.py','tests/native/check_source_panel.py',
        'tests/native/check_panel_wire.py','experiments/p63_build_panel_logic.py','experiments/p63_build_panel_wire.py',
        'experiments/p63_board_logic_selftest.py','experiments/p63_render_panel_preview.py','experiments/p63_finalize.py'))
    for p in (ROOT/'results').iterdir():
        if p==out or p.name=='p63-active.json':continue
        if p.name.startswith(('p63-','p59-p63-')) or p.name in (
            'p59-status-20261025T044749620111Z','p59-status-20261025T053621996072Z'):
            files.update(p.rglob('*') if p.is_dir() else [p])
    files={p for p in files if p.is_file() and '__pycache__' not in p.parts}
    manifest=[dict(path=rel(p),bytes=p.stat().st_size,sha256=sha(p)) for p in sorted(files)]
    write(out/'manifest.json',manifest);archive=out/'p63-component-increment.zip'
    with zipfile.ZipFile(archive,'x',zipfile.ZIP_DEFLATED,compresslevel=3) as z:
        for row in manifest:z.write(ROOT/row['path'],row['path'])
        z.write(out/'manifest.json','P63-MANIFEST.json')
    with zipfile.ZipFile(archive) as z:
        if z.testzip() is not None:raise ValueError('Archive CRC failed')
        for row in manifest:
            content=z.read(row['path'])
            if len(content)!=row['bytes'] or hashlib.sha256(content).hexdigest()!=row['sha256']:
                raise ValueError('Archive member changed')
    summary.update(archive=dict(path=rel(archive),bytes=archive.stat().st_size,sha256=sha(archive),
        files=len(manifest),all_member_SHA_and_CRC_verified=True))
    write(out/'report.json',summary)
    write(ROOT/'results/p63-active.json',dict(status=summary['status'],report=rel(out/'report.json'),
        report_sha256=sha(out/'report.json'),hardware_status=evidence['final_status'],
        handoff='docs/handoff/RESUME-P63-20261025.md'))
    print(out/'report.json');print(summary['status']);print('Verified increment files:',len(manifest))

if __name__=='__main__':main()
