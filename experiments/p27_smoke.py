"""Upload checked receiver binary and run 16-buffer receive-only smoke test."""
from datetime import datetime,timezone
import hashlib,json,re,subprocess,sys
from pathlib import Path
from p22_acquire_comparison import ROOT,Console


def main():
    sys.stdout.reconfigure(encoding='utf-8')
    build=sorted(ROOT.glob('results/p27-native-build-*/report.json'))[-1]
    manifest=json.loads(build.read_text('utf-8'))
    binary=Path(manifest['binary'])
    if manifest['status']!='cross_compile_verified' or hashlib.sha256(binary.read_bytes()).hexdigest()!=manifest['binary_sha256']:
        raise RuntimeError('native build not accepted')
    stamp=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
    out=ROOT/'results'/('p27-smoke-'+stamp);out.mkdir(exist_ok=False)
    remote='/tmp/p27-rx-diag-'+stamp[9:15]
    directory='/tmp/p27-smoke-'+stamp[9:15]
    report={'stages':[],'status':'preflight','build':str(build),'remote_binary':remote,'output_directory':directory,'RF_transmitted':False}
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=Console('COM8',report,save)
    try:
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong receiver')
        board.command('test ! -e '+remote)
        board.command('test ! -e '+directory)
    finally:board.close();save()
    uploaded=subprocess.run([sys.executable,str(ROOT/'experiments/p15_serial_send.py'),'--port','COM8','--source',str(binary),'--remote',remote],capture_output=True,timeout=60)
    (out/'upload.stdout').write_bytes(uploaded.stdout);(out/'upload.stderr').write_bytes(uploaded.stderr)
    if uploaded.returncode:raise RuntimeError('upload failed')
    board=Console('COM8',report,save)
    try:
        board.command('p='+remote)
        if manifest['binary_sha256'] not in board.command('sha256sum $p'):raise RuntimeError('remote binary mismatch')
        board.command('chmod 755 $p')
        board.command('mkdir '+directory)
        result=board.command('$p '+directory+' 16',timeout=20)
        if 'SPARSE_RX_PASS blocks=16' not in result or 'SPARSE_RX_RELEASED completed=16 status=0' not in result:
            raise RuntimeError('native smoke acceptance missing')
        board.command('cd '+directory)
        meta=board.command('cat metadata.json')
        data=json.loads(re.search(r'^\{.*\}\r?$',meta,re.M)[0])
        if data['blocks']!=16 or not data['buffer_released'] or data['complete_stream_saved']:
            raise RuntimeError('native diagnostic contract invalid')
        report['native_metadata']=data
        board.command('sha256sum prefixes.bin')
        board.command('cat before.txt after.txt')
        report['status']='receiver_abi_layout_capture_and_release_verified'
        print(out)
    finally:board.close();save()


if __name__=='__main__':main()
