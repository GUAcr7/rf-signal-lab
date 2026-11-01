from pathlib import Path
import hashlib,json,re,xml.etree.ElementTree as ET
out=Path(__file__).resolve().parent
root=out.parents[1]
oldwork=Path('E:/p32-pwm2-105934'); newwork=Path('E:/p33-ttl-114312')
bdrel='project/combined.srcs/sources_1/bd/system/system.bd'
old=json.loads((oldwork/bdrel).read_text())['design']; new=json.loads((newwork/bdrel).read_text())['design']
removedcells={'dual_pixel_24bpp_lvds_mapping_0','lvds_n_x_7to1_sdr_tx_0'}
removedports={'lvds_clk_out_n','lvds_clk_out_p','lvds_data_out_n','lvds_data_out_p','o_video_data','o_video_de','o_video_hsync','o_video_pclk','o_video_vsync'}
checks=[]
def ck(name,value):checks.append(dict(name=name,passed=bool(value)))
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
ck('only_two_unused_BD_cells_removed',set(old['components'])-set(new['components'])==removedcells and not set(new['components'])-set(old['components']))
ck('only_nine_unused_BD_ports_removed',set(old['ports'])-set(new['ports'])==removedports and not set(new['ports'])-set(old['ports']))
for key in new['components']:
    if key!='clk_wiz_0':ck('component_unchanged:'+key,old['components'][key]==new['components'][key])
for key in ['addressing','interface_nets']:ck(key+'_unchanged',old.get(key)==new.get(key))
ck('single_PS7',sum(c.get('vlnv','').startswith('xilinx.com:ip:processing_system7:') for c in new['components'].values())==1)
# Independently compare each surviving net endpoint set, regardless of net renaming.
def surviving(design):
    nets=[]
    for net in design['nets'].values():
        pins=sorted(p for p in net['ports'] if p not in removedports and p.split('/')[0] not in removedcells)
        if len(pins)>1:nets.append(tuple(pins))
    return sorted(nets)
ck('surviving_scalar_connectivity_identical',surviving(old)==surviving(new))
params={k:v['value'] for k,v in new['components']['clk_wiz_0']['parameters'].items()}
prev={k:v['value'] for k,v in old['components']['clk_wiz_0']['parameters'].items()}
delta={k:dict(before=prev.get(k),after=v) for k,v in params.items() if prev.get(k)!=v}
(out/'clock-parameter-delta.json').write_text(json.dumps(delta,indent=2)+'\n')
inputmhz=float(params['PRIM_IN_FREQ']); mult=float(params['MMCM_CLKFBOUT_MULT_F']); div=float(params['MMCM_DIVCLK_DIVIDE']); outdiv=float(params['MMCM_CLKOUT0_DIVIDE_F'])
vco=inputmhz*mult/div; actual=vco/outdiv
ck('computed_exact33MHz',abs(actual-33)<1e-9)
for k,v in {'PRIM_IN_FREQ':'100.000','PRIM_SOURCE':'No_buffer','USE_DYN_RECONFIG':'true','NUM_OUT_CLKS':'1','CLKOUT2_USED':'false'}.items():ck('ClockWiz:'+k,params[k]==v)
ck('pixel_metadata33MHz',int(new['ports']['lcd_pclk']['parameters']['FREQ_HZ']['value'])==33000000)
ck('retained_PWM2',set(new['nets']['display_backlight_ttc0_ch2']['ports'])=={'sys_ps7/TTC0_WAVE2_OUT','lcd_pwm_backlight'})
ck('RF_constraints_exact',sha(oldwork/'constraints/rf.xdc')==sha(newwork/'constraints/rf.xdc'))
oldxdc=(oldwork/'constraints/display.xdc').read_text(); newxdc=(newwork/'constraints/display.xdc').read_text()
ck('display_constraints_only_remove_unused_lines',newxdc.splitlines()==[s for s in oldxdc.splitlines() if 'lvds_' not in s and 'o_video' not in s])
top=(newwork/'hdl/rf_display_top.v').read_text(); decl=top[top.index('module rf_display_top'):top.index(');',top.index('module rf_display_top'))]
topports=set(re.findall(r'\b(?:input|output|inout)\s+(?:wire\s+)?(?:\[[^\]]+\]\s+)?(\w+)',decl))
ck('removed_ports_absent_from_top',all(p not in topports for p in removedports))
sysinst=top[top.index('system i_system_wrapper'):]; sysinst=sysinst[:sysinst.index(');')]
bound=set(re.findall(r'\.([a-zA-Z_][a-zA-Z0-9_]*)\s*\(',sysinst))
flattened_PS={'ddr_addr','ddr_ba','ddr_cas_n','ddr_ck_n','ddr_ck_p','ddr_cke','ddr_cs_n','ddr_dm','ddr_dq','ddr_dqs_n','ddr_dqs_p','ddr_odt','ddr_ras_n','ddr_reset_n','ddr_we_n','fixed_io_ddr_vrn','fixed_io_ddr_vrp','fixed_io_mio','fixed_io_ps_clk','fixed_io_ps_porb','fixed_io_ps_srstb'}
ck('system_instance_ports_match_BD',bound==set(new['ports'])|flattened_PS)
refs=[]
for name in ['display.xdc','rf.xdc']:
    text=(newwork/'constraints'/name).read_text()
    for token in re.findall(r'\[get_ports\s+(\{[^}]+\}|[^\]\s]+)\s*\]',text):
        namebase=re.sub(r'\[\d+\]','',token.strip('{}'))
        refs.append(dict(token=token,base=namebase))
        ck('XDC_top_port:'+token,namebase in topports)
(out/'xdc-port-map.json').write_text(json.dumps(refs,indent=2)+'\n')
xpr=ET.parse(newwork/'project/combined.xpr').getroot()
constr=[e.attrib['Path'] for e in xpr.findall("./FileSets/FileSet[@Name='constrs_1']/File")]
ck('only_display_and_RF_XDC',set(Path(s).name for s in constr)=={'display.xdc','rf.xdc'})
ns={'s':'http://www.spiritconsortium.org/XMLSchema/SPIRIT/1685-2009'}
xci=ET.parse(newwork/'project/combined.srcs/sources_1/bd/system/ip/system_clk_wiz_0_0/system_clk_wiz_0_0.xci').getroot()
xmap={e.attrib.get('{'+ns['s']+'}referenceId'):e.text for e in xci.iter() if e.tag.endswith('configurableElementValue')}
for k in ['MMCM_CLKFBOUT_MULT_F','MMCM_DIVCLK_DIVIDE','MMCM_CLKOUT0_DIVIDE_F','CLKOUT1_REQUESTED_OUT_FREQ','PRIM_IN_FREQ','PRIM_SOURCE','USE_DYN_RECONFIG']:
    ck('XCI_matches_BD:'+k,xmap['PARAM_VALUE.'+k]==params[k])
prep=json.loads((root/'results/p33-ttl-project-20261020T114312Z/report.json').read_text())
for p,h in prep['source_hashes_before'].items():ck('P32_source_unchanged:'+p,sha(p)==h)
for p,h in prep['candidate_hashes'].items():ck('candidate_manifest_matches:'+p,sha(newwork/p)==h)
report=dict(status='source_review_ready_for_fresh_generation_and_synthesis',scope='independent static source/XML/BD review; no synth/route/board/UI',candidate=str(newwork/'project/combined.xpr'),actual_MMCM=dict(input_mhz=inputmhz,mult=mult,divclk=div,out_divide=outdiv,vco_mhz=vco,pixel_mhz=actual),removedcells=sorted(removedcells),removedports=sorted(removedports),clock_delta=delta,checks=checks,passed=sum(c['passed'] for c in checks),failed=sum(not c['passed'] for c in checks),hardware_operations=False,project_saved=False,limitations=['No elaborated/synthesized resource or timing proof','Fresh generated BD/IP outputs required before synthesis','Existing external timing/CDC gaps remain','FractionalM49.5 runtime driver implementation must be verified before board display trial'])
if report['failed']:report['status']='review_failed'
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
print(json.dumps(dict(status=report['status'],passed=report['passed'],failed=report['failed'],actual_MMCM=report['actual_MMCM']),indent=2))
if report['failed']:
 print(json.dumps([c for c in checks if not c['passed']],indent=2));raise SystemExit(1)

