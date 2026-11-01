"""Add two uniquely named SD experiment files; never replace boot selections.

Known original boot files are checked and backed up before a bounded rw mount.
Candidate is NOT selected automatically. Activation is a separate U-Boot step.
"""
from datetime import datetime,timezone
import http.server,importlib.util,json,shutil,sys,threading
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments')]
spec=importlib.util.spec_from_file_location('p64_stage_control',ROOT/'host/board_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)
READ=ROOT/'results/p59-p64-boot-inspect-20261025T054349692174Z/report.json'
BIT=ROOT/'results/p64-uart-bit-20261025T054717Z/report.json'
DT=ROOT/'results/p201-uart-candidate-20261024T023801Z/report.json'

def main():
    prior=json.loads(READ.read_text(encoding='utf-8'));bit=json.loads(BIT.read_text(encoding='utf-8'));dt=json.loads(DT.read_text(encoding='utf-8'))
    if prior['status']!='passed_P64_read_only_boot_media_and_clock_inspection' or not prior['temporary_SD_unmounted']:
        raise ValueError('Read-only card preflight incomplete')
    if bit['status']!='built_P64_UART_experiment_bitstream_not_deployed_or_released':raise ValueError('Build incomplete')
    if not dt['DTB_checks']['all_other_tree_properties_unchanged']:raise ValueError('DTB changed non-UART properties')
    paths={'p64-uart.bit':BIT.parent/'uart-experiment.bit','p64-uart.dtb':DT.parent/'candidate.dtb'}
    hashes={name:control.sha(p) for name,p in paths.items()}
    if hashes['p64-uart.bit']!=bit['bitstreams']['uart-experiment.bit']['sha256'] or hashes['p64-uart.dtb']!=dt['saved_files_sha256']['candidate.dtb']:
        raise ValueError('Payload changed')
    payload={name:p.read_bytes() for name,p in paths.items()};c=None
    with control.operation_lock():
        try:
            c=control.Controller('p64-stage-uart');print(c.out,flush=True)
            c.ports=control.discover_ports(c.record['ports'])
            c.record.update(added_SD_files=hashes,original_boot_files_changed=False,
                persistent_file_writes=True,
                automatic_selection_changed=False,PL_programmed=False,RF_transmissions=0,
                experiment_gate='UART-only one-shot trial, no whole-system timing/CDC/RF release')
            (c.out/'staging-script.py').write_bytes(Path(__file__).read_bytes())
            backup=c.out/'original-boot';backup.mkdir()
            for name,meta in prior['boot_files'].items():
                local=Path(meta['local_path'])
                if not meta['identical'] or control.sha(local)!=meta['SD_sha256']:raise ValueError('Backup provenance changed')
                shutil.copy2(local,backup/name)
            c.record['original_files_sha256']={name:meta['SD_sha256'] for name,meta in prior['boot_files'].items()}
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    name=self.path.removeprefix('/')
                    if name not in payload:self.send_error(404);return
                    self.send_response(200);self.send_header('Content-Length',str(len(payload[name])))
                    self.end_headers();self.wfile.write(payload[name])
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('192.168.2.10',0),Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                with c.board('TX') as (b,identity):
                    before=c.inspect('TX',b,identity);control.require_tx_off(before)
                    if before['boot_id']!=prior['after_TX']['boot_id']:raise ValueError('Preflight boot changed')
                    c.record['before_TX']=before;c.record['resolved_RAM_tmp']=control.board_ram_tmp(b)
                    directory='/tmp/p35-p64s-'+datetime.now(timezone.utc).strftime('%H%M%S')
                    b.command('r='+directory);b.command('test ! -e $r');b.command('mkdir $r')
                    for name in paths:
                        b.command('u=$r/'+name)
                        b.command('h=http://192.168.2.10:'+str(server.server_port)+'/'+name)
                        b.command('wget -q -T 10 -O $u $h',timeout=15)
                        if c.digest(b,directory+'/'+name)!=hashes[name]:raise ValueError('RAM transfer mismatch')
                    mount=directory+'/sd';b.command('d='+mount);b.command('mkdir $d')
                    b.command('! grep -q /dev/mmcblk0p1 /proc/mounts');mounted=False
                    try:
                        b.command('mount -t vfat -o rw,nosuid,nodev,noexec /dev/mmcblk0p1 $d');mounted=True
                        for name,wanted in c.record['original_files_sha256'].items():
                            if c.digest(b,mount+'/'+name)!=wanted:raise ValueError('Original SD file changed')
                        for name in paths:
                            b.command('n='+name);b.command('test ! -e $d/$n')
                        for name in paths:
                            b.command('n='+name);b.command('cp $r/$n $d/$n')
                            if c.digest(b,mount+'/'+name)!=hashes[name]:raise ValueError('SD copy mismatch')
                        b.command('sync')
                        for name,wanted in c.record['original_files_sha256'].items():
                            if c.digest(b,mount+'/'+name)!=wanted:raise ValueError('Original file mutated')
                    finally:
                        if mounted:b.command('sync');b.command('umount $d');c.record['SD_unmounted']=True
                    after=c.inspect('TX',b,identity);control.require_tx_off(after)
                    if before['boot_id']!=after['boot_id'] or before['RF']!=after['RF']:raise ValueError('Runtime changed')
                    c.record['after_TX']=after
            finally:server.shutdown();server.server_close();worker.join(2)
            c.record.update(status='passed_P64_two_SD_artifacts_staged_original_boot_unchanged_not_activated',
                bit_report=str(BIT.relative_to(ROOT)),bit_report_sha256=control.sha(BIT),
                DT_report=str(DT.relative_to(ROOT)),DT_report_sha256=control.sha(DT))
        except Exception as e:
            if c:c.record.update(status='failed_or_incomplete_P64_staging',error=repr(e))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1
if __name__=='__main__':raise SystemExit(main())
