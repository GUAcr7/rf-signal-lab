"""Read-only verification of P32 artifact scopes, pairing and original baseline."""
from datetime import datetime,timezone
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from p32_session import ROOT


def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()


def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p32-delivery-check-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    checks=[]
    report=dict(status='checking',checks=checks,board_operations=False)
    def check(name,ok,detail=None):
        checks.append(dict(name=name,passed=bool(ok),detail=detail))
    def read(path):return json.loads((ROOT/path).read_text('utf-8'))
    runtime=read('results/p32-dma4k-resume-20261020T105719Z/report.json')
    check('fresh boot RX4K and normal factory restore accepted',runtime['status']=='fresh_boot_DMA4K_RX_transfer_and_factory_restore_verified')
    check('no hot remove or TX application',not runtime['hot_overlay_removal'] and not runtime['TX_application_started'])
    smoke=json.loads(Path(runtime['trial_smoke']['report']).read_text('utf-8'))
    check('RX16 buffers released',smoke['native_metadata']['blocks']==16 and smoke['native_metadata']['buffer_released'])
    check('sparse scope preserved',not smoke['native_metadata']['complete_stream_saved'])
    archive=json.loads(Path(runtime['trial_archive']['report']).read_text('utf-8'))
    raw=Path(runtime['trial_archive']['report']).parent/'prefixes.bin'
    check('RX retrieved bytes hash matches',raw.stat().st_size==65536 and digest(raw)==archive['raw']['sha256'])
    check('1.5625 percent retained, not lossless stream',archive['raw']['saved_fraction']==1/64 and not archive['lossless_proven'])
    end=read('results/p32-preflight-20261020T111006Z/report.json')
    rx=end['boards']['COM8'];tx=end['boards']['COM9']
    check('factory final boot linked',runtime['factory_final_boot']==rx['boot_id'])
    check('both current boards untainted and idle',all(v['tainted']=='0' and not v['experiment_process_observed'] for v in [rx,tx]))
    check('RX guard and scan released',rx['guard_matches'] and rx['buffer_enable']=='0' and rx['scan_enable']==['0']*4)
    project=read('results/p32-pwm2-project-20261020T105934Z/report.json')
    check('P30 three key baseline files still match',all(digest(Path(p))==h for p,h in project['baseline_hashes_before'].items()))
    src=Path(project['source'])/'project/combined.srcs/sources_1/bd/system'
    dst=Path(project['working_directory'])/'project/combined.srcs/sources_1/bd/system'
    old=json.loads((src/'system.bd').read_text('utf-8'))['design']
    new=json.loads((dst/'system.bd').read_text('utf-8'))['design']
    for k in ['interface_ports','ports','interface_nets','addressing','design_tree']:
        check('unchanged '+k,old[k]==new[k])
    oldnets={k:v for k,v in old['nets'].items() if 'lcd_pwm_backlight' not in v['ports']}
    newnets={k:v for k,v in new['nets'].items() if 'lcd_pwm_backlight' not in v['ports']}
    check('all other signal nets identical',oldnets==newnets)
    check('PWM2 physical net pair saved',new['nets']['display_backlight_ttc0_ch2']['ports']==['sys_ps7/TTC0_WAVE2_OUT','lcd_pwm_backlight'])
    check('BD validation marked true',new['design_info']['validated']=='true')
    # Vivado serializes previously implicit PS7 defaults when re-saving a BD.
    # Check these against the original fully configured XCI, not omitted JSON.
    expanded=[];common_changes=[];unexplained=[]
    ns={'s':'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
    for cell,body in old['components'].items():
        after=new['components'][cell]
        for field in body.keys()|after.keys():
            if field!='parameters':
                check('component field '+cell+'/'+field,body.get(field)==after.get(field))
        before_params=body.get('parameters',{});after_params=after.get('parameters',{})
        xcipath=src/body['xci_path'].replace('\\','/') if 'xci_path' in body else None
        values={}
        if xcipath and xcipath.exists():
            tree=ET.parse(xcipath)
            for e in tree.findall('.//s:configurableElementValue',ns):
                ref=e.attrib.get('{'+ns['s']+'}referenceId','')
                if ref.startswith('PARAM_VALUE.'):values[ref[12:]]=e.text
        for key in before_params.keys()|after_params.keys():
            a,b=before_params.get(key),after_params.get(key)
            if a==b:continue
            row=dict(cell=cell,parameter=key,before=a,after=b)
            if a is None and b and b.get('value')==values.get(key):expanded.append(row)
            else:common_changes.append(row)
    check('no unexplained component parameter changes',not common_changes,common_changes)
    report['serialized_existing_XCI_defaults']=expanded
    sim=read('results/p32-fifo-mm-20261020T110537Z/report.json')
    check('FIFO/MM simulation passes',sim['status']=='passed')
    check('two cases have explicit EOT/data completion',sum('CASE_PASS' in m and 'desc=64 beats=2216 EOT=64' in m for m in sim['markers'])==2)
    for item in sim['sources']:
        check('unchanged sim source '+item['name'],digest(Path(item['path']))==item['sha256'])
    expected={
        'adc':dict(DMA_TYPE_SRC='2',DMA_TYPE_DEST='0',ASYNC_CLK_REQ_SRC='true',ASYNC_CLK_DEST_REQ='false',AXI_SLICE_DEST='false'),
        'dac':dict(DMA_TYPE_SRC='0',DMA_TYPE_DEST='2',ASYNC_CLK_REQ_SRC='false',ASYNC_CLK_DEST_REQ='true',AXI_SLICE_DEST='true')}
    for role,params in expected.items():
        name='system_axi_ad9361_'+role+'_dma_0'
        xci=src/'ip'/name/(name+'.xci');values={}
        for e in ET.parse(xci).findall('.//s:configurableElementValue',ns):
            ref=e.attrib.get('{'+ns['s']+'}referenceId','')
            if ref.startswith('MODELPARAM_VALUE.'):values[ref[17:]]=e.text
        for k,v in {**params,'DMA_DATA_WIDTH_SRC':'64','DMA_DATA_WIDTH_DEST':'64','MAX_BYTES_PER_BURST':'128','FIFO_SIZE':'4','ASYNC_CLK_SRC_DEST':'true','AXI_SLICE_SRC':'false'}.items():
            check('simulation parameter '+role+'/'+k,values.get(k)==v,values.get(k))
    paired=read('results/p32-paired-overlay-20261020T110125Z/report.json')
    check('PWM2 BD paired hash unchanged',digest(dst/'system.bd')==paired['candidate_BD_sha256'])
    check('candidate source/blob unchanged',digest(Path(paired['source']))==paired['source_sha256'] and digest(Path(paired['dtbo']))==paired['dtbo_sha256'])
    check('new overlay never claimed hardware verification',not paired['merged_hardware_verified'] and not paired['physical_backlight_and_timer_validation'])
    cdc=read('results/p32-final-cdc-20261020T105847Z/report.json')
    check('58 findings retained in final report',cdc['total_critical']==58 and not cdc['all_CDC_resolved'] and not cdc['waivers_added'])
    report['checks_count']=len(checks)
    report['status']='scoped_delivery_checks_passed' if all(c['passed'] for c in checks) else 'failed'
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    print(out);print(report['status']);print('checks',len(checks));print('expanded XCI defaults',len(expanded))
    for c in checks:
        if not c['passed']:print(c)
    return 0 if report['status']=='scoped_delivery_checks_passed' else 1


if __name__=='__main__':raise SystemExit(main())
