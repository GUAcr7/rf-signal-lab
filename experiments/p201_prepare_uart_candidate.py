"""Build/validate isolated P201 UART0 EMIO candidate off board; never programs hardware."""
from datetime import datetime,timezone
import difflib,hashlib,json,os,shutil,subprocess,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'src'))
from rfsig.p201_uart import candidate_sources,enabled_dts
from p201_uart_document_check import fdt_serial_properties

def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p201-uart-candidate-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/FPGA_Tools/Work')/('uart-'+stamp);work.mkdir(exist_ok=False)
    hdl=work/'hdl';project=hdl/'projects/pzp201'
    r=dict(status='preparing_offline',work=str(work),board_operations=False,
        bitstream_generated=False,board_tested=False,deployable=False,stages=[])
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    save()
    def run(label,args,cwd=ROOT,timeout=240):
        print(label,flush=True);log=out/(label+'.log')
        with log.open('wb') as f:
            completed=subprocess.run([str(a) for a in args],cwd=cwd,env=env,stdout=f,stderr=subprocess.STDOUT,timeout=timeout)
        r['stages'].append(dict(label=label,exit_code=completed.returncode,log=str(log.relative_to(ROOT))));save()
        if completed.returncode:raise RuntimeError(label+' failed; see saved log')
    env=os.environ.copy()
    for key in list(env):
        if key.startswith('ADI_') or key=='REQUIRED_VIVADO_VERSION':env.pop(key)
    env.update(ADI_HDL_DIR=hdl.as_posix(),REQUIRED_VIVADO_VERSION='2021.1',ADI_MAX_OOC_JOBS='2')
    tool=Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat')
    try:
        manifest=json.loads((ROOT/'fpga/vendor-baseline/source-manifest.json').read_text('utf-8'))
        rows=[]
        for row in manifest['files']:
            src=ROOT/'fpga/vendor-baseline'/row['relative_path']
            if sha(src)!=row['sha256']:raise ValueError('vendor source changed')
            dest=hdl/Path(row['archive_member']).relative_to('plutosdr-fw/hdl')
            dest.parent.mkdir(parents=True,exist_ok=True);shutil.copy2(src,dest);rows.append((src,row['sha256']))
        r['vendor_source_count']=len(rows);r['vendor_manifest_sha256']=sha(ROOT/'fpga/vendor-baseline/source-manifest.json')
        names=('system_bd.tcl','system_top.v','system_constr.xdc')
        old=[(project/n).read_text() for n in names]
        patched=candidate_sources(*old)
        for name,a,b in zip(names,old,patched):
            (project/name).write_text(b,encoding='utf-8',newline='\n')
            (out/name).write_text(b,encoding='utf-8',newline='\n')
            (out/(name+'.diff')).write_text(''.join(difflib.unified_diff(a.splitlines(True),b.splitlines(True),fromfile='vendor/'+name,tofile='candidate/'+name)),encoding='utf-8')
        # DTC compile and complete tree comparison, permitting only these UART properties.
        dtbin=Path(json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'))['bin'])
        original=Path('D:/FPGA natch/pluto/devicetree.dtb');shutil.copy2(original,out/'original.dtb')
        run('dtc-original',[dtbin/'dtc.exe','-I','dtb','-O','dts','-o',out/'original.dts',original])
        (out/'candidate.dts').write_text(enabled_dts((out/'original.dts').read_text()),encoding='utf-8')
        run('dtc-candidate',[dtbin/'dtc.exe','-I','dts','-O','dtb','-o',out/'candidate.dtb',out/'candidate.dts'])
        run('dtc-roundtrip',[dtbin/'dtc.exe','-I','dtb','-O','dts','-o',out/'candidate-roundtrip.dts',out/'candidate.dtb'])
        before=fdt_serial_properties(original.read_bytes());after=fdt_serial_properties((out/'candidate.dtb').read_bytes())
        expected=json.loads(json.dumps(before));expected['/amba/serial@e0000000']['status']='okay'
        expected['/aliases'].update(serial0='/amba/serial@e0001000',serial1='/amba/serial@e0000000')
        expected['/chosen']['stdout-path']='/amba/serial@e0001000:115200n8'
        if after!=expected:raise ValueError('unexpected serial properties')
        # Strip the four intentionally changed properties then require the ENTIRE DTS to match.
        import re
        def normalized(text):
            text=re.sub(r'\bserial[01]\s*=\s*"[^"]*";','',text)
            text=re.sub(r'\bstdout-path\s*=\s*"[^"]*";','',text)
            text=re.sub(r'(serial@e0000000\s*\{[^}]*?status\s*=\s*)"(?:okay|disabled)"',r'\1"UART0_STATUS"',text,flags=re.S)
            return re.sub(r'\s+','',text)
        if normalized((out/'original.dts').read_text())!=normalized((out/'candidate-roundtrip.dts').read_text()):raise ValueError('non-UART device-tree property changed')
        r['DTB_checks']=dict(serial_properties_exact=True,all_other_tree_properties_unchanged=True,console_UART1_preserved=True,UART0_enabled=True,serial_properties=after)
        r['original_DTB_sha256']=sha(original)
        run('host-tests',[sys.executable,'-m','pytest','tests/test_p201_uart_candidate.py','-q','--junitxml='+str(out/'tests.xml')])
        libraries=('axi_ad9361','util_cdc','util_axis_fifo','axi_dmac','util_pack/util_cpack2','util_pack/util_upack2')
        for item in libraries:
            folder=hdl/'library'/item;name=item.rsplit('/',1)[-1]
            run('package-'+name,[tool,'-mode','batch','-notrace','-source',name+'_ip.tcl'],folder)
        tcl=project/'uart_validate.tcl'
        tcl.write_text('''source ../scripts/adi_env.tcl
source $ad_hdl_dir/projects/scripts/adi_project_xilinx.tcl
source $ad_hdl_dir/projects/scripts/adi_board.tcl
set p_device xc7z020clg400-2
adi_project pzp201
adi_project_files pzp201 [list system_top.v system_constr.xdc "$ad_hdl_dir/library/common/ad_iobuf.v"]
set_property top system_top [current_fileset]
validate_bd_design
set ps [get_bd_cells sys_ps7]
if {[get_property CONFIG.PCW_UART0_PERIPHERAL_ENABLE $ps] != 1} {error "UART0 disabled"}
if {[get_property CONFIG.PCW_UART0_UART0_IO $ps] ne "EMIO"} {error "UART0 not EMIO"}
if {[get_property CONFIG.PCW_UART1_UART1_IO $ps] ne "MIO 12 .. 13"} {error "console moved"}
foreach {port pin direction} {ext_uart_tx UART0_TX O ext_uart_rx UART0_RX I} {
  if {[get_property DIR [get_bd_ports $port]] ne $direction} {error "UART direction"}
  set net [get_bd_nets -of_objects [get_bd_ports $port]]
  set expected [get_bd_nets -of_objects [get_bd_pins sys_ps7/$pin]]
  if {[llength $net] != 1 || $net ne $expected} {error "UART disconnected"}
}
write_bd_tcl -force uart-generated-bd.tcl
report_ip_status -file uart-ip-status.rpt
puts "UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS"
update_compile_order -fileset sources_1
puts "UART_CANDIDATE_READY_FOR_FULL_SYNTHESIS"
close_project
''',encoding='utf-8')
        shutil.copy2(tcl,out/tcl.name)
        run('vivado-uart-validation',[tool,'-mode','batch','-notrace','-source',tcl.name],project,timeout=900)
        log=(out/'vivado-uart-validation.log').read_text(errors='replace')
        if not all(s in log for s in ('UART_BD_ROUTE_AND_CONSOLE_CHECKS_PASS','UART_CANDIDATE_READY_FOR_FULL_SYNTHESIS')):raise ValueError('missing tool acceptance markers')
        for name in ('uart-generated-bd.tcl','uart-ip-status.rpt'):
            shutil.copy2(project/name,out/name)
        wrapper=list(project.glob('pzp201.srcs/**/system_wrapper.v'))
        for i,p in enumerate(wrapper):shutil.copy2(p,out/('wrapper-'+str(i)+'.v'))
        r['pristine_sources_unchanged']=all(sha(p)==digest for p,digest in rows)
        if not r['pristine_sources_unchanged']:raise ValueError('original sources mutated')
        r['status']='passed_offline_BD_UART0_route_console_DTB_pending_full_synthesis'
    except Exception as e:r.update(status='failed_or_incomplete_offline_candidate',error=repr(e))
    r['saved_files_sha256']={p.name:sha(p) for p in out.iterdir() if p.is_file() and p.name!='report.json'}
    save();print(out/'report.json',flush=True);print(r['status'],flush=True)
    return 0 if r['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
