"""Build a third, PL-only integration candidate from the retained P29 exports.

No board access. PS initialization remains a reviewed-release gate, not a claim
that the display demo preset is the currently running FSBL configuration.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def cell_blocks(text):
    region = text.split('  # Create interface connections')[0]
    parts = re.split(r'(?=  # Create instance: )', region)
    return {re.search(r'# Create instance: ([^,]+),', s)[1]: s for s in parts[1:]}


def main():
    active = json.loads((ROOT/'results/p29-active-build.json').read_text('utf-8'))
    old = Path(active['work'])
    display = Path(active['display_short_project']).parent
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    work = Path('E:/p30c-' + datetime.now().strftime('%m%d-%H%M%S'))
    work.mkdir(exist_ok=False)
    out = ROOT/'results'/('p30-preparation-'+stamp)
    out.mkdir(exist_ok=False)
    (work/'hdl').mkdir()
    (work/'constraints').mkdir()
    inputs=[]
    def copy(src, dst):
        shutil.copy2(src, dst)
        inputs.append(dict(source=str(src), target=str(dst), sha256=digest(src)))
    rf = (old/'rf-migrated-bd.tcl').read_text('utf-8')
    ds = (old/'display-migrated-bd.tcl').read_text('utf-8')
    rblocks, dblocks = cell_blocks(rf), cell_blocks(ds)
    assert len(dblocks)==18, len(dblocks)
    for path in (display/'axi_video_display.srcs/sources_1/imports/hdl').rglob('*'):
        if path.suffix.lower() in {'.v','.vh','.vhd'}:
            dst=work/'hdl'/path.name
            if dst.exists(): raise RuntimeError('flattened HDL collision')
            copy(path, dst)
    # ADI's catalog includes FIFO interfaces whose permissive port-name rules
    # otherwise turn each bit of video data into a false inferred FIFO bus.
    # These metadata attributes suppress inference on scalar-data ports only.
    # Strip-back equality below proves the original RTL text is retained.
    annotations=[]
    for name, data_ports in {
        'dual_pixel_24bpp_lvds_mapping.v':{'vid_hsync','vid_vsync','vid_data_enable','vid_data_in','data_out'},
        'lvds_n_x_7to1_sdr_tx.v':{'data_in','clk_out_p','clk_out_n','data_out_p','data_out_n'},
    }.items():
        path=work/'hdl'/name
        original=path.read_text('utf-8')
        lines=original.splitlines(keepends=True)
        count=0
        for i,line in enumerate(lines):
            match=re.match(r'\s*(?:input|output)\s+(?:\[[^\]]+\]\s*)?(\w+)',line)
            if match and match[1] in data_ports:
                lines[i]='    (* X_INTERFACE_IGNORE = "true" *)\n'+line
                count+=1
        assert count==len(data_ports),(name,count)
        annotated=''.join(lines)
        assert annotated.replace('    (* X_INTERFACE_IGNORE = "true" *)\n','')==original
        path.write_text(annotated,encoding='utf-8',newline='\n')
        annotations.append(dict(path=str(path),metadata_only=True,stripback_equal=True,ports=sorted(data_ports),sha256=digest(path)))
    copy(old/'rf/src/hdl/ad_iobuf.v',work/'hdl/ad_iobuf.v')
    copy(ROOT/'fpga/rtl/rf_display_gpio.v',work/'hdl/rf_display_gpio.v')
    copy(old/'rf/src/constraints/ad9361_z7xh.xdc',work/'constraints/rf.xdc')
    copy(display/'axi_video_display.srcs/constrs_1/imports/constraints/axi_video_display_tlz7xh.xdc',work/'constraints/display.xdc')
    copy(ROOT/'fpga/constraints/display_lvds_half_clock.xdc',work/'constraints/half_clock.xdc')

    # Replace only PS creation/configuration; explicitly restore RF PL interfaces.
    ps = dblocks['processing_system7_0'].replace('processing_system7_0','sys_ps7')
    overrides = {
        'PCW_GPIO_EMIO_GPIO_IO':'64', 'PCW_GPIO_EMIO_GPIO_WIDTH':'64',
        'PCW_EN_SPI1':'1','PCW_EN_EMIO_SPI1':'1',
        'PCW_SPI1_PERIPHERAL_ENABLE':'1','PCW_SPI1_SPI1_IO':'EMIO',
        'PCW_SPI1_GRP_SS0_ENABLE':'1','PCW_SPI1_GRP_SS0_IO':'EMIO',
        'PCW_SPI1_GRP_SS1_ENABLE':'1','PCW_SPI1_GRP_SS1_IO':'EMIO',
        'PCW_SPI1_GRP_SS2_ENABLE':'1','PCW_SPI1_GRP_SS2_IO':'EMIO',
        'PCW_USE_S_AXI_HP1':'1','PCW_USE_S_AXI_HP2':'1',
        'PCW_IRQ_F2P_MODE':'REVERSE', 'PCW_USE_DMA0':'1',
    }
    ps += '  # Integration candidate only: no replacement FSBL is generated.\n'
    ps += '  set_property -dict [list '+ ' '.join('CONFIG.'+k+' {'+v+'}' for k,v in overrides.items())+'] $sys_ps7\n\n'
    rf=rf.replace(rblocks['sys_ps7'],ps)
    # GP0 stays at 100 MHz; free M00..M03 are asynchronous 200 MHz display slaves.
    # HP0 is moved from the RF demo's unused 100 MHz net to video's 200 MHz net.
    for i in range(4):
        rf=rf.replace(f' [get_bd_pins axi_cpu_interconnect/M0{i}_ACLK]','')
        rf=rf.replace(f' [get_bd_pins axi_cpu_interconnect/M0{i}_ARESETN]','')
    rf=rf.replace(' [get_bd_pins sys_ps7/S_AXI_HP0_ACLK]','')
    ports=ds.split('  # Create ports\n',1)[1].split('  # Create instance:',1)[0]
    ports='\n'.join(s for s in ports.splitlines() if 'touch_intr' not in s)+'\n'
    skip={'processing_system7_0','ps7_0_axi_periph','xlconcat_0'}
    # write_bd_tcl omits propagated AXIS widths, but emits remaps that refer to
    # them. Restore those exact widths from the generated baseline XCI before
    # validating customization; do not replace video sidebands with constants.
    propagated={}
    for name in ['axis_subset_converter_0','axis_subset_converter_1']:
        xci=display/f'axi_video_display.srcs/sources_1/bd/axi_video_display/ip/axi_video_display_{name}_0/axi_video_display_{name}_0.xci'
        params={}
        for elem in ET.parse(xci).iter():
            ref=next((v for k,v in elem.attrib.items() if k.endswith('referenceId')), '')
            if elem.tag.endswith('configurableElementValue') and ref.startswith('PARAM_VALUE.'):
                key=ref[len('PARAM_VALUE.'):]
                if re.fullmatch(r'[SM]_(?:HAS_T\w+|T(?:DEST|ID|USER)_WIDTH)',key):
                    params[key]=elem.text
        assert len(params)==14,(name,params)
        propagated[name]=dict(source=str(xci),sha256=digest(xci),parameters=params)
        extra=' '.join('CONFIG.'+key+' {'+value+'}' for key,value in params.items())
        dblocks[name]=dblocks[name].replace('set_property -dict [ list \\', 'set_property -dict [ list '+extra+' \\',1)
    cells=''.join(block for name,block in dblocks.items() if name not in skip)
    # PS FCLK is an internal clock, not a package clock pin. The vendor default
    # otherwise inserts a new primary clock inside ClockWiz and severs latency.
    cells+='\nset_property CONFIG.PRIM_SOURCE No_buffer [get_bd_cells clk_wiz_0]\n'
    additions=ports+cells
    def transform(line):
        if 'processing_system7_0_DDR ' in line or 'processing_system7_0_FIXED_IO ' in line or 'processing_system7_0_M_AXI_GP0 ' in line:
            return None
        if '-net GPIO_I_0_1 ' in line or '-net xlconcat_0_dout ' in line:
            return None
        line=line.replace('processing_system7_0/','sys_ps7/')
        for i in range(4):
            line=line.replace(f'ps7_0_axi_periph/M0{i}_',f'axi_cpu_interconnect/M0{i}_')
            line=line.replace(f'xlconcat_0/In{i}',f'sys_concat_intc/In{i}')
        # Drop pins of the omitted display AXI-Lite interconnect and the GP clock.
        line=re.sub(r' \[get_bd_pins ps7_0_axi_periph/[^\]]+\]','',line)
        line=line.replace(' [get_bd_pins sys_ps7/M_AXI_GP0_ACLK]','')
        if 'connect_bd_' in line:
            line=line.replace('-intf_net ','-intf_net display_').replace('-net ','-net display_')
        for previous,shared in {
            'display_processing_system7_0_FCLK_CLK0':'sys_cpu_clk',
            'display_processing_system7_0_FCLK_CLK1':'sys_200m_clk',
            'display_processing_system7_0_FCLK_RESET0_N':'sys_ps7_FCLK_RESET0_N',
        }.items():
            line=line.replace(previous+' ',shared+' ')
        # This legacy net consisted solely of the omitted interconnect reset.
        if 'rst_ps7_0_100M_interconnect_aresetn ' in line:
            return None
        return line
    sections=ds.split('  # Create interface connections\n',1)[1].split('  # Restore current instance',1)[0]
    additions+='\n# Display connections; explicitly reuse PS/AXI-Lite/IRQ resources.\n'
    additions+='\n'.join(t for line in sections.splitlines() if (t:=transform(line)) is not None)
    additions+='\n'
    # The transformed display clock/reset nets above already include M00..M03.
    additions+=r'''
set zero [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 integration_zero]
set_property CONFIG.CONST_VAL 0 $zero
set one [create_bd_cell -type ip -vlnv xilinx.com:ip:xlconstant:1.1 integration_one]
set_property CONFIG.CONST_VAL 1 $one
foreach pin {sys_ps7/SPI0_SCLK_I sys_ps7/SPI0_MOSI_I} {
    connect_bd_net [get_bd_pins integration_zero/dout] [get_bd_pins $pin]
}
connect_bd_net [get_bd_pins integration_one/dout] [get_bd_pins sys_ps7/SPI0_SS_I]
foreach i {4 5 6 7 8 9 10 11 14 15} {
    connect_bd_net [get_bd_pins integration_zero/dout] [get_bd_pins sys_concat_intc/In$i]
}
# Progressive video only. Do not leave newly introduced field inputs floating.
foreach pin {v_tc_0/fid_in v_tpg_0/fid_in v_axi4s_vid_out_0/fid} {
    set obj [get_bd_pins -quiet $pin]
    if {[llength $obj] == 1 && [get_property DIR $obj] eq "I" && ![llength [get_bd_nets -quiet -of_objects $obj]]} {
        connect_bd_net [get_bd_pins integration_zero/dout] $obj
    }
}
'''
    # Insert into the existing proc before its sole final validation.
    needle='  validate_bd_design\n  save_bd_design'
    assert rf.count(needle)==1
    rf=rf.replace(needle,additions+'\n'+needle)
    (work/'combined_bd.tcl').write_text(rf,encoding='utf-8',newline='\n')

    # Preserve the vendor top copyright, RF pin names and SPI1 input constants.
    top=(old/'rf/src/hdl/system_top_ad_fmcomms3_ebz_xc7z100.v').read_text('utf-8')
    top=top.replace('module ad_fmcomms3_ebz_xc7z100 (','module rf_display_top (')
    for declaration in ['  inout       [14:0]      gpio_bd,','  inout                   gpio_muxout_tx,','  inout                   gpio_muxout_rx,']:
        assert declaration in top
        top=top.replace(declaration,'')
    newdecl=[]; connections=[]
    for line in ports.splitlines():
        m=re.search(r'set (\w+) \[ create_bd_port -dir ([IO])(?: -from (\d+) -to (\d+))? (\w+) \]',line)
        if not m: continue
        name,direction,hi,lo,_=m.groups()
        width=f'[{hi}:{lo}] ' if hi is not None else ''
        newdecl.append(f'  {"input" if direction=="I" else "output"} wire {width}{name},')
        connections.append(f'    .{name} ({name}),')
    newdecl.append('  input wire touch_intr,')
    top=top.replace('  input                   rx_clk_in_p,','\n'.join(newdecl)+'\n  input                   rx_clk_in_p,')
    top=top.replace('  // instantiations',r'''
  wire [14:0] rf_gpio_i, rf_gpio_o, rf_gpio_t;
  wire mapped_enable, mapped_txnrx;
  rf_display_gpio i_gpio_mapping (
    .ps_o(gpio_o), .ps_t(gpio_t), .rf_i(rf_gpio_i),
    .touch_intr(touch_intr), .ps_i(gpio_i),
    .rf_o(rf_gpio_o), .rf_t(rf_gpio_t),
    .up_enable(mapped_enable), .up_txnrx(mapped_txnrx));
  // No external TDD sync connector is used by this carrier integration.
  assign tdd_sync_i = 1'b0;
  // instantiations''')
    top=top.replace('{gpio_t[46:32]}','rf_gpio_t').replace('{gpio_o[46:32]}','rf_gpio_o').replace('{gpio_i[46:32]}','rf_gpio_i')
    top=re.sub(r'  ad_iobuf #\(\.DATA_WIDTH\(1\)\) i_iobuf_tdd_sync .*?\);','',top,flags=re.S)
    top=top.replace('    .ddr_addr (ddr_addr),','\n'.join(connections)+'\n    .ddr_addr (ddr_addr),')
    top=top.replace('.up_enable (gpio_o[47])','.up_enable (mapped_enable)').replace('.up_txnrx (gpio_o[48])','.up_txnrx (mapped_txnrx)')
    (work/'hdl/rf_display_top.v').write_text(top,encoding='utf-8',newline='\n')
    (ROOT/'fpga/rtl/rf_display_top.v').write_text(top,encoding='utf-8',newline='\n')
    script=f'''set_param general.maxThreads 2
cd {{{work.as_posix()}}}
create_project combined {{{work.as_posix()}/project}} -part xc7z100ffg900-2
set_property target_language Verilog [current_project]
set_property ip_repo_paths {{{(old/'adi/library').as_posix()}}} [current_project]
update_ip_catalog
add_files [glob hdl/*.v]
add_files -fileset constrs_1 [glob constraints/*.xdc]
set_property PROCESSING_ORDER LATE [get_files */half_clock.xdc]
source combined_bd.tcl
validate_bd_design
save_bd_design
set_property top rf_display_top [current_fileset]
update_compile_order -fileset sources_1
write_bd_tcl -force merged-bd.tcl
report_ip_status -file merged-ip-status.rpt
if {{[llength [get_bd_cells -filter {{VLNV =~ *processing_system7*}}]] != 1}} {{error "expected one PS7"}}
if {{[get_property CONFIG.PCW_GPIO_EMIO_GPIO_WIDTH [get_bd_cells sys_ps7]] != 64}} {{error "EMIO mapping lost"}}
if {{[get_property CONFIG.NUM_PORTS [get_bd_cells sys_concat_intc]] != 16}} {{error "IRQ width changed"}}
puts "P30_MERGED_BD_VALIDATED cells=[llength [get_bd_cells -hier]]"
close_project
exit 0
'''
    (work/'create.tcl').write_text(script,encoding='utf-8',newline='\n')
    report=dict(status='prepared_not_validated',created_utc=datetime.now(timezone.utc).isoformat(),work=str(work),
        inputs=inputs,interface_annotations=annotations,propagated_axis_baseline=propagated,ps_baseline='display migrated export, with explicit RF PL interface overrides',ps_overrides=overrides,
        ps_boot_configuration_verified=False,board_operations=False,boot_files_modified=False,
        omitted_display_cells=sorted(skip),display_axi_ports={'TPG':0,'ClockWiz':1,'VTC':2,'VDMA':3},
        clocks={'GP0_RF_HP1_HP2':100000000,'display_HP0':200000000,'RF_delay':200000000},
        limitations=['No release approval for PS initialization','External IO constraints, CDC, timing and IP functional migration pending'])
    report['generated']=[dict(path=str(f),sha256=digest(f)) for f in work.rglob('*') if f.is_file()]
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    pointer=dict(work=str(work),preparation=str(out/'report.json'),project=str(work/'project/combined.xpr'))
    (ROOT/'results/p30-active-build.json').write_text(json.dumps(pointer,indent=2)+'\n',encoding='utf-8')
    print(out)


if __name__=='__main__':
    main()
