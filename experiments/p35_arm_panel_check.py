"""Host numerical/geometry regressions and pinned ARM cross-build; no board I/O."""
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import subprocess
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
ARM=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')

def posix(path):
    value=Path(path).resolve().as_posix()
    return '/mnt/'+value[0].lower()+value[2:]

def sha(path):return hashlib.sha256(path.read_bytes()).hexdigest()

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-arm-panel-check-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source=ROOT/'embedded/arm_panel/arm_panel.c'
    font=source.with_name('font8x12.h')
    report=dict(status='running',checks=[],stages=[],board_operations=False,
        ARM_execution=False,source=str(source),source_sha256=sha(source),font_sha256=sha(font),
        limitations=['Host numerical and geometry tests are not framebuffer hardware tests',
            'Compute timings exclude file I/O, scanout/vsync and RF capture',
            'ARM binary compiled/readelf checked, not executed by this runner'])
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    def check(name,passed,detail=None):
        report['checks'].append(dict(name=name,passed=bool(passed),detail=detail))
        save()
        if not passed:raise RuntimeError(name)
    def run(label,command,expect=0,timeout=90):
        result=subprocess.run([str(x) for x in command],capture_output=True,timeout=timeout)
        (out/(label+'.stdout')).write_bytes(result.stdout)
        (out/(label+'.stderr')).write_bytes(result.stderr)
        report['stages'].append(dict(name=label,command=[str(x) for x in command],exit_code=result.returncode))
        save()
        if result.returncode!=expect:raise RuntimeError(label+' unexpected exit '+str(result.returncode))
        return result.stdout.decode('utf-8',errors='replace')
    for path in [source,font,Path(__file__)]:
        (out/path.name).write_bytes(path.read_bytes())
    save()
    try:
        host=out/'arm-panel-host'
        flags=['-std=c11','-O2','-Wall','-Wextra','-Werror']
        run('host-build',['wsl.exe','--exec','/usr/bin/gcc',*flags,posix(source),'-lm','-o',posix(host)])
        def fixture(name,data):
            path=out/(name+'.iq')
            path.write_bytes(data)
            return path
        n=np.arange(8192)
        def tone(k,channels=2):
            data=np.zeros((8192,channels),dtype='<i2')
            data[:,0]=np.rint(1000*np.cos(2*np.pi*k*n/1024)).astype(np.int16)
            data[:,1]=np.rint(1000*np.sin(2*np.pi*k*n/1024)).astype(np.int16)
            if channels>2:data[:,2:]=12345
            return data
        rows={}
        for name,k,channels in [('positive',73,2),('negative',-137,4),('dc',0,8)]:
            data=tone(k,channels)
            path=fixture(name,data.tobytes())
            for frames in [1,2,8]:
                label=name+'-frames'+str(frames)
                text=run(label,['wsl.exe','--exec',posix(host),'--analyse-only',posix(path),channels,frames,1])
                row=json.loads(next(s for s in text.splitlines() if s.startswith('{')))
                rows[label]=row
                x=data[:frames*1024,0].astype(float)+1j*data[:frames*1024,1].astype(float)
                window=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32)
                power=np.mean(abs(np.fft.fft(x.reshape(frames,1024)*window,axis=1))**2,axis=0)/(1024*np.sum(window.astype(float)**2))
                expected_db=10*np.log10(np.max(power))
                check(label+' signed bin',row['peak_valid'] and row['peak_offset_bins']==k,row)
                check(label+' numpy normalized bin power',abs(row['peak_db']-expected_db)<.002,dict(actual=row['peak_db'],expected=expected_db))
                check(label+' numpy component RMS',abs(row['rms_per_component_counts']-np.sqrt(np.mean(abs(x)**2)/2))<1e-6)
                check(label+' numpy summed bin power',abs(row['spectrum_power_sum_counts_squared']/float(np.sum(power))-1)<1e-5)
                check(label+' timing scope',row['analysis_ms']>=0 and row['draw_ms']==0 and row['iteration_compute_ms']>=row['analysis_ms'] and not row['display_refresh_measured'] and not row['capture_throughput_measured'] and 'fps=' not in text)
            check(name+' averaging count invariant',abs(rows[name+'-frames1']['peak_db']-rows[name+'-frames8']['peak_db'])<1e-5)
        zero=fixture('zero',np.zeros((2048,2),dtype='<i2').tobytes())
        text=run('zero',['wsl.exe','--exec',posix(host),'--analyse-only',posix(zero),2,8,2])
        zero_rows=[json.loads(s) for s in text.splitlines() if s.startswith('{')]
        check('zero input has no invented peak',len(zero_rows)==2 and all(not r['peak_valid'] and r['peak_offset_bins'] is None and r['rms_per_component_counts']==0 and r['spectrum_power_sum_counts_squared']==0 and r['peak_db']==-300 for r in zero_rows) and 'peak=none offset=none' in text and 'offset=-512' not in text)
        for name,data in [('odd',b'abc'),('partial-channel',b'\0'*6),('short',b'\0'*(1023*4))]:
            path=fixture(name,data)
            run(name,['wsl.exe','--exec',posix(host),'--analyse-only',posix(path),2,1,1],expect=2)
            check(name+' rejected',True)
        positive=out/'positive.iq'
        bad_args=[['2x'],['999999999999999999999999'],['2','0'],['2','4097'],['2','1','-1'],['2','1','4097'],['2','1','1','extra']]
        for i,args in enumerate(bad_args):
            run('invalid-'+str(i),['wsl.exe','--exec',posix(host),'--analyse-only',posix(positive),*args],expect=2)
            check('invalid arguments '+str(i)+' rejected',True)
        geometry=out/'geometry.c'
        geometry.write_text('''#define main panel_program_main
#include "arm_panel.c"
#undef main
#include <assert.h>
int main(void) {
 struct fb_fix_screeninfo f={0}; struct fb_var_screeninfo v={0}; size_t start=0,len=0;
 f.type=FB_TYPE_PACKED_PIXELS; f.visual=FB_VISUAL_TRUECOLOR; f.line_length=3200; f.smem_len=3200*480;
 v.xres=800;v.yres=480;v.xres_virtual=800;v.yres_virtual=480;v.bits_per_pixel=32;
 v.red.offset=16;v.red.length=8;v.green.offset=8;v.green.length=8;v.blue.length=8;
 assert(framebuffer_geometry(&f,&v,&start,&len)==0 && start==0 && len==3200*480);
 v.transp.offset=24;v.transp.length=8;assert(framebuffer_geometry(&f,&v,&start,&len)==0);
 v.xres_virtual=804;v.yres_virtual=482;v.xoffset=2;v.yoffset=1;f.line_length=3216;f.smem_len=3216*482;
 assert(framebuffer_geometry(&f,&v,&start,&len)==0 && start==3224 && len==3224+479*3216+3200);
 uint32_t *memory=malloc(f.smem_len);assert(memory);for(size_t i=0;i<f.smem_len/4;i++)memory[i]=0x12345678;
 fb=memory+start/4;fb_stride_words=f.line_length/4;fill(0x87654321);put(-1,0,0);put(800,0,0);
 assert(memory[0]==0x12345678 && memory[start/4]==0x87654321 && memory[start/4+800]==0x12345678);
 assert(memory[start/4+479*fb_stride_words+799]==0x87654321);free(memory);
 f.smem_len=(unsigned int)len-1;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);f.smem_len=3216*482;
 v.red.offset=0;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.red.offset=16;
 f.line_length=3199;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);f.line_length=3216;
 v.xoffset=5;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.xoffset=2;
 v.yoffset=3;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.yoffset=1;
 v.bits_per_pixel=16;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.bits_per_pixel=32;
 v.red.msb_right=1;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.red.msb_right=0;
 v.vmode=FB_VMODE_YWRAP;assert(framebuffer_geometry(&f,&v,&start,&len)!=0);v.vmode=0;
 puts("P35_PANEL_GEOMETRY_PASS");return 0;
}
''',encoding='utf-8',newline='\n')
        run('geometry-build',['wsl.exe','--exec','/usr/bin/gcc',*flags,posix(geometry),'-lm','-o',posix(out/'geometry')])
        text=run('geometry-test',['wsl.exe','--exec',posix(out/'geometry')])
        check('stride offsets boundaries and format geometry', 'P35_PANEL_GEOMETRY_PASS' in text)
        arm=out/'arm-panel'
        run('arm-build',['wsl.exe','--exec',posix(ARM/'arm-linux-gnueabihf-gcc'),*flags,
            '-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',posix(source),'-lm','-o',posix(arm)])
        elf=run('arm-readelf',['wsl.exe','--exec',posix(ARM/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-V','-d',posix(arm)])
        check('ARM32 hardfloat ELF', 'ELF32' in elf and 'Machine:                           ARM' in elf and 'VFP registers' in elf and '/lib/ld-linux-armhf.so.3' in elf)
        check('source remained pinned',sha(source)==report['source_sha256'] and sha(font)==report['font_sha256'])
        report.update(status='passed_host_regressions_and_ARM_cross_compile_not_board_test',binary=str(arm),binary_sha256=sha(arm),binary_bytes=arm.stat().st_size,host_binary_sha256=sha(host),checks_count=len(report['checks']))
    except Exception as exc:
        report.update(status='failed',error=repr(exc))
    finally:
        save();print(out,flush=True);print(report['status'],flush=True)
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
