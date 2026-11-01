"""Close only P35's interrupted decoder after host uploader has been stopped."""
from datetime import datetime,timezone
import hashlib,json,re
from p32_session import ROOT,BoardConsole

def main():
    source=ROOT/'results/p35-once-merged-20261020T162656Z/report.json'
    old=json.loads(source.read_text('utf-8'))
    if old['status']!='uploading_independent_artifacts' or any(old[k] for k in ['reboots_issued','PL_programming_attempts','overlay_apply_attempts']):
        raise RuntimeError('not the unarmed upload phase')
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-interrupt-close-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    report=dict(status='closing_own_decoder',stages=[],interrupted_trial=str(source),
        reboot=False,PL_loaded=False,overlay_applied=False,reason='User requested summary before further work')
    (out/'trial-before.json').write_bytes(source.read_bytes())
    def save():(out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
    board=None
    try:
        board=BoardConsole('COM8',report,save)
        # This is the base64 decoder created by the stopped, unarmed uploader.
        board.port.write(b'\x03\r');board.read(.7)
        board.port.write(b'stty echo\r');board.read(.5)
        board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise RuntimeError('wrong receiver')
        report['boot_id']=board.value('/proc/sys/kernel/random/boot_id')
        if report['boot_id']!=old['expected_boot']:raise RuntimeError('boot changed')
        report['tainted']=board.value('/proc/sys/kernel/tainted')
        if report['tainted']!='0':raise RuntimeError('kernel tainted')
        board.command('/etc/rcS.d/S99board --check-rf')
        guard=hashlib.sha256((ROOT/'board/boot/S99board').read_bytes()).hexdigest()
        text=board.command('sha256sum /etc/rcS.d/S99board')
        if not re.search(r'^'+guard+r'\s',text,re.M):raise RuntimeError('startup guard changed')
        board.command('cd /lib/firmware')
        board.command('sha256sum display.bin system_wrapper.bin ad9361.bin')
        board.command('cd /sys/bus/iio/devices/iio:device2')
        report['buffer_enable']=board.value('buffer/enable')
        report['scan_enable']=[board.value(f'scan_elements/in_voltage{i}_en') for i in range(4)]
        if report['buffer_enable']!='0' or report['scan_enable']!=['0']*4:raise RuntimeError('RX not idle')
        report['status']='upload_interrupted_before_arm_current_RF_idle_guard_unchanged'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        if board:board.close()
        report['serial_closed']=True;save()
        if report['status'].startswith('upload_interrupted_'):
            old['status']='interrupted_during_upload_before_boot_or_PL_change'
            old['interruption_close_report']=str(out/'report.json')
            old['serial_closed']=True
            old['ended_utc']=datetime.now(timezone.utc).isoformat()
            source.write_text(json.dumps(old,indent=2)+'\n',encoding='utf-8')
        print(out);print(report['status'])
    return 0 if report['status'].startswith('upload_interrupted_') else 1

if __name__=='__main__':raise SystemExit(main())
