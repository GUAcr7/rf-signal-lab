"""Inventory actual vendor sources and test XC7Z100 synthesis capability offline."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess,zipfile
from pathlib import Path
from p22_acquire_comparison import ROOT


def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p27-fpga-readiness-'+stamp);out.mkdir(exist_ok=False)
    work=Path('E:/FPGA_Tools/Work')/('p27-license-'+stamp)
    work.mkdir(exist_ok=False)
    source=Path('D:/AD9361/AD9361/软件资料/Demo/hw/src')
    sources=[{'path':str(p),'bytes':p.stat().st_size,'sha256':hashlib.sha256(p.read_bytes()).hexdigest()}
             for p in sorted(source.rglob('*')) if p.is_file()]
    script=(source/'scripts/system_bd.tcl').read_text('utf-8-sig')
    versions=re.findall(r'^set scripts_vivado_version\s+([0-9.]+)',script,re.M)
    archive=Path('D:/xilinx/xilinx/4-软件资料/Demo.zip')
    with zipfile.ZipFile(archive) as z:
        display_sources=[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()
                         if 'axi_video_display' in i.filename and Path(i.filename).suffix.lower() in ('.tcl','.v','.vhd','.xdc','.xpr','.bd','.xci')]
    (work/'probe.v').write_text('module license_probe(input wire a, output wire y); assign y = a; endmodule\n',encoding='ascii')
    tcl='''set expected xc7z100ffg900-2
puts "P27_TOOL [version -short]"
puts "P27_Z100_PARTS [get_parts -quiet xc7z100*]"
puts "P27_Z020_PARTS [get_parts -quiet xc7z020*]"
help get_parts
puts "P27_PART_COUNT [llength [get_parts -quiet $expected]]"
if {![llength [get_parts -quiet $expected]]} { puts "P27_PART_MISSING"; exit 3 }
create_project -in_memory -part $expected
read_verilog probe.v
if {[catch {synth_design -top license_probe -part $expected} reason]} {
    puts "P27_SYNTHESIS_BLOCKED $reason"
    exit 4
}
puts "P27_SYNTHESIS_CAPABILITY_PASS"
exit 0
'''
    (work/'probe.tcl').write_text(tcl,encoding='ascii')
    tool=Path('E:/FPGA_Tools/Xilinx/Vivado/2021.1/bin/vivado.bat')
    args=[str(tool),'-mode','batch','-notrace','-source','probe.tcl','-log','probe.log','-journal','probe.jou']
    # All command arguments are fixed ASCII paths created above. No vendor
    # project script (which uses -force and relative output paths) is executed.
    result=subprocess.run(args,cwd=work,capture_output=True,timeout=150)
    (out/'stdout.txt').write_bytes(result.stdout);(out/'stderr.txt').write_bytes(result.stderr)
    for name in ('probe.v','probe.tcl','probe.log','probe.jou'):
        path=work/name
        if path.exists():(out/name).write_bytes(path.read_bytes())
    text=(result.stdout+result.stderr).decode('utf-8',errors='replace')
    report={'status':'synthesis_capability_pass' if result.returncode==0 and 'P27_SYNTHESIS_CAPABILITY_PASS' in text else 'synthesis_capability_blocked',
            'exit_code':result.returncode,'tool':str(tool),'work_directory':str(work),'part':'xc7z100ffg900-2',
            'RF_used':False,'vendor_files_modified':False,'vendor_rf_sources':sources,'vendor_bd_version_lines':versions,
            'vendor_display_source_members':display_sources,'vendor_display_archive':str(archive),
            'scope':'Only a one-wire toy design is synthesized. Passing is not RF/LCD integration, timing or bitstream acceptance.'}
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(report['status'],'exit',result.returncode,'display source members',len(display_sources))
    print(out)


if __name__=='__main__':main()
