from pathlib import Path
import hashlib,json,re
root=Path.cwd().parents[1]
out=Path(__file__).parent.resolve()
sha=lambda p:hashlib.sha256(Path(p).read_bytes()).hexdigest()
base=json.loads((root/'results/p32-pwm2-project-20261020T105934Z/report.json').read_text())
baseline=[dict(path=p,expected_sha256=h,current_sha256=sha(p)) for p,h in base['baseline_hashes_after'].items()]
for item in baseline:item['unchanged']=item['expected_sha256']==item['current_sha256']
p31=json.loads((root/'results/p31-timing-sources-20261019T140648Z/report.json').read_text())
sources=[]
for name,item in p31['sources'].items():
    sources.append(dict(name=name,path=item['path'],expected_sha256=item['sha256'],current_sha256=sha(item['path'])))
for item in sources:item['unchanged']=item['expected_sha256']==item['current_sha256']
bdpath=Path('E:/p32-pwm2-105934/project/combined.srcs/sources_1/bd/system/system.bd')
bd=json.loads(bdpath.read_text())['design']
netnames=['display_clk_wiz_0_clk_out1','display_clk_wiz_0_locked','display_v_axi4s_vid_out_0_vid_active_video','display_v_axi4s_vid_out_0_vid_data','display_v_axi4s_vid_out_0_vid_hsync','display_v_axi4s_vid_out_0_vid_vsync','display_xlslice_B_Dout','display_xlslice_G_Dout','display_xlslice_R_Dout','display_backlight_ttc0_ch2']
netmap={k:bd['nets'][k] for k in netnames}
(out/'ttl-bd-net-map.json').write_text(json.dumps(dict(source=str(bdpath),sha256=sha(bdpath),nets=netmap),indent=2)+'\n')
ports=(out/'clock-port-map.txt').read_text()
rt=(out/'runtime-probe.log').read_text(errors='replace')
neg=(out/'runtime-explicit-period.log').read_text(errors='replace')
checks=[
 ('baseline_three_files_unchanged',all(i['unchanged'] for i in baseline)),
 ('primary_three_timing_pdfs_unchanged',all(i['unchanged'] for i in sources)),
 ('rx_seven_iddr_cells','i_rx_frame/i_rx_data_iddr REF IDDR' in ports and len(set(re.findall(r'^CELL (.*?) REF IDDR$',ports,re.M)))==7),
 ('tx_forwarded_output_has_no_clock','PORT tx_clk_out_p CLOCKS \n' in ports),
 ('ttl_pixel_port_tracks_main_clock','PORT lcd_pclk CLOCKS clk_out1_system_clk_wiz_0_0' in ports),
 ('runtime_propagation_rejects_aux_period','Timing 38-305' in rt and '60.606' in rt),
 ('native_explicit_period_rejected','Netlist 29-154' in neg and '0 to 52.631' in neg),
 ('ttl_clock_bypasses_aux_pll',all(p in netmap['display_clk_wiz_0_clk_out1']['ports'] for p in ['clk_wiz_0/clk_out1','lcd_pclk','v_tc_0/clk','v_axi4s_vid_out_0/vid_io_out_clk'])),
 ('ttl_lock_bypasses_aux_pll','clk_wiz_0/locked' in netmap['display_clk_wiz_0_locked']['ports']),
 ('source_archive_hash_matches_p31',json.loads((out/'driver-sources.json').read_text())['archive_sha256']=='2b11bea5872677e0c444f3c43518ada78814dd90b3fa4d31d1e2bce582bb1a70')
]
doc=root/'docs/experiments/P33-external-timing-review.md'
for label,target in re.findall(r'\[([^\]]+)\]\(([^)]+)\)',doc.read_text(encoding='utf-8')):
    if '://' not in target:checks.append(('doc_link:'+target,(doc.parent/target).resolve().exists()))
report=dict(status='offline_review_complete_external_timing_release_pending',date_local='2026-10-20',hardware_operations=False,serial_operations=False,stable_project_edits=False,entry_or_status_edits=False,baseline=baseline,primary_timing_sources=sources,clock_mapping=dict(rx_root_period_ns=4.0,baseline_pixel_period_ns=6.734,runtime_pixel_period_ns=30.303,runtime_aux_input_period_ns=60.606,runtime_aux_vco_mhz=231.0,ttl_uses_aux_pll_or_lock=False),negative_diagnostic=dict(exit_code=1,reason='Vivado native PLL property rejected60.606ns:allowed0..52.631ns',explicit_period_drc_created=False,scope='in-memory probe; not deployable XDC; not runtime STA signoff'),closure_gaps=['RF board clock/data skew bounds including core/carrier/FMC','Runtime RF portmode and tuned chip/FPGA delays','TX FB clock polarity and DDR edge mapping','Exact bare-panel sampling edge/setup/hold and FFC/translator delay','Real33MHz ClockWiz default/DRP/lock checks and runtime STA','Per-group CDC/reset closure'],practical_path='Separate TTL-only33MHz candidate removes unused auxiliary LVDS branch; preserve RF and actualTTL stream path; fullsynthesis/route and boundedfresh-boot validation; finalexternal timing release remainspending',checks=[dict(name=n,passed=v) for n,v in checks],passed_checks=sum(v for _,v in checks),failed_checks=sum(not v for _,v in checks))
files=[p for p in out.iterdir() if p.is_file() and p.name!='report.json']+[doc]
report['artifact_manifest']=[dict(path=str(p),bytes=p.stat().st_size,sha256=sha(p)) for p in files]
(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
print(json.dumps(dict(status=report['status'],passed=report['passed_checks'],failed=report['failed_checks'],baseline_unchanged=all(i['unchanged'] for i in baseline)),indent=2))
if report['failed_checks']:raise SystemExit(1)

