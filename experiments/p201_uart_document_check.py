"""Archive P201 UART documentary evidence only; no board or serial access."""
from datetime import datetime, timezone
import hashlib,json,shutil,struct
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()

def fdt_serial_properties(data):
    magic,total,off,strings_off=struct.unpack_from('>4I',data)
    if magic!=0xd00dfeed or total>len(data):raise ValueError('invalid FDT header')
    path=[];properties={};pos=off
    while pos<total:
        token=struct.unpack_from('>I',data,pos)[0];pos+=4
        if token==1:
            end=data.index(b'\0',pos);path.append(data[pos:end].decode('ascii'));pos=(end+4)&~3
        elif token==2:path.pop()
        elif token==3:
            size,nameoff=struct.unpack_from('>II',data,pos);pos+=8
            start=strings_off+nameoff;end=data.index(b'\0',start);name=data[start:end].decode('ascii')
            value=data[pos:pos+size];pos=(pos+size+3)&~3
            node='/'.join(path) or '/'
            if ('serial' in node or node in ('/aliases','/chosen')) and name in ('status','compatible','reg','serial0','serial1','stdout-path','bootargs'):
                properties.setdefault(node,{})[name]=value.hex() if name=='reg' else value.rstrip(b'\0').decode('ascii',errors='replace')
        elif token==4:continue
        elif token==9:break
        else:raise ValueError('invalid FDT token')
    return properties

def main():
    now=datetime.now(timezone.utc);out=ROOT/'results'/now.strftime('p201-uart-docs-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    base=ROOT/'fpga/vendor-baseline/source/plutosdr-fw/hdl/projects/pzp201'
    inputs={
        'schematic':Path('D:/FPGA natch/01.芯片手册/ZYNQ7020/Puzhitech P201 P203-SCH.pdf'),
        'vendor_dtb':Path('D:/FPGA natch/pluto/devicetree.dtb'),
        **{name:base/name for name in ('system_bd.tcl','system_top.v','system_constr.xdc','system_project.tcl')}}
    rows={}
    for name,p in inputs.items():
        dest=out/(name+'.pdf' if name=='schematic' else p.name);shutil.copy2(p,dest)
        rows[name]=dict(path=str(p),sha256=sha(p),archived=dest.relative_to(ROOT).as_posix())
    for p in (ROOT/'tmp/p201-uart-review').iterdir():
        if p.suffix in ('.txt','.png'):shutil.copy2(p,out/p.name)
    xdc=(base/'system_constr.xdc').read_text();top=(base/'system_top.v').read_text();bd=(base/'system_bd.tcl').read_text()
    import re
    pins=set(re.findall(r'PACKAGE_PIN\s+(\w+)',xdc))
    if {'E17','E18'}&pins:raise ValueError('candidate pin already constrained')
    if 'CONFIG.PCW_UART1_UART1_IO "MIO 12 .. 13"' not in bd:raise ValueError('UART configuration changed')
    report=dict(status='documentary_feasibility_confirmed_extra_UART_not_implemented_or_board_tested',
        recorded_utc=now.isoformat(),board_operations=False,source_files=rows,
        schematic_pages=dict(PL=dict(pdf_page=4,sheet='7/17'),USB_UART=dict(pdf_page=7,sheet='10/17'),J19=dict(pdf_page=14,sheet='17/17')),
        configured_console='UART1 MIO12/13 through USB bridge; occupied console',
        candidate_assignment_proposed_only=[dict(header='J19',pin=5,net='IO_3P_35',package_pin='E17',bank=35,nominal_logic_volts=3.3,proposed_function='UART_TX'),
            dict(header='J19',pin=6,net='IO_5P_35',package_pin='E18',bank=35,nominal_logic_volts=3.3,proposed_function='UART_RX')],
        mixed_voltage_header=True,J19_power_pins={'1':'+5V','3':'+5V','2':'+3.3V','4':'+3.3V'},
        J19_dedicated_ground_pin_shown=False,ground_connection='separate verified board GND required; physical point not identified in this review',
        candidates_absent_from_inspected_XDC=True,external_UART_port_in_inspected_top=bool(re.search(r'\b(?:input|output|inout)\b[^;\n]*uart',top,re.I)),
        vendor_DTB_serial=fdt_serial_properties(inputs['vendor_dtb'].read_bytes()),
        limitations=['Schematic and vendor source/DTB, not current running image readback',
            'Physical board revision, header orientation, voltage and ground not measured',
            'No new bitstream, device-tree deployment, loopback, external screen protocol or peripheral compatibility test'],
        proposed_implementation='Enable unused PS UART via EMIO if confirmed available, or AXI UART Lite, route to candidate PL pins with LVCMOS33; rebuild and validate offline before any deployment')
    (out/'report.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
    print(out/'report.json');print(json.dumps(report['vendor_DTB_serial'],ensure_ascii=False,indent=2))

if __name__=='__main__':main()
