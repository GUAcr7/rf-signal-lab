"""Build/test native software FFT and a bounded capture -> analysis board bundle."""
import json,hashlib,subprocess,tarfile
from datetime import datetime,timezone
from pathlib import Path
import numpy as np
from rfsig.spectrum import power_periodogram
from rfsig.bandwidth import occupied_bandwidth
ROOT=Path(__file__).resolve().parents[1]

def lp(p):s=p.resolve().as_posix();return '/mnt/'+s[0].lower()+s[2:]
def verify(input,prefix):
    raw=np.frombuffer(input.read_bytes(),dtype='<i2').reshape(-1,1024,2);actual=np.frombuffer(prefix.with_suffix('.psd').read_bytes(),dtype='<f8').reshape(len(raw),1024);meta=json.loads(prefix.with_suffix('.json').read_text());assert len(meta['records'])==len(raw);errors=[]
    for i,pair in enumerate(raw):
        x=pair[:,0].astype(float)+1j*pair[:,1];ref=power_periodogram(x,30720000);roi=occupied_bandwidth(ref.frequency_hz,ref.psd,(-9e6,9e6));m=meta['records'][i]
        np.testing.assert_allclose(actual[i],ref.psd,rtol=1e-10,atol=1e-12)
        assert m['mean_power']==float(np.sum(pair.astype(np.int64)**2,dtype=np.int64)/1024)
        for key,value in [('weighted_power',ref.window_weighted_mean_power),('integrated_psd',ref.window_weighted_mean_power),('ROI_power',roi.observed_region_power)]:np.testing.assert_allclose(m[key],value,rtol=1e-11,atol=1e-10)
        for key,value in [('ROI_lower_hz',roi.lower_hz),('ROI_upper_hz',roi.upper_hz),('ROI_width_hz',roi.bandwidth_hz),('ROI_midpoint_hz',roi.center_baseband_hz)]:
            if value is None:assert m[key] is None
            else:np.testing.assert_allclose(m[key],value,rtol=0,atol=1e-6)
        errors.append(float(max(abs(actual[i]-ref.psd))))
    return {'frames':len(raw),'maximum_psd_absolute_error':max(errors),'benchmark':meta.get('benchmark')}

def main():
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ');prefix='arm-spectrum-'+stamp;out=ROOT/'results'/('p07b-arm-spectrum-'+stamp);out.mkdir();bundle=out/prefix;(bundle/'bin').mkdir(parents=True);(bundle/'inputs').mkdir();source=ROOT/'embedded/arm_rx_probe/arm_spectrum.c';host=out/'spectrum-host.exe';binary=bundle/'bin/arm-spectrum';flags=['-std=c11','-O2','-Wall','-Wextra','-Werror','-fno-fast-math','-ffp-contract=off']
    def run(label,cmd):
        r=subprocess.run(cmd,capture_output=True,timeout=180);(out/(label+'.stdout.txt')).write_bytes(r.stdout);(out/(label+'.stderr.txt')).write_bytes(r.stderr)
        if r.returncode:raise RuntimeError(label+' exit '+str(r.returncode))
        return r.stdout.decode()
    run('host-compile',['C:/msys64/ucrt64/bin/gcc.exe',*flags,str(source),'-o',str(host),'-lm'])
    tool=Path('E:/FPGA_Tools/ARM-GNU-A-8.3-2019.03/attempt-2/gcc-arm-8.3-2019.03-x86_64-arm-linux-gnueabihf/bin')
    run('arm-compile',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-gcc'),*flags,'-mcpu=cortex-a9','-mfpu=neon','-mfloat-abi=hard','-marm',lp(source),'-o',lp(binary),'-lm','-lrt'])
    elf=run('arm-elf',['wsl.exe','-d','Ubuntu-24.04','--exec',lp(tool/'arm-linux-gnueabihf-readelf'),'-h','-A','-l','-d','-V',lp(binary)]);assert 'ELF32' in elf and 'VFP registers' in elf
    n=np.arange(1024);rng=np.random.default_rng(43);vectors={'positive_tone':np.rint(700*np.exp(2j*np.pi*32*n/1024)),'negative_tone':np.rint(500*np.exp(-2j*np.pi*64*n/1024)),'off_bin':np.rint(600*np.exp(2j*np.pi*100.3*n/1024)),'dc':np.full(1024,100+20j),'zero':np.zeros(1024,dtype=complex),'random':rng.integers(-2048,2048,1024)+1j*rng.integers(-2048,2048,1024),'impulse':np.zeros(1024,dtype=complex)};vectors['impulse'][512]=1000+300j
    checks=[]
    for name,x in vectors.items():
        file=bundle/'inputs'/(name+'.iq');file.write_bytes(np.column_stack((x.real,x.imag)).astype('<i2').tobytes());dest=out/(name+'-host');run(name,[str(host),str(file),str(dest),'30720000']);checks.append({'name':name,**verify(file,dest)})
    bad=out/'bad.iq';bad.write_bytes(b'123');r=subprocess.run([str(host),str(bad),str(out/'bad-output'),'30720000']);assert r.returncode==2
    repeated=subprocess.run([str(host),str(bundle/'inputs/zero.iq'),str(out/'zero-host'),'30720000']);assert repeated.returncode==2
    native=ROOT/'results/p06-native-rx-20261011T053133Z';nr=json.loads((native/'report.json').read_text());nb=native/nr['prefix']/'bin/arm-rx-probe';assert hashlib.sha256(nb.read_bytes()).hexdigest()==nr['binary_sha256'];(bundle/'bin/arm-rx-probe').write_bytes(nb.read_bytes());(bundle/'arm_rx_probe.c').write_bytes((ROOT/'embedded/arm_rx_probe/arm_rx_probe.c').read_bytes());(bundle/source.name).write_bytes(source.read_bytes())
    script=['#!/bin/sh','set -eu','cd "$(dirname "$0")"','test ! -e outputs','sha256sum -c SHA256SUMS','mkdir outputs','uname -a > outputs/uname.txt']
    for name in vectors:script.append(f'./bin/arm-spectrum inputs/{name}.iq outputs/{name} 30720000')
    script+=['./bin/arm-rx-probe outputs > outputs/run.txt','cat outputs/run.txt']
    for session in [1,2]:script += [f'grep -qx "adc_sampling_frequency=30720000" outputs/session-{session}.before.txt',f'grep -qx "adc_sampling_frequency=30720000" outputs/session-{session}.after.txt',f'./bin/arm-spectrum outputs/session-{session}.iq outputs/rx-spectrum-{session} 30720000']
    script.append('echo ARM_BOUNDED_RX_SOFTWARE_SPECTRUM_DONE');(bundle/'run.sh').write_text('\n'.join(script)+'\n',newline='\n')
    (bundle/'SHA256SUMS').write_text('\n'.join(hashlib.sha256(p.read_bytes()).hexdigest()+'  '+p.relative_to(bundle).as_posix() for p in sorted(bundle.rglob('*')) if p.is_file())+'\n',newline='\n')
    archive=out/(prefix+'.tar')
    with tarfile.open(archive,'w') as tar:
        for p in sorted(bundle.rglob('*')):
            if p.is_file():
                info=tar.gettarinfo(str(p),arcname=prefix+'/'+p.relative_to(bundle).as_posix());info.mode=0o755 if p.parent.name=='bin' else 0o644
                with p.open('rb') as f:tar.addfile(info,f)
    report={'status':'host_C_FFT_and_ROI_passed_ARM_pending','prefix':prefix,'archive':str(archive),'sha256':hashlib.sha256(archive.read_bytes()).hexdigest(),'host_checks':checks,'FFT_length':1024,'algorithm':'radix2 FP64 software FFT','periodic_Hann':True,'DC_removed':False,'PSD_tolerance':{'relative':1e-10,'absolute':1e-12},'ROI_edge_absolute_tolerance_hz':1e-6,'known_cases':list(vectors),'new_RX_frames':36,'RF_writes':False,'AI':'not_connected','FIR':'not_connected; coefficients have incompatible Fs','FPGA':'not_implemented','partial_file_and_overwrite_rejected':True}
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report))
if __name__=='__main__':main()
