"""Fetch exact current desktop init bytes and profiles; no target file writes."""
import base64,hashlib,json,re
from datetime import datetime,timezone
from p32_session import ROOT,BoardConsole
from p35_once_merged_trial import AuditPort
def main():
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p44-policy-inputs-%Y%m%dT%H%M%SZ');out.mkdir(exist_ok=False)
    r=dict(status='reading',stages=[],read_only=True)
    def save():(out/'report.json').write_text(json.dumps(r,indent=2)+'\n',encoding='utf-8')
    board=None;save()
    try:
        board=BoardConsole('COM8',r,save);board.port=AuditPort(board.port,out);board.shell()
        if board.value('/proc/sys/kernel/random/boot_id')!='f65eb741-88fc-44c1-9cb7-8fced08ac86a' or board.value('/proc/sys/kernel/tainted')!='0':raise ValueError('boot changed')
        board.command('f=/etc/init.d/xserver-nodm');text=board.command('sha256sum $f');digests=re.findall(r'^([0-9a-f]{64})\s+\S+\r?$',text,re.M)
        text=board.command('echo __B44__;base64 $f;echo __E44__')
        frame=re.search(r'(?m)^__B44__\r?\n([A-Za-z0-9+/=\r\n]+)^__E44__\r?$',text)
        if not frame or len(digests)!=1:raise ValueError('file framing failed')
        data=base64.b64decode(frame[1])
        if len(data)!=1107 or hashlib.sha256(data).hexdigest()!=digests[0]:raise ValueError('original init size/hash differs')
        (out/'xserver-original').write_bytes(data);r.update(original_sha256=digests[0],original_bytes=len(data),boot='f65eb741-88fc-44c1-9cb7-8fced08ac86a')
        r['profiles']={}
        for path in ('/etc/profile','/home/root/.profile','/etc/X11/Xsession.d/90xXWindowManager.sh'):
            board.command('f='+path);r['profiles'][path]=board.command('cat $f 2>&1 || true')
        r['status']='exact_X_init_archived_and_profiles_read'
    except Exception as e:r.update(status='failed',error=repr(e))
    finally:
        if board:board.close()
        r['serial_closed']=True;save();print(out);print(r['status'])
    return 0 if r['status'].startswith('exact_') else 1
if __name__=='__main__':raise SystemExit(main())
