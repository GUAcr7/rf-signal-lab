"""Validate sparse observer on full historical captures, including a bad control."""
from datetime import datetime,timezone
import json
import numpy as np
from p22_acquire_comparison import ROOT
from p26_audit_data import source
from p21_track_and_measure import moment_carrier
from rfsig.iq_io import load_iq_dma_s16
from rfsig.sparse_continuity import StridedReferenceMatcher
from rfsig.capture_continuity import assess_source_progress


def analyse(prefixes,matcher):
    rows=[]
    for index,prefix in enumerate(prefixes):
        hint=moment_carrier(prefix,30720000/8,2,50000,960000)
        try:
            fit=matcher.align(prefix,30720000,hint)
            rows.append({'window':index,'source_start':fit.source_start,'correlation':fit.correlation,
                         'nmse_db':fit.nmse_db,'carrier_hz':fit.frequency_hz})
        except ValueError as error:
            rows.append({'window':index,'source_start':None,'correlation':None,'error':str(error)})
    assessment=assess_source_progress([r['source_start'] for r in rows],[r['correlation'] for r in rows],65536,len(matcher.reference))
    return {'windows':rows,'assessment':assessment,'diagnostic_only':True,'complete_stream_saved':False}


def main():
    tx=source('bpsk')
    ref=tx.iq*np.exp(-2j*np.pi*960000*np.arange(len(tx.iq))/30720000)
    matcher=StridedReferenceMatcher(ref,8)
    full=json.loads((ROOT/'results/p26-independent-audit-20261018T122935Z/report.json').read_text('utf-8'))
    cases=[]
    for index in (3,4):
        old=full['buffer_progress'][index]
        iq=load_iq_dma_s16(ROOT/old['source'],channels=old['channels']).reshape(-1,65536)
        result=analyse(iq[:,:8192:8],matcher)
        result['original_full_capture']=old['source']
        result['full_capture_jump_count']=old['assessment']['detected_jump_count']
        if result['assessment']['detected_jump_count']!=result['full_capture_jump_count']:
            raise RuntimeError('sparse observer failed the original full-capture control')
        for actual,expected in zip(result['windows'],old['windows']):
            if actual['source_start'] is None or abs((actual['source_start']-expected['source_start']+65536)%131072-65536)>1:
                raise RuntimeError('sparse position differs from full-buffer alignment')
        cases.append(result)
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p27-observer-validation-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    (out/'report.json').write_text(json.dumps({'cases':cases,'status':'full_capture_control_reproduced'},indent=2)+'\n',encoding='utf-8')
    print([(c['assessment']['detected_jump_count'],c['assessment']['usable_windows']) for c in cases])
    print(out)


if __name__=='__main__':main()
