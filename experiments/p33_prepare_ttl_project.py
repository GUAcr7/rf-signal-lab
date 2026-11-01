"""Fresh PWM2 + TTL-only 33MHz source candidate; no board or bitstream writes.

The ADI CDC candidate is intentionally kept in its independent experiment.
This clone still uses the pinned vendor DMA RTL.
"""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import shutil
import subprocess
from p32_session import ROOT

SOURCE = Path('E:/p32-pwm2-105934')
REMOVED_PORTS = ['lvds_clk_out_n', 'lvds_clk_out_p', 'lvds_data_out_n',
    'lvds_data_out_p', 'o_video_data', 'o_video_de', 'o_video_hsync',
    'o_video_pclk', 'o_video_vsync']
REMOVED_CELLS = ['dual_pixel_24bpp_lvds_mapping_0', 'lvds_n_x_7to1_sdr_tx_0']
BD = Path('project/combined.srcs/sources_1/bd/system/system.bd')

def sha(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out = ROOT/'results'/('p33-ttl-project-'+stamp)
    out.mkdir(exist_ok=False)
    work = Path('E:/p33-ttl-'+stamp[9:15])
    work.mkdir(exist_ok=False)
    critical = [SOURCE/'project/combined.xpr', SOURCE/BD,
        SOURCE/'hdl/rf_display_top.v', SOURCE/'constraints/display.xdc',
        SOURCE/'constraints/rf.xdc', SOURCE/'constraints/half_clock.xdc']
    before = {str(p):sha(p) for p in critical}
    report = dict(status='copying',source=str(SOURCE),work=str(work),
        hardware_operations=False,bitstream_generated=False,
        synthesis_or_route_run=False,source_hashes_before=before,
        dma_rtl='unmodified_vendor_baseline')
    def save():
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    save()
    try:
        (work/'project').mkdir()
        for name in ['hdl','constraints']:
            shutil.copytree(SOURCE/name, work/name)
        shutil.copytree(SOURCE/'project/combined.srcs',work/'project/combined.srcs')
        xpr = (SOURCE/'project/combined.xpr').read_text('utf-8')
        (work/'project/combined.xpr').write_text(xpr.replace(SOURCE.as_posix(),work.as_posix()),encoding='utf-8',newline='\n')
        top = work/'hdl/rf_display_top.v'
        text = top.read_text('utf-8')
        for port in REMOVED_PORTS:
            text,n1 = re.subn(r'^\s*output wire[^\n]*\b'+port+r',\s*\n','',text,flags=re.M)
            text,n2 = re.subn(r'^\s*\.'+port+r'\s*\('+port+r'\),\s*\n','',text,flags=re.M)
            if (n1,n2)!=(1,1):
                raise RuntimeError('unexpected top-level port occurrence '+port+str((n1,n2)))
        top.write_text(text,encoding='utf-8',newline='\n')
        xdc = work/'constraints/display.xdc'
        kept = [line for line in xdc.read_text('utf-8').splitlines() if 'lvds_' not in line and 'o_video' not in line]
        xdc.write_text('\n'.join(kept)+'\n',encoding='utf-8',newline='\n')
        tcl = f'''set_param general.maxThreads 2
open_project {{{(work/'project/combined.xpr').as_posix()}}}
if {{[get_property PART [current_project]] ne "xc7z100ffg900-2"}} {{error "wrong device"}}
open_bd_design [get_files */system.bd]
foreach name {{{' '.join(REMOVED_CELLS)}}} {{
  set obj [get_bd_cells -quiet $name]
  if {{[llength $obj] != 1}} {{error "missing unused branch $name"}}
  delete_bd_objs $obj
}}
foreach name {{{' '.join(REMOVED_PORTS)}}} {{
  set obj [get_bd_ports -quiet $name]
  if {{[llength $obj] != 1}} {{error "missing removed port $name"}}
  delete_bd_objs $obj
}}
set_property CONFIG.CLKOUT1_REQUESTED_OUT_FREQ {{33.000}} [get_bd_cells clk_wiz_0]
set half [get_files -quiet */half_clock.xdc]
if {{[llength $half] != 1}} {{error "half-clock XDC ambiguous"}}
remove_files $half
validate_bd_design
save_bd_design
write_bd_tcl -force {{{(work/'p33-ttl-validated.tcl').as_posix()}}}
puts "P33_TTL_BD_VALIDATED no_synthesis_no_bitstream"
close_project
exit 0
'''
        script = work/'prepare-ttl.tcl'
        script.write_text(tcl,encoding='utf-8',newline='\n')
        (out/'executed.tcl').write_text(tcl,encoding='utf-8',newline='\n')
        command = ['E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat','-mode','batch',
            '-source',str(script),'-log',str(work/'prepare.log'),'-journal',str(work/'prepare.jou')]
        report['command']=command
        save()
        result=subprocess.run(command,cwd=work,capture_output=True,timeout=240)
        (out/'stdout.txt').write_bytes(result.stdout)
        (out/'stderr.txt').write_bytes(result.stderr)
        report['exit_code']=result.returncode
        if result.returncode or b'P33_TTL_BD_VALIDATED' not in result.stdout:
            raise RuntimeError('Vivado TTL BD validation failed')
        old=json.loads((SOURCE/BD).read_text('utf-8'))['design']
        new=json.loads((work/BD).read_text('utf-8'))['design']
        expected_cells=set(old['components'])-set(REMOVED_CELLS)
        if set(new['components'])!=expected_cells:
            raise RuntimeError('unexpected component addition/removal')
        changed=[name for name in expected_cells if old['components'][name]!=new['components'][name]]
        if changed!=['clk_wiz_0']:
            raise RuntimeError('unexpected changed cells '+str(changed))
        if set(new['ports'])!=set(old['ports'])-set(REMOVED_PORTS):
            raise RuntimeError('unexpected external port changes')
        def surviving_endpoints(design):
            endpoints=set()
            for net in design['nets'].values():
                pins=frozenset(p for p in net['ports'] if p not in REMOVED_PORTS and p.split('/')[0] not in REMOVED_CELLS)
                if len(pins)>1:
                    endpoints.add(pins)
            return endpoints
        if surviving_endpoints(old)!=surviving_endpoints(new):
            raise RuntimeError('surviving scalar connections changed')
        if old.get('interface_nets')!=new.get('interface_nets'):
            raise RuntimeError('interface nets changed')
        if old.get('addressing')!=new.get('addressing'):
            raise RuntimeError('address map changed')
        config=new['components']['clk_wiz_0']['parameters']
        values={key:value['value'] for key,value in config.items()}
        for key,expected in {'PRIM_SOURCE':'No_buffer','USE_DYN_RECONFIG':'true',
                'NUM_OUT_CLKS':'1','CLKOUT2_USED':'false'}.items():
            if values[key]!=expected:
                raise RuntimeError('ClockWiz contract '+key)
        if float(values['PRIM_IN_FREQ'])!=100 or float(values['CLKOUT1_REQUESTED_OUT_FREQ'])!=33:
            raise RuntimeError('pixel clock contract')
        if float(new['ports']['lcd_pclk']['parameters']['FREQ_HZ']['value'])!=33000000:
            raise RuntimeError('pixel port metadata')
        if sha(work/'constraints/rf.xdc')!=sha(SOURCE/'constraints/rf.xdc'):
            raise RuntimeError('RF constraints changed')
        report.update(status='passed_BD_and_source_contract_not_synthesized',
            removed_cells=REMOVED_CELLS,removed_ports=REMOVED_PORTS,
            changed_cells=changed,clock_wizard=values,
            preserved_scalar_connections=True,preserved_interface_connections=True,
            preserved_address_map=True,preserved_RF_constraints=True,
            candidate_hashes={str(p.relative_to(work)):sha(p) for p in [work/'project/combined.xpr',work/BD,top,xdc]})
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        report['source_hashes_after']={str(p):sha(p) for p in critical}
        report['source_unchanged']=before==report['source_hashes_after']
        if not report['source_unchanged']:
            report['status']='failed_source_changed'
        save()
        print(out,flush=True)
        print(report['status'],flush=True)
        print(work,flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':
    raise SystemExit(main())
