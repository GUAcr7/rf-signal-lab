"""Actual C renderer/reference checks, without board access."""
import json
import sys
from pathlib import Path
import numpy as np
import pytest
from test_native_rx_full_p36 import ROOT, run, posix
sys.path.insert(0,str(ROOT/'experiments'))
from p67_build_dashboard import generate_dashboard

@pytest.fixture(scope='module')
def built(tmp_path_factory):
    out=tmp_path_factory.mktemp('p67-dashboard')
    frozen,monitor,core=generate_dashboard()
    (out/'test_monitor.c').write_text(monitor.replace('int main(int argc, char **argv) {','int candidate_main(int argc, char **argv) {'),encoding='utf-8')
    (out/'ai_impl.h').write_text(core,encoding='utf-8')
    for key,name in (('C','trained_cnn_infer.c'),('header','trained_model.h'),('taps','rf_frontend.h')):
        (out/name).write_bytes((ROOT/frozen['frozen_inputs'][key]['path']).read_bytes())
    for name in ('runtime_policy.h','telemetry.h'):
        (out/name).write_bytes((ROOT/'embedded/arm_live_panel_p56'/name).read_bytes())
    (out/'dashboard.h').write_bytes((ROOT/'embedded/arm_live_panel_p67/dashboard.h').read_bytes())
    harness='''#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=4)return 2;
    int16_t iq[65536*2];FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    if(fread(iq,1,sizeof iq,f)!=sizeof iq || fgetc(f)!=EOF)return 2;
    fclose(f);panel_sample_rate_hz=30720000;
    float window[FFT_N];double acc[FFT_N];struct metrics m={0};
    for(int n=0;n<FFT_N;n++)window[n]=.5f-.5f*(float)cos(2*M_PI*n/FFT_N);
    spectrum(iq,8192,2,8,0,window,acc,&m);
    for(int n=0;n<atoi(argv[3]);n++)p67_measure(iq,acc,(n+1)*7,n*.5);
    if(p67_evidence(argv[2],"running"))return 3;
    uint32_t *pixels=malloc((PANEL_W+16)*PANEL_H*4+64);if(!pixels)return 3;
    for(int n=0;n<(PANEL_W+16)*PANEL_H+16;n++)pixels[n]=0x12345678;
    fb=pixels;fb_stride_words=PANEL_W+16;
    p67_draw(acc,&m,2,8192,0,0,8);p56_line();
    for(int y=0;y<PANEL_H;y++)for(int x=PANEL_W;x<PANEL_W+16;x++)
        if(pixels[y*fb_stride_words+x]!=0x12345678)return 4;
    for(int n=0;n<16;n++)if(pixels[(PANEL_W+16)*PANEL_H+n]!=0x12345678)return 4;
    char path[2048];snprintf(path,sizeof path,"%s/render.raw",argv[2]);
    f=fopen(path,"wb");if(!f)return 3;
    for(int y=0;y<PANEL_H;y++)if(fwrite(fb+y*fb_stride_words,4,PANEL_W,f)!=PANEL_W)return 3;
    fclose(f);free(pixels);
    snprintf(path,sizeof path,"%s/power.bin",argv[2]);f=fopen(path,"wb");if(!f)return 3;
    if(fwrite(acc,sizeof(double),FFT_N,f)!=FFT_N)return 3;
    fclose(f);return 0;
}'''
    (out/'harness.c').write_text(harness,encoding='ascii')
    q=run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-pthread','-I',posix(ROOT/'embedded/vendor/libiio-v0.24'),posix(out/'harness.c'),'-o',posix(out/'harness'),'-lm','-ldl','-lrt'],timeout=120)
    assert q.returncode==0,q.stderr.decode()
    return out/'harness'

def invoke(built,tmp_path,x,rows=1):
    pair=np.column_stack((np.real(x),np.imag(x)))
    pair=np.rint(pair).clip(-2048,2047).astype('<i2')
    src=tmp_path/'iq.bin';src.write_bytes(pair.tobytes());dest=tmp_path/'output';dest.mkdir()
    q=run([posix(built),posix(src),posix(dest),str(rows)],timeout=25)
    assert q.returncode==0,q.stderr.decode()
    return json.loads((dest/'dashboard.json').read_text()),pair,dest

@pytest.mark.parametrize('kind',['zero','tone','offbin','noise','two_tones','negative_tone'])
def test_numerics_against_numpy_with_explicit_record_not_target_scope(built,tmp_path,kind):
    n=np.arange(65536);rng=np.random.default_rng(67)
    signals={
        'zero':np.zeros(65536),
        'tone':300*np.exp(2j*np.pi*32*n/1024),
        'offbin':300*np.exp(2j*np.pi*32.37*n/1024),
        'noise':rng.normal(0,60,65536)+1j*rng.normal(0,60,65536),
        'two_tones':150*(np.exp(2j*np.pi*32*n/1024)+np.exp(-2j*np.pi*64*n/1024)),
        'negative_tone':300*np.exp(-2j*np.pi*32*n/1024),
    }
    d,pair,out=invoke(built,tmp_path,signals[kind])
    x=pair[:8192,0].astype(float)+1j*pair[:8192,1]
    w=(.5-.5*np.cos(2*np.pi*np.arange(1024)/1024)).astype(np.float32).astype(float)
    power=np.mean(abs(np.fft.fft(x.reshape(8,1024)*w,axis=1))**2,axis=0)/(1024*np.sum(w*w))
    cpower=np.fromfile(out/'power.bin',dtype='<f8')
    np.testing.assert_allclose(cpower,power,rtol=3e-4,atol=.025)
    assert d['mean_i2_q2_counts_squared']==pytest.approx(np.mean(abs(x)**2),rel=1e-12)
    assert d['source_block_sequence']==7 and d['sample_rate_hz']==30720000
    assert d['AI_state']=='CALIBRATION_REQUIRED' and d['accepted_class']==-1
    assert not d['target_bandwidth_validated'] and not d['absolute_RF_power_calibrated']
    if kind=='zero':
        assert d['record_99_percent_width_hz'] is None and d['relative_power_db'] is None
    else:
        shifted=np.fft.fftshift(power);cumulative=np.r_[0,np.cumsum(shifted)]
        edges=(np.arange(1025)-512-.5)*30000
        lo,hi=np.interp(np.array([.005,.995])*cumulative[-1],cumulative,edges)
        assert d['record_99_percent_width_hz']==pytest.approx(hi-lo,abs=5)
        assert d['record_interval_midpoint_hz']==pytest.approx((hi+lo)/2,abs=5)
        assert d['relative_power_db']==0
    if kind=='noise':assert d['record_99_percent_width_hz']>29e6  # explicitly not target OBW
    assert (out/'render.raw').stat().st_size==800*480*4

def test_waterfall_ring_is_bounded_and_counted_as_snapshots(built,tmp_path):
    x=100*np.exp(2j*np.pi*32*np.arange(65536)/1024)
    d,_,_=invoke(built,tmp_path,x,rows=105)
    assert d['waterfall_rows']==d['waterfall_max_rows']==96
    assert d['source_block_sequence']==105*7
    assert d['waterfall_axis']=='displayed_snapshots_not_ADC_time'

def test_spectrum_history_does_not_autonormalize_each_row(built,tmp_path):
    x=300*np.exp(2j*np.pi*32*np.arange(65536)/1024)
    _,_,a=invoke(built,tmp_path,x)
    other=tmp_path/'other';other.mkdir();_,_,b=invoke(built,other,x/4)
    p1=np.fromfile(a/'render.raw',dtype='<u4').reshape(480,800)
    p2=np.fromfile(b/'render.raw',dtype='<u4').reshape(480,800)
    assert np.any(p1[412:414,48:432]!=p2[412:414,48:432])
