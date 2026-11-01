"""Serve exactly one SHA-checked source package over existing P201 USB network; no TX."""
import argparse,gzip,hashlib,http.server,json,re,threading
from datetime import datetime,timezone
from pathlib import Path
from p45_checkpoint import ROOT,read,write,sha,rel
from p46_restore_tx import validate_source_package
from p46_known_source import GUARD_SHA
from p46_console import Console
from p35_once_merged_trial import AuditPort

def main():
    p=argparse.ArgumentParser();p.add_argument('--source-report',required=True,type=Path);p.add_argument('--preflight',required=True,type=Path);args=p.parse_args()
    meta,payload,tar_sha=validate_source_package(args.source_report);fresh=read(args.preflight)
    if fresh['status']!='read_only_both_boards_identified_DMA_idle' or not fresh['serial_closed']:raise ValueError('idle dual preflight required')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p52-restored-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='restoring_no_TX',stages=[],expected_boot=fresh['boards']['COM9']['boot_id'],RX_expected_boot=fresh['boards']['COM8']['boot_id'],
        source_report=str(args.source_report.resolve()),source_report_sha256=sha(args.source_report),preflight=str(args.preflight.resolve()),preflight_sha256=sha(args.preflight),
        files_sha256=meta['files_sha256'],references=meta['references'],source_peak_component_counts=256,
        RF_operations=False,RF_attribute_writes=False,PL_changes=False,remote_directory='/tmp/p35-p52-'+out.name[-7:-1])
    def save():write(out/'report.json',r)
    def digest(b,path):
        b.command('v='+path);m=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',b.command('sha256sum $v'),re.M)
        if len(m)!=1:raise ValueError('hash ambiguity')
        return m[0]
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path!='/pkg.gz':self.send_error(404);return
            self.send_response(200);self.send_header('Content-Length',str(len(payload)));self.end_headers();self.wfile.write(payload)
        def log_message(self,*a):pass
    server=None;b=None;save()
    try:
        server=http.server.ThreadingHTTPServer(('192.168.2.10',0),Handler);threading.Thread(target=server.serve_forever,daemon=True).start()
        r['HTTP_port']=server.server_address[1];save()
        b=Console('COM9',r,save);b.shell();b.port=AuditPort(b.port,out)
        if 'Linux pzp201' not in b.command('uname -a') or b.value('/proc/sys/kernel/random/boot_id')!=r['expected_boot'] or b.value('/proc/sys/kernel/tainted')!='0':raise ValueError('TX identity changed')
        if 'arm-tx-source' in b.command('ps'):raise ValueError('TX already active')
        d=r['remote_directory'];b.command('mkdir '+d);b.command('d='+d);b.command('u=$d/pkg.gz')
        b.command('h=http://192.168.2.10:'+str(r['HTTP_port'])+'/pkg.gz')
        b.command('wget -q -T 10 -O $u $h',timeout=15)
        if digest(b,d+'/pkg.gz')!=meta['archive_sha256']:raise ValueError('network transfer SHA mismatch')
        b.command('gzip -dc $d/pkg.gz >$d/pkg.tar')
        if digest(b,d+'/pkg.tar')!=tar_sha:raise ValueError('tar SHA mismatch')
        b.command('tar -xf $d/pkg.tar -C $d');b.command('chmod 755 $d/guard');b.command('cd $d');b.command('sha256sum -c sums')
        for name,wanted in meta['files_sha256'].items():
            if digest(b,d+'/'+name)!=wanted:raise ValueError('extracted file SHA differs')
        r['inspect']=b.command('./guard --inspect',timeout=15)
        for key,val in [('tx0_sampling_frequency','30720000'),('tx0_hardwaregain','-10.000000 dB'),('tx0_rf_bandwidth','18000000'),('tx0_rf_port_select','A'),('tx_lo','2450000000'),('TX_DMA_sampling_frequency','30720000')]:
            if key+'='+val not in r['inspect']:raise ValueError('TX configuration differs '+key)
        for i in range(8):
            if not re.search(r'^dds'+str(i)+r'_scale=0(?:\.0+)?\r?$',r['inspect'],re.M):raise ValueError('DDS scale nonzero')
        for name in ('tone','bpsk','qpsk','qam16'):
            b.command('h='+meta['files_sha256'][name]);v=b.command('./guard --check '+name+' 131072 $h')
            if 'INPUT_CHECK_PASS samples=131072' not in v:raise ValueError('native source check failed')
        r['status']='guard_and_peak256_sources_restored_inspected_checked_no_TX'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if b:b.close()
        if server:server.shutdown();server.server_close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('guard_and_') else 1
if __name__=='__main__':raise SystemExit(main())
