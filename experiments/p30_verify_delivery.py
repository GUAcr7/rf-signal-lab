"""Read-only cross-check of the saved P30 delivery against independent raw outputs."""
import ast
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
from urllib.parse import unquote

ROOT=Path(__file__).resolve().parents[1]


def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def read(path):
    return json.loads(path.read_text('utf-8'))


def main():
    out=ROOT/'results'/('p30-delivery-verification-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'))
    out.mkdir(exist_ok=False)
    report=dict(status='running',created_utc=datetime.now(timezone.utc).isoformat(),checks=[],board_operations=False,
        scope='Saved bytes, tool evidence, source correspondence and current documentation only; not hardware or CDC acceptance')
    def check(name,condition,detail=None):
        report['checks'].append(dict(check=name,passed=bool(condition),detail=detail))
    try:
        pointer=read(ROOT/'results/p30-latest-delivery.json')
        manifest_path=Path(pointer['report']);manifest=read(manifest_path);bundle=manifest_path.parent
        report['delivery']=str(manifest_path);report['delivery_sha256']=sha(manifest_path)
        active=read(ROOT/'results/p30-active-build.json');work=Path(active['work'])
        check('active work matches saved delivery',str(work)==manifest['work'])
        check('delivery scope remains offline and not released',manifest['status']=='merged_PL_routed_offline_verified_not_released')
        for item in manifest['artifacts']:
            file=bundle/item['file']
            check('archived bytes '+item['file'],file.is_file() and file.stat().st_size==item['bytes'] and sha(file)==item['sha256'])
        for name in ['merged-synth.dcp','merged-route.dcp','merged-bd.tcl']:
            check('current E work matches archive '+name,sha(work/name)==sha(bundle/name))
        for folder in ['hdl','constraints']:
            for file in (bundle/folder).rglob('*'):
                if file.is_file():
                    relative=file.relative_to(bundle)
                    check('E copy matches archive '+relative.as_posix(),sha(work/relative)==sha(file))
        evidence={name:read(Path(path)) for name,path in manifest['evidence'].items()}
        for stage in ['synthesis','route']:
            path=Path(manifest['evidence'][stage]);stage_report=evidence[stage]
            check(stage+' real tool exit',stage_report['status']=='passed' and all(c['exit_code']==0 for c in stage_report['commands']))
            check(stage+' saved script hash',sha(path.parent/('synth.tcl' if stage=='synthesis' else 'implement.tcl'))==stage_report['script_sha256'])
            for item in stage_report['artifacts']:
                check(stage+' report hash '+item['name'],sha(path.parent/item['name'])==item['sha256'])
        check('final route follows corrected synthesis',evidence['route']['created_utc']>evidence['synthesis']['ended_utc'])
        route_folder=Path(manifest['evidence']['route']).parent
        text=(route_folder/'merged-route-timing.rpt').read_text('utf-8')
        match=re.search(r'^\s*WNS\(ns\)[^\n]*\n[^\n]*\n([^\n]+)',text,re.M)
        values=match[1].split() if match else []
        check('reported WNS and WHS match raw table',len(values)==12 and float(values[0])==manifest['route_timing']['wns_ns'] and float(values[4])==manifest['route_timing']['whs_ns'])
        check('constrained timing acceptance present','All user specified timing constraints are met.' in text)
        method=(route_folder/'merged-route-methodology.rpt').read_text('utf-8')
        check('no internal-clock primary override severe rule',not re.search(r'^\| TIMING-(?:4|27)\s*\|',method,re.M))
        check('graph applies to archived BD',evidence['graph']['bd_sha256']==sha(bundle/'system.bd') and all(c['passed'] for c in evidence['graph']['checks']))
        vtc=evidence['vtc'];gpio_folder=Path(manifest['evidence']['gpio']).parent
        check('actual VTC model remains tested bytes',sha(Path(vtc['source']))==vtc['source_sha256'])
        check('VTC testbench remains tested bytes',sha(ROOT/'fpga/tb/tb_vtc_runtime.sv')==vtc['tb_sha256'])
        for file in ['tb_rf_display_gpio.sv','rf_display_gpio.v']:
            current=ROOT/('fpga/tb' if file.startswith('tb_') else 'fpga/rtl')/file
            check('GPIO test source matches '+file,sha(current)==sha(gpio_folder/file))
        check('GPIO used in candidate equals simulated module',sha(work/'hdl/rf_display_gpio.v')==sha(gpio_folder/'rf_display_gpio.v'))
        check('pure declarative divider constraint matches candidate',sha(ROOT/'fpga/constraints/display_lvds_half_clock.xdc')==sha(work/'constraints/half_clock.xdc'))
        raw_folder=Path(manifest['evidence']['sparse_rx']).parent;raw=evidence['sparse_rx']
        file=raw_folder/'prefixes.bin'
        check('saved raw IQ byte count and digest',file.stat().st_size==raw['raw']['bytes'] and sha(file)==raw['raw']['sha256'])
        check('sparse diagnostic is not labeled complete recording',raw['complete_stream_saved'] is False and raw['lossless_proven'] is False and raw['raw']['saved_fraction']==0.015625)
        check('RX record cannot be confused with TX board',raw['expected_boot_id']!=evidence['tx_restore']['boot_id'])
        status=read(ROOT/'TX-SOURCE-STATUS.json')
        check('machine status points to this delivery',status['p30_integration']['delivery']==manifest_path.relative_to(ROOT).as_posix())
        check('current boot identities agree',status['p30_integration']['tx_boot_id']==evidence['tx_restore']['boot_id'] and status['p30_integration']['rx_boot_id']==raw['expected_boot_id'])
        check('current flags do not claim deployment or RF transmission',all(manifest[k] is False for k in ['bitstream_generated','new_design_programmed','RF_transmitted_this_round','FPGA_RF_display_simultaneous_hardware_verified']))
        check('no bitstream file in candidate project',not any((work/'project').rglob('*.bit')))
        docs=['START-HERE.md','README.md','docs/handoff/RESUME-20261019.md','docs/experiments/EXP-HW-022-rf-display-integration.md',
            'docs/design/rf-display-integration-20261019.md','fpga/integration/README.md']
        report['local_links']=[]
        for name in docs:
            path=ROOT/name;text=path.read_text('utf-8')
            check('current handoff reference '+name,'HW-022' in text)
            for target in re.findall(r'!?\[[^\]\n]*\]\(([^)\n]+)\)',text):
                target=target.strip().strip('<>')
                if re.match(r'^[A-Za-z]+://|^mailto:|^#',target):continue
                target=unquote(target.split('#',1)[0])
                dest=(path.parent/target).resolve()
                report['local_links'].append(dict(document=name,target=target,exists=dest.exists()))
        check('all local Markdown links resolve',all(link['exists'] for link in report['local_links']),len(report['local_links']))
        for file in sorted((ROOT/'experiments').glob('p30_*.py')):
            ast.parse(file.read_text('utf-8'),filename=str(file))
            check('Python syntax '+file.name,True)
        report['status']='passed' if all(c['passed'] for c in report['checks']) else 'failed'
    except Exception as error:
        report.update(status='failed',error=repr(error))
    finally:
        report['ended_utc']=datetime.now(timezone.utc).isoformat()
        shutil.copy2(__file__,out/Path(__file__).name)
        report['verifier_sha256']=sha(out/Path(__file__).name)
        (out/'report.json').write_text(json.dumps(report,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
    print(out);print(report['status'],len(report['checks']))
    for item in report['checks']:
        if not item['passed']:print(item)
    if 'error' in report:print(report['error'])
    return 0 if report['status']=='passed' else 1


if __name__=='__main__':raise SystemExit(main())
