"""Bounded known-source RX diagnostic with preallocated prefix storage, no RF writes."""
from datetime import datetime,timezone
import hashlib,json,re,sys
from p22_acquire_comparison import ROOT,Console
from p26_retrieve_chunks import ChunkConsole


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    smoke_path=sorted(ROOT.glob('results/p27-smoke-*/report.json'))[-1]
    smoke=json.loads(smoke_path.read_text('utf-8'))
    if smoke['status']!='receiver_abi_layout_capture_and_release_verified':raise RuntimeError('native receiver not tested')
    build=json.loads(open(smoke['build'],encoding='utf-8').read())
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p27-acquisition-'+stamp);out.mkdir(exist_ok=False)
    report={'stages':[],'status':'preflight','RF_attributes_written':False,'rf_operations':False,
            'tx_duration_limit_s':30,'diagnostic_only':True,'complete_stream_saved':False,'board_files':[],
            'smoke':str(smoke_path),'build':smoke['build'],'sample_rate_hz':30720000}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    tx=rx=None;started=finished=False
    save()
    try:
        tx=Console('COM9',report,save);rx=ChunkConsole('COM8',report,save)
        if 'Linux pzp201' not in tx.command('uname -a') or 'Zynq-Tronlong' not in rx.command('uname -a'):
            raise RuntimeError('unexpected board identity')
        if any('arm-tx-source --run' in row and 'grep' not in row for row in tx.command('ps').splitlines()):
            raise RuntimeError('TX already active')
        bootid=re.search(r'[0-9a-f]{8}-(?:[0-9a-f]{4}-){3}[0-9a-f]{12}',tx.command('cat /proc/sys/kernel/random/boot_id'))[0]
        tx.command('cd /tmp/p12-source-stage-1018/stage')
        inspect=tx.command('./arm/arm-tx-source --inspect')
        for expected in ('tx0_sampling_frequency=30720000','tx_lo=2450000000','tx0_hardwaregain=-10.000000 dB','tx0_rf_bandwidth=18000000'):
            if expected not in inspect:raise RuntimeError('TX settings changed')
        tx.command('p=/tmp/p12-source-stage-mods1018/bundle/bpsk.iq16le')
        source_sha=hashlib.sha256((ROOT/'results/p21-mod-waveforms-20261017T122536Z/bundle/bpsk.iq16le').read_bytes()).hexdigest()
        if source_sha not in tx.command('sha256sum $p'):raise RuntimeError('source mismatch')
        tx.command('h='+source_sha);tx.command('b=boot-session:'+bootid)
        tx.command('n=131072; f=30720000; l=2450000000; w=18000000')
        rx.command('p='+smoke['remote_binary'])
        if build['binary_sha256'] not in rx.command('sha256sum $p'):raise RuntimeError('receiver binary mismatch')
        directory='/tmp/p27-run-'+stamp[9:15]
        rx.command('test ! -e '+directory);rx.command('mkdir '+directory)
        report['remote_directory']=directory
        # Native config guard refuses any drift from the reviewed RX profile.
        run='./arm/arm-tx-source --run $p $n $f $l $w -10 30 $b A $h RF_LINK_REVIEWED'
        started=True  # Even a start-banner timeout must wait for native cleanup.
        tx.port.write((run+'\recho __P27_TX_RC__:$?\r').encode())
        report['tx_start']=tx.read_until(r'CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=30',8)
        report['rf_operations']=True;save()
        result=rx.command('$p '+directory+' 512',timeout=20)
        if 'SPARSE_RX_PASS blocks=512' not in result or 'SPARSE_RX_RELEASED completed=512 status=0' not in result:
            raise RuntimeError('capture/release not accepted')
        rx.command('cd '+directory)
        metadata=rx.command('cat metadata.json',timeout=15)
        report['native_metadata']=json.loads(re.search(r'^\{.*\}\r?$',metadata,re.M)[0])
        rx.command('cat before.txt after.txt')
        filename='p27-'+stamp[9:15]+'-prefixes.bin'
        rx.command('test ! -e /tmp/'+filename)
        rx.command('cp prefixes.bin /tmp/'+filename)
        digest=re.search(r'^([0-9a-f]{64})\s',rx.command('sha256sum prefixes.bin'),re.M)[1]
        size=rx.command('wc -c prefixes.bin')
        if 512*1024*4 not in [int(word) for word in size.split() if word.isdigit()]:raise RuntimeError('prefix size mismatch')
        report['board_files']=[{'name':'prefixes512','path':'/tmp/'+filename,'expected_bytes':512*1024*4,
                                'sha256':digest,'channels':2,'diagnostic_only':True}]
        save()
        report['tx_end']=tx.read_until(r'^__P27_TX_RC__:[0-9]+\r?$',40)
        finished=True
        if 'TX_CLEANUP buffer_released=true rf_settings_written=false status=0' not in report['tx_end'] or not re.search(r'^__P27_TX_RC__:0\r?$',report['tx_end'],re.M):
            raise RuntimeError('TX cleanup not verified')
        report['status']='capture_and_tx_cleanup_verified'
        print(out)
    except Exception as error:
        report['status']='failed';report['error']=repr(error)
        if started and not finished:
            try:report['cleanup_after_error']=tx.read_until(r'^__P27_TX_RC__:[0-9]+\r?$',40)
            except Exception as failure:report['cleanup_error']=repr(failure)
        raise
    finally:
        if tx:tx.close()
        if rx:rx.close()
        save()


if __name__=='__main__':main()
