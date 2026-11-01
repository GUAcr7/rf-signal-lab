"""Wake the existing X/DRM display through xset, preserving drivers and RF."""
from datetime import datetime,timezone
import json,re
from pathlib import Path
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-wake-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='preflight',stages=[],RF_changes=False,PL_changes=False,driver_unbinds=False,desktop_settings_changed=True)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save();(out/'executed.py').write_bytes(Path(__file__).read_bytes())
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if 'Zynq-Tronlong' not in board.command('uname -a') or board.value('/proc/sys/kernel/random/boot_id')!='f65eb741-88fc-44c1-9cb7-8fced08ac86a' or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('identity changed')
        r['X_before']=board.command('DISPLAY=:0 xset q');r['PWM_before']=board.command('cat /sys/kernel/debug/pwm');save()
        if 'Monitor is Off' not in r['X_before']:raise ValueError('DPMS-off diagnosis not present')
        board.command('DISPLAY=:0 xset dpms force on')
        board.command('DISPLAY=:0 xset -dpms');board.command('DISPLAY=:0 xset s off')
        r['X_after']=board.command('DISPLAY=:0 xset q');r['PWM_after']=board.command('cat /sys/kernel/debug/pwm')
        if 'DPMS is Disabled' not in r['X_after'] or not re.search(r'pwm-2.*requested enabled.*duty: 50000 ns',r['PWM_after']):raise ValueError('backlight did not resume')
        r['files']={}
        for path in ('/etc/init.d/xserver-nodm','/etc/X11/Xsession.d','/etc/X11/Xsession-gpe.d'):
            board.command('f='+path);r['files'][path]=board.command('ls -la $f;test -f $f && cat $f;true',timeout=12)
        r['status']='DPMS_woken_disabled_screen_saver_off_PWM2_enabled'
    except Exception as e:r.update(status='failed_or_unconfirmed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('DPMS_') else 1
if __name__=='__main__':raise SystemExit(main())
