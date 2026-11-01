"""P80 full checks with batched RX reads and prompt-driven serial wake-up.

No cached boot/AI authorization and no reduced SHA/RF/kernel/ownership checks.
The temporary shell helper only reads files; P76 firmware remains unchanged.
"""
from contextlib import contextmanager,ExitStack
import base64,gzip,json,re,time,uuid
import board_control as control
from p201_usb_network import PanelController
from p46_console import Console
from p35_once_merged_trial import AuditPort
from rfsig.board_session import WORK,boot_uuid,classify_rx,one_json
from p35_uart_files import upload
from p52_ram import board_ram_tmp

class PromptConsole(Console):
    def shell(self):
        # A verified prompt ends the wait immediately. No fixed 2s idle delay.
        prompt=r'(?:^|\n)[^\r\n]*#\s*$'
        login=r'(?:login:|Password:)\s*$'
        passive=self.read(.03)
        self.port.write(b'\r')
        answer=passive+self.read(2,'(?:'+prompt+'|'+login+')')
        self.record['stages'].append(dict(port=self.name,stage='P80_prompt_wake',output=answer));self.save()
        if re.search(r'login:\s*$',answer):
            self.port.write(b'root\r');answer=self.read(3,'(?:'+prompt+'|'+login+')')
            if re.search(r'Password:\s*$',answer,re.I):
                self.port.write(b'analog\r');answer=self.read(3,prompt)
            self.record['stages'].append(dict(port=self.name,stage='P80_login_result',output=answer));self.save()
        if not re.search(prompt,answer,re.M):raise RuntimeError('RX root prompt not established')

def decode_snapshot(output,profile,identity):
    lines=[s.strip() for s in output.splitlines() if s.strip() and not s.startswith('__P46_')]
    if not lines or any(not re.fullmatch(r'[A-Za-z0-9+/]+={0,2}',s) for s in lines):
        raise ValueError('Malformed compressed snapshot frame')
    data=gzip.decompress(base64.b64decode(''.join(lines),validate=True))
    if len(data)>512*1024:raise ValueError('Snapshot exceeds bound')
    parts=data.split(b'\0')
    if parts[-1]!=b'' or len(parts[:-1])%2:raise ValueError('Invalid snapshot field delimiters')
    values={}
    for index in range(0,len(parts)-1,2):
        key=parts[index].decode('ascii');value=parts[index+1].decode('ascii',errors='replace')
        if key in values:raise ValueError('Duplicate snapshot field: '+key)
        values[key]=value
    required={'schema','complete','boot_before','boot_after','taint','names','rx_buffer','tx_buffer',
              'selected_wrapper_sha256','init_boot_marker','exit_code','owned_pid','owned_timeout_argv',
              'progress','later_progress','ai','summary','kernel_tail'}
    required.update('rf_'+x for x in control.RF_EXPECTED)
    required.update('scan_'+str(i) for i in range(4))
    required.update('sha_'+x for x in profile['installed_files_sha256'])
    if set(values)!=required or values['schema']!='rfsig.rx_control_snapshot.v1' or values['complete']!='yes':
        raise ValueError('Incomplete/unknown RX snapshot fields')
    boot=boot_uuid(values['boot_before'])
    if values['boot_after']!=boot:raise ValueError('Boot changed during snapshot')
    info=dict(identity=identity,boot_id=boot,taint=values['taint'],
              IIO_names=control.parse_names(values['names']),RX_buffer=values['rx_buffer'],TX_buffer=values['tx_buffer'],
              RF={x:values['rf_'+x] for x in control.RF_EXPECTED},kernel_tail=values['kernel_tail'],
              RX_scans=[values['scan_'+str(i)] for i in range(4)],
              profile_hashes={x:values['sha_'+x] for x in profile['installed_files_sha256']},
              selected_wrapper_sha256=values['selected_wrapper_sha256'],
              init_boot_marker=values['init_boot_marker'] or None,exit_code=values['exit_code'] or None,
              owned_pid=values['owned_pid'] or None,
              owned_timeout_argv=values['owned_timeout_argv'].splitlines(),
              progress=json.loads(values['progress']) if values['progress'] else None,
              later_progress=json.loads(values['later_progress']) if values['later_progress'] else None,
              AI=json.loads(values['ai']) if values['ai'] else None,
              summary=json.loads(values['summary']) if values['summary'] else None)
    info['critical_kernel_fault']=bool(re.search(control.CRITICAL_KERNEL,info['kernel_tail']))
    info['RF_matches']=info['RF']==control.RF_EXPECTED
    info['profile_verified']=(info['profile_hashes']==profile['installed_files_sha256'] and
                              info['selected_wrapper_sha256']==profile['installed_files_sha256']['boot'])
    info['owned_timeout_pid']=int(info['owned_pid']) if str(info['owned_pid']).isdigit() else None
    info['progress_advancing']=False
    return info

class FastPanelController(PanelController):
    @contextmanager
    def session(self):
        """Reuse exclusively owned handles only within this single action.

        Every inspect still re-reads complete boot/RF/SHA/AI/ownership data.
        No authorization state is cached between APPLY and START.
        """
        if getattr(self,'_handle_scope',None) is not None:raise RuntimeError('Nested fast control scope')
        self._handle_scope=ExitStack();self._handles={}
        try:yield
        finally:
            try:self._handle_scope.close()
            finally:self._handle_scope=None;self._handles={}

    @contextmanager
    def board(self,role):
        scope=getattr(self,'_handle_scope',None)
        if scope is not None:
            if role not in self._handles:self._handles[role]=scope.enter_context(self._uncached_board(role))
            yield self._handles[role]
            return
        with self._uncached_board(role) as value:yield value

    @contextmanager
    def _uncached_board(self,role):
        if role!='RX':
            with super().board(role) as value:yield value
            return
        folder=self.out/('RX-fast-'+uuid.uuid4().hex[:8]);folder.mkdir()
        b=None;tty_saved=False
        try:
            b=PromptConsole(self.ports[role],self.record,self.save);b.port=AuditPort(b.port,folder);b.shell()
            identity=b.command('uname -a')
            if 'Zynq-Tronlong' not in identity:raise ValueError('Unexpected RX Linux identity')
            b.command('p59_prompt=$PS1');b.command('p59_tty=$(stty -g)');tty_saved=True
            b.command("PS1=''");b.command('stty -echo')
            yield b,identity
        finally:
            if b:
                if tty_saved:
                    try:b.command('stty "$p59_tty"');b.command('PS1=$p59_prompt')
                    except Exception as error:self.record.setdefault('TTY_restore_errors',[]).append(repr(error))
                b.close()
            self.save()

    def inspect(self,role,b,identity):
        if role!='RX':return super().inspect(role,b,identity)
        begin=time.monotonic()
        template=control.ROOT/'board/rx-control-snapshot.sh';payload=template.read_bytes();digest=control.sha(template)
        if b'\r' in payload:raise ValueError('RX helper requires LF')
        names=list(self.profile['installed_files_sha256'])
        if any(x not in ('original','monitor','control','run','bringup','boot','previous-boot') for x in names):
            raise ValueError('Unsupported verified profile file list')
        directory='/tmp/p35-p80-'+digest[:12];remote=directory+'/snapshot.sh'
        b.command('z='+directory);b.command('mkdir -p $z');b.command('a=$z/snapshot.sh')
        present=b.command('if test -e $a;then echo __EXISTS__;fi')
        if '__EXISTS__' not in present:
            self.record['snapshot_RAM_tmp']=board_ram_tmp(b)
            # TLZ7xH provides base64 -d, whereas P201 supplies uudecode.
            # Reuse the previously audited TLZ7xH uploader with its prompt.
            b.command("PS1='# '")
            try:uploaded=upload(b,remote,payload)
            finally:b.command("PS1=''");b.command('stty -echo')
            self.record.setdefault('snapshot_uploads',[]).append(dict(path=remote,sha256=uploaded))
        if self.digest(b,remote)!=digest:raise ValueError('RX helper SHA changed')
        (self.out/'rx-control-snapshot.sh').write_bytes(payload)
        b.command('a='+remote);b.command('d='+self.profile['installed_directory']);b.command('w='+WORK)
        b.command("k='"+' '.join(names)+"'")
        output=b.command('sh $a $d $w $k | gzip -1 | base64',timeout=10)
        info=decode_snapshot(output,self.profile,identity)
        # Preserve the original two-read progress proof, but overlap its elapsed
        # time with all other reads and wait only when a new update is needed.
        before=info.get('progress') or {};later=info.get('later_progress') or {}
        until=time.monotonic()+1.5
        while (before.get('state')=='running' and later.get('state')=='running'
               and later.get('display_updates',0)<=before.get('display_updates',0) and time.monotonic()<until):
            time.sleep(.1)
            later=one_json(self.optional(b,WORK+'/data/progress.json'),optional=True) or {}
        info['later_progress']=later or None
        info['progress_advancing']=bool(before and later and later.get('display_updates',0)>before.get('display_updates',0))
        if b.value('/proc/sys/kernel/random/boot_id')!=info['boot_id']:raise ValueError('RX boot changed after snapshot')
        info['session_state']=classify_rx(info)
        self.record.setdefault('P80_snapshot_timings',[]).append(dict(seconds=time.monotonic()-begin,helper_sha256=digest,
                                                                    progress_proof=info['progress_advancing']))
        return info
