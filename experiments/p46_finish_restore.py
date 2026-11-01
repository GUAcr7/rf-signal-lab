"""Finish the SHA-verified P201 transfer using its separate gzip/tar tools."""
import gzip,hashlib,json,re
from datetime import datetime,timezone
from pathlib import Path
from p32_session import ROOT
from p46_console import Console
from p35_once_merged_trial import AuditPort

def sha(b):return hashlib.sha256(b).hexdigest()
def main():
    prior=ROOT/'results/p46-restored-20261022T113416Z/report.json';old=json.loads(prior.read_text('utf-8'))
    source=Path(old['source_report']);original=json.loads(source.read_text('utf-8'));payload=(source.parent/'pkg.gz').read_bytes()
    if sha(source.read_bytes())!=old['source_report_sha256'] or sha(payload)!=original['archive_sha256'] or '__UU_DONE__:0' not in old['decoder_tail']:raise ValueError('verified transfer required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p46-ready-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r={k:v for k,v in old.items() if k in ('remote_directory','expected_boot','RX_expected_boot','source_report','source_report_sha256','files_sha256','references','source_peak_component_counts')}
    r.update(status='checking_archive',stages=[],RF_operations=False,RF_attribute_writes=False,PL_changes=False,reused_transfer_report=str(prior),reused_transfer_sha256=sha(prior.read_bytes()))
    (out/'executed.py').write_bytes(Path(__file__).read_bytes())
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    b=None;save()
    def digest(path):
        b.command('f='+path);vals=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $f'),re.M)
        if len(vals)!=1:raise ValueError('hash ambiguous')
        return vals[0]
    try:
        b=Console('COM9',r,save);b.shell();b.port=AuditPort(b.port,out)
        if b.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0' or 'Linux pzp201' not in b.command('uname -a'):raise ValueError('identity differs')
        b.command('d='+r['remote_directory']);r['tools']=b.command('command -v gzip gunzip zcat tar || true')
        if digest(r['remote_directory']+'/pkg.gz')!=sha(payload):raise ValueError('board archive differs')
        b.command('command -v gzip');b.command('test ! -e $d/pkg.tar');b.command('gzip -dc $d/pkg.gz >$d/pkg.tar',timeout=20)
        if digest(r['remote_directory']+'/pkg.tar')!=sha(gzip.decompress(payload)):raise ValueError('uncompressed archive differs')
        b.command('tar -xf $d/pkg.tar -C $d');b.command('chmod 755 $d/guard');b.command('cd $d');b.command('sha256sum -c sums')
        for name,value in r['files_sha256'].items():
            if digest(r['remote_directory']+'/'+name)!=value:raise ValueError('board file differs '+name)
        r['inspect']=b.command('./guard --inspect',timeout=15)
        for key,value in [('tx0_sampling_frequency','30720000'),('tx0_hardwaregain','-10.000000 dB'),('tx0_rf_bandwidth','18000000'),('tx0_rf_port_select','A'),('tx_lo','2450000000'),('TX_DMA_sampling_frequency','30720000')]:
            if key+'='+value not in r['inspect']:raise ValueError('TX config differs '+key)
        for i in range(8):
            if not re.search(r'^dds'+str(i)+r'_scale=0(?:\.0+)?\r?$',r['inspect'],re.M):raise ValueError('DDS scale not zero')
        r['checks']={}
        for name in ('tone','bpsk','qpsk','qam16'):
            b.command('h='+r['files_sha256'][name]);result=b.command('./guard --check '+name+' 131072 $h')
            if 'INPUT_CHECK_PASS samples=131072' not in result:raise ValueError('native source rejected')
            r['checks'][name]=result;save()
        r['status']='guard_and_peak256_sources_restored_inspected_checked_no_TX'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if b:b.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('guard_and_') else 1
if __name__=='__main__':raise SystemExit(main())
