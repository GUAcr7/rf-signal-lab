"""Read display blanking/desktop state after a physical black-screen report."""
from datetime import datetime,timezone
import hashlib,json
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort

def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-display-state-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='reading',stages=[],read_only=True,RF_changes=False,PL_changes=False)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a'):raise ValueError('wrong board')
        r['boot']=board.value('/proc/sys/kernel/random/boot_id');r['taint']=board.value('/proc/sys/kernel/tainted')
        if r['boot']!='f65eb741-88fc-44c1-9cb7-8fced08ac86a' or r['taint']!='0':raise ValueError('boot/taint changed; preserve state')
        r['reads']={}
        for key,cmd in [('processes','ps -ef'),('uptime','cat /proc/uptime'),('kernel_args','cat /proc/cmdline'),
            ('GPIO','cat /sys/kernel/debug/gpio'),('PWM','cat /sys/kernel/debug/pwm'),
            ('fb_blank','cat /sys/class/graphics/fb0/blank'),('consoleblank','cat /sys/module/kernel/parameters/consoleblank'),
            ('X_query','DISPLAY=:0 xset q'),('X_sockets','ls -la /tmp/.X11-unix'),
            ('Xsession','cat /etc/X11/Xsession'),('X_log_tail','tail -n 70 /var/log/Xorg.0.log')]:
            r['reads'][key]=board.command(cmd+' 2>&1 || true',timeout=12);save()
        if board.value('/proc/sys/kernel/random/boot_id')!=r['boot']:raise ValueError('boot changed')
        r['status']='read_only_display_blanking_state_collected'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('read_only_') else 1
if __name__=='__main__':raise SystemExit(main())
