"""Actual native ROI calculator compared to independent Python integration."""
import json
import numpy as np
import pytest
from test_native_rx_full_p36 import ROOT,run,posix
from rfsig.bandwidth import occupied_bandwidth

@pytest.fixture(scope='module')
def probe(tmp_path_factory):
    out=tmp_path_factory.mktemp('p69-math')
    source='''#include <stdio.h>
#include <stdlib.h>
#include "'''+posix(ROOT/'embedded/arm_live_panel_p69/roi_math.h')+'''"
int main(int argc,char **argv) {
    if(argc!=5)return 2;
    double data[2048];FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    if(fread(data,sizeof(double),2048,f)!=2048)return 2;
    fclose(f);
    struct p69_result r=p69_compute(data,data+1024,1024,strtod(argv[2],NULL),2450000000,strtod(argv[3],NULL),atoi(argv[4]));
    printf("{\\"status\\":\\"%s\\",\\"center\\":%.17g,\\"width\\":%.17g,\\"power\\":%.17g,\\"background\\":%.17g,\\"rf\\":%.17g}\\n",p69_names[r.status],r.midpoint,r.width,r.power,r.background,r.rf);
    return 0;
}'''
    (out/'probe.c').write_text(source,encoding='ascii')
    q=run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',posix(out/'probe.c'),'-o',posix(out/'probe'),'-lm'])
    assert q.returncode==0,q.stderr.decode(errors='replace')
    return out/'probe'

def invoke(probe,tmp_path,p,b,center=994000,allowed=1,fs=30720000):
    path=tmp_path/'powers.bin';path.write_bytes(np.r_[p,b].astype('<f8').tobytes())
    q=run([posix(probe),posix(path),str(fs),str(center),str(allowed)])
    assert q.returncode==0,q.stderr.decode(errors='replace')
    return json.loads(q.stdout)

@pytest.mark.parametrize('center_bin,sigma',[(32,1),(32.37,3.7),(33.13,4.5),(30.6,2.1)])
def test_quantile_power_and_LO_sum_match_independent_python(probe,tmp_path,center_bin,sigma):
    f=np.fft.fftfreq(1024)*30720000
    p=500*np.exp(-.5*((f-center_bin*30000)/(sigma*30000))**2)+.01
    b=np.full(1024,.01);center=994000
    result=invoke(probe,tmp_path,p,b,center)
    gold=occupied_bandwidth(np.fft.fftshift(f),np.fft.fftshift(p)/30000,(center-600000,center+600000),rf_lo_hz=2450000000)
    assert result['status']=='VALID'
    assert result['center']==pytest.approx(gold.center_baseband_hz,abs=1e-7)
    assert result['width']==pytest.approx(gold.bandwidth_hz,abs=1e-7)
    assert result['rf']==pytest.approx(gold.center_rf_hz,abs=1e-6)
    assert result['power']==pytest.approx(gold.observed_region_power,rel=1e-12)

@pytest.mark.parametrize('case,status',[
    ('zero','BELOW_BACKGROUND_GATE'),('background','BELOW_BACKGROUND_GATE'),
    ('no_background','BELOW_BACKGROUND_GATE'),('not_allowed','NO_USABLE_SIGNAL'),
    ('outside','DOMINANT_PEAK_OUTSIDE_ROI'),('broad','ROI_EDGE_OR_BROAD'),
    ('edge','ROI_EDGE_OR_BROAD'),('nan','INVALID_INPUT'),('negative','INVALID_INPUT'),
    ('bad_rate','INVALID_INPUT'),('wrapping','INVALID_INPUT'),
])
def test_invalid_measurements_never_become_valid(probe,tmp_path,case,status):
    f=np.fft.fftfreq(1024)*30720000;b=np.full(1024,.01)
    p=500*np.exp(-.5*((f-994000)/80000)**2)+.01
    allowed=1;center=994000;fs=30720000
    if case=='zero':p[:]=0
    elif case=='background':p=b.copy()
    elif case=='no_background':b[:]=0
    elif case=='not_allowed':allowed=0
    elif case=='outside':p[0]=10000
    elif case=='broad':p=np.where(abs(f-center)<600000,100,.01)
    elif case=='edge':p=500*np.exp(-.5*((f-(center+570000))/10000)**2)+.01
    elif case=='nan':p[0]=np.nan
    elif case=='negative':p[0]=-1
    elif case=='bad_rate':fs=15360000
    elif case=='wrapping':center=15360000
    result=invoke(probe,tmp_path,p,b,center,allowed,fs)
    assert result['status']==status
    assert result['center']==result['width']==result['rf']==0
