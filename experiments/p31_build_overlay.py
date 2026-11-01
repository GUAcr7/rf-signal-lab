"""Rebuild symbolic factory overlays into one offline P30-matched candidate."""
from datetime import datetime, timezone
import ctypes
import hashlib
import json
from pathlib import Path
import re
import shutil
import struct
import subprocess
from p30_display_profile import properties

ROOT=Path(__file__).resolve().parents[1]


def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()


def remove_node(text,name):
    match=re.search(r'^\s*'+re.escape(name)+r'\s*\{',text,re.M)
    if not match:return text
    start=match.start();pos=match.end();depth=1;quoted=False;escaped=False
    while depth:
        char=text[pos];pos+=1
        if quoted:
            if escaped:escaped=False
            elif char=='\\':escaped=True
            elif char=='"':quoted=False
        elif char=='"':quoted=True
        elif char=='{':depth+=1
        elif char=='}':depth-=1
    if text[pos:pos+1]!=';':raise ValueError('node terminator missing')
    return text[:start]+text[pos+1:]


def clean_body(text,prefix,start):
    # DTC 1.8 reconstructs symbolic references from the blob's fixup metadata.
    # Remove stale metadata and regenerate it once, rather than relocating twice.
    for name in ['__symbols__','__fixups__','__local_fixups__']:text=remove_node(text,name)
    text=re.sub(r'^\s*(?:linux,)?phandle\s*=.*?;\s*$', '',text,flags=re.M)
    labels=set(re.findall(r'\b([A-Za-z_][A-Za-z0-9_]*):\s*[^;\n]*\{',text))
    referenced=set(re.findall(r'&([A-Za-z_][A-Za-z0-9_]*)',text))
    for label in sorted(labels,key=len,reverse=True):
        if label in referenced:
            text=re.sub(r'\b'+re.escape(label)+r':',prefix+label+':',text)
            text=re.sub(r'&'+re.escape(label)+r'\b','&'+prefix+label,text)
        else:
            text=re.sub(r'\b'+re.escape(label)+r':\s*','',text)
    numbers=re.findall(r'fragment@(\d+)\s*\{',text)
    mapping={n:str(start+i) for i,n in enumerate(numbers)}
    text=re.sub(r'fragment@(\d+)(?=\s*\{)',lambda m:'fragment@'+mapping[m[1]],text)
    begin=text.index('/ {')+3;end=text.rfind('};')
    return text[begin:end].strip(),len(numbers)


def main():
    source=ROOT/'results/p31-board-contract-20261019T135528Z'
    raw=json.loads((source/'report.json').read_text('utf-8'))
    if raw['status']!='original_blobs_and_runtime_contract_archived_read_only':raise RuntimeError('unaccepted originals')
    for item in raw['files']:
        if sha(source/item['file'])!=item['sha256']:raise RuntimeError('original bytes changed')
    tool=json.loads((ROOT/'results/p31-dtc-active.json').read_text('utf-8'));bin=Path(tool['bin'])
    out=ROOT/'results'/('p31-overlay-'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'));out.mkdir(exist_ok=False)
    report=dict(status='running',stages=[],source_report=str(source/'report.json'),tool_report=tool['evidence'],
        board_operations=False,overlay_applied_to_hardware=False,bitstream_generated=False,changes=[],checks=[])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def run(name,args):
        result=subprocess.run([str(a) for a in args],capture_output=True,timeout=35)
        (out/(name+'.stdout')).write_bytes(result.stdout);(out/(name+'.stderr')).write_bytes(result.stderr)
        report['stages'].append(dict(name=name,command=[str(a) for a in args],exit_code=result.returncode));save()
        if result.returncode:raise RuntimeError(name+' failed')
    def apply_native(name,base_path,overlays,output):
        # The packaged Windows fdtoverlay utility short-reads this captured blob
        # at 4096 bytes. Use the same pinned native libfdt with explicit binary
        # buffers, retaining the failed CLI report as evidence of that limitation.
        library=ctypes.CDLL(str(bin/'libfdt-1.dll'))
        library.fdt_open_into.argtypes=[ctypes.c_void_p,ctypes.c_void_p,ctypes.c_int]
        library.fdt_overlay_apply.argtypes=[ctypes.c_void_p,ctypes.c_void_p]
        library.fdt_check_full.argtypes=[ctypes.c_void_p,ctypes.c_size_t]
        library.fdt_pack.argtypes=[ctypes.c_void_p]
        library.fdt_strerror.argtypes=[ctypes.c_int];library.fdt_strerror.restype=ctypes.c_char_p
        data=base_path.read_bytes();inputs=[p.read_bytes() for p in overlays]
        capacity=len(data)+sum(map(len,inputs))*2+65536
        base=ctypes.create_string_buffer(capacity);original=ctypes.create_string_buffer(data)
        calls=[]
        def checked(function,*args):
            result=getattr(library,function)(*args)
            calls.append(dict(function=function,exit_code=result))
            if result:raise RuntimeError(name+' '+function+' '+library.fdt_strerror(result).decode())
        checked('fdt_check_full',original,len(data))
        checked('fdt_open_into',original,base,capacity)
        for payload in inputs:
            overlay=ctypes.create_string_buffer(payload)
            checked('fdt_check_full',overlay,len(payload))
            checked('fdt_overlay_apply',base,overlay)
        checked('fdt_pack',base)
        size=struct.unpack_from('>I',base.raw,4)[0]
        checked('fdt_check_full',base,size)
        output.write_bytes(base.raw[:size])
        report['stages'].append(dict(name=name,native_library=str(bin/'libfdt-1.dll'),calls=calls,exit_code=0));save()
    def check(name,condition,detail=None):
        report['checks'].append(dict(check=name,passed=bool(condition),detail=detail))
    def replace_once(text,before,after,reason):
        if text.count(before)!=1:raise RuntimeError('nonunique expected source: '+before)
        report['changes'].append(dict(reason=reason,before=before,after=after))
        return text.replace(before,after)
    save()
    try:
        bodies=[];number=0
        for role in ['rf','display']:
            dts=out/('original-'+role+'.dts')
            run('decompile-'+role,[bin/'dtc.exe','-I','dtb','-O','dts','-o',dts,source/('factory-'+role+'.dtbo')])
            body,count=clean_body(dts.read_text('utf-8'),role+'_',number);number+=count
            if role=='rf':
                # P30 AXI-Lite and memory-facing RF DMA clocks are all FCLK0.
                check('two original DMA clock references',body.count('clocks = <&clkc>, <0x10>;')==2)
                body=body.replace('clocks = <&clkc>, <0x10>;','clocks = <&clkc>, <0x0f>;')
                report['changes'].append(dict(reason='RF DMA clocks now match FCLK0 100MHz',changed_nodes=2))
                for address in ['7c400000','7c420000']:
                    body=replace_once(body,f'reg = <0x{address} 0x10000>;',f'reg = <0x{address} 0x1000>;',
                        'DMA resource matches the actual 4KiB hardware decode; driver compatibility remains a hardware gate')
            else:
                body=replace_once(body,'clocks = <&clkc>, <0x0f>, <&clkc>, <0x0f>;',
                    'clocks = <&clkc>, <0x0f>, <&clkc>, <0x10>;','ClockWiz input stays FCLK0; AXI control uses FCLK1')
                body=replace_once(body,'firmware-name = "system_wrapper.bin";',
                    'firmware-name = "rf-display-p31.bin";','Unique future merged firmware name prevents loading an unrelated factory bitstream')
            bodies.append(body)
        text='''// Generated from hash-verified factory DTBOs captured in p31-board-contract.
// Offline candidate only. Native FDT application is not a kernel or board test.
// No deployed firmware currently has the unique rf-display-p31.bin name.
/dts-v1/;
/plugin/;
/ {
'''+ '\n\n'.join(bodies)+'\n};\n'
        # The RF-only artifact allows a bounded, reversible driver-contract
        # test on the existing factory RF fabric, without loading any bitstream.
        rf_source=out/'rf-only-driver-check.dts'
        rf_source.write_text('/dts-v1/;\n/plugin/;\n/ {\n'+bodies[0]+'\n};\n',encoding='utf-8',newline='\n')
        rf_blob=out/'rf-only-driver-check.dtbo'
        run('compile-rf-only',[bin/'dtc.exe','-@','-I','dts','-O','dtb','-o',rf_blob,rf_source])
        check('RF-only cannot trigger firmware reload',not any(k.endswith('/firmware-name') for k in properties(rf_blob.read_bytes())))
        candidate=out/'rf-display-800x480.dts';candidate.write_text(text,encoding='utf-8',newline='\n')
        blob=out/'rf-display-800x480.dtbo'
        run('compile',[bin/'dtc.exe','-@','-I','dts','-O','dtb','-o',blob,candidate])
        applied=out/'offline-combined-base.dtb'
        apply_native('apply-on-PC',source/'boot-base.dtb',[blob],applied)
        run('decompile-applied',[bin/'dtc.exe','-I','dtb','-O','dts','-o',out/'offline-combined-base.dts',applied])
        props=properties(applied.read_bytes())
        (out/'applied-properties.json').write_text(json.dumps(props,indent=2)+'\n',encoding='utf-8')
        def cells(path):return props[path]['u32']
        def strings(path):return props[path]['strings']
        clock=cells('/amba/slcr@f8000000/clkc@100/phandle')[0]
        for address,irq in [('7c400000',57),('7c420000',56)]:
            node='/amba/dma@'+address
            check(node+' exact address decode',cells(node+'/reg')==[int(address,16),4096])
            check(node+' FCLK0 reference',cells(node+'/clocks')==[clock,15])
            check(node+' original GIC input preserved',cells(node+'/interrupts')==[0,irq,0])
        check('ClockWiz separate input and AXI clocks',cells('/amba/clk_wiz@43c10000/clocks')==[clock,15,clock,16])
        check('VDMA all five clocks FCLK1',cells('/amba/dma@43000000/clocks')==[clock,16]*5)
        check('unique future firmware name',strings('/fpga-full/firmware-name')==['rf-display-p31.bin'])
        for name,value in [('hactive',800),('vactive',480),('htotal',1056),('vtotal',528),('clock-frequency',33000)]:
            check('preserved 480p '+name,cells('/amba/lcd_800x480/'+name)==[value])
        handles={}
        for path,value in props.items():
            if path.endswith('/phandle'):
                handle=value['u32'][0]
                check('unique handle '+path,handle not in handles)
                handles[handle]=path.rsplit('/',1)[0]
        references={
            '/amba/cf-ad9361-lpc@79020000/dmas':[(0,'/amba/dma@7c400000')],
            '/amba/cf-ad9361-lpc@79020000/spibus-connected':[(0,'/amba/spi@e0007000/ad9361-phy@0')],
            '/amba/cf-ad9361-dds-core-lpc@79024000/dmas':[(0,'/amba/dma@7c420000')],
            '/amba/xilinx_drm/planes/plane0/dmas':[(0,'/amba/dma@43000000')],
            '/amba/xilinx_drm/clocks':[(0,'/amba/clk_wiz@43c10000')],
            '/amba/xilinx_drm/xlnx,vtc':[(0,'/amba/v_tc@43c20000')],
            '/backlight/pwms':[(0,'/amba/ttc_pwm@0')],
        }
        for path,targets in references.items():
            for offset,target in targets:check('resolved reference '+path,handles.get(cells(path)[offset])==target)
        base=properties((source/'boot-base.dtb').read_bytes())
        for key,item in base.items():
            if key.endswith('/phandle'):check('base handle preserved '+key,props[key]['hex']==item['hex'])
        if not all(c['passed'] for c in report['checks']):raise RuntimeError('contract checks failed')
        # Independent original overlays are also applied natively for a baseline.
        baseline=out/'offline-factory-combined.dtb'
        apply_native('factory-baseline-on-PC',source/'boot-base.dtb',[source/'factory-rf.dtbo',source/'factory-display.dtbo'],baseline)
        before=properties(baseline.read_bytes())
        # All 100+ AD9361 configuration properties remain byte-identical. Only
        # reference-bearing properties can legally change their numeric handles.
        protected='/amba/spi@e0007000/ad9361-phy@0/'
        protected_count=0
        for key,item in before.items():
            if key.startswith(protected) and key.split('/')[-1].startswith('adi,'):
                protected_count+=1;check('unchanged RF property '+key,props[key]['hex']==item['hex'])
        report['protected_RF_properties']=protected_count
        if not all(c['passed'] for c in report['checks']):raise RuntimeError('protected RF property changed')
        dest=ROOT/'fpga/integration/rf-display-800x480.dts'
        if dest.exists():shutil.copy2(dest,out/'previous-source.dts')
        shutil.copy2(candidate,dest)
        report.update(status='compiled_native_PC_overlay_apply_and_contract_checks_passed_not_deployed',checks_count=len(report['checks']),
            files=[dict(file=p.name,sha256=sha(p)) for p in [candidate,blob,applied]],
            limitations=['No target kernel/driver or hardware proof','TTC PWM versus active timer ownership pending',
                '4KiB DMA driver compatibility must be confirmed on the target','CDC, external timing and merged PL release gates remain'])
        (ROOT/'results/p31-overlay-active.json').write_text(json.dumps(dict(report=str(out/'report.json'),source=str(dest),dtbo=str(blob)),indent=2)+'\n',encoding='utf-8')
    except Exception as error:report.update(status='failed',error=repr(error))
    finally:save()
    print(out);print(report['status']);print('checks',len(report['checks']))
    for c in report['checks']:
        if not c['passed']:print(c)
    if 'error' in report:print(report['error'])
    return 0 if report['status'].endswith('_not_deployed') else 1


if __name__=='__main__':raise SystemExit(main())
