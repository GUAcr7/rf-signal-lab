"""Explicit P201 task transport over the existing USB network, never fallback.

Binding requires same-boot P201 model proof from the selected USB serial console
and a pinned SSH public host key. No PTY, shell job control or serial login is used
for actual jobs. Existing board_control.py remains on its selected USB console.
"""
from contextlib import contextmanager
from pathlib import Path
import hashlib,json,re,socket,time,uuid
import board_control as control
from p46_console import Console
from p35_once_merged_trial import AuditPort

ROOT=control.ROOT
BINDING=ROOT/'results/p79-usb-network-active.json'

def fingerprint(transport):
    return hashlib.sha256(transport.get_remote_server_key().asbytes()).hexdigest()

def connect(host):
    import paramiko
    transport=paramiko.Transport(socket.create_connection((host,22),timeout=3))
    try:
        transport.start_client(timeout=5)
        return transport
    except Exception:
        transport.close();raise

def authenticate(transport):
    # Existing board factory credential, same as the established serial login.
    # Never written to UART traces, records or command arguments.
    transport.auth_password('root','analog')
    if not transport.is_authenticated():raise ValueError('P201 SSH authentication failed')

class NetworkPort:
    def __init__(self,transport):
        self.transport=transport;self.channel=transport.open_session(timeout=5)
        self.channel.settimeout(.1);self.channel.exec_command('/bin/sh')
    @property
    def in_waiting(self):return 4096 if self.channel.recv_ready() else 0
    def write(self,data):
        self.channel.sendall(data.replace(b'\r',b'\n'));return len(data)
    def read(self,size):
        try:return self.channel.recv(size)
        except socket.timeout:return b''
    def close(self):
        try:self.channel.close()
        finally:self.transport.close()

class NetworkConsole(Console):
    def __init__(self,binding,record,save,folder):
        self.name='P201_USB_NETWORK';self.record=record;self.save=save
        t=connect(binding['host'])
        try:
            if fingerprint(t)!=binding['host_key_sha256']:raise ValueError('P201 SSH key changed')
            authenticate(t);self.port=AuditPort(NetworkPort(t),folder)
        except Exception:
            t.close();raise
    def shell(self):
        output=self.command('id -u')
        if not re.search(r'^0\r?$',output,re.M):raise ValueError('P201 root required')
    def upload(self,payload,destination):
        if not re.fullmatch(r'/tmp/p35-p59-\d{8}T\d{6}Z/[a-z0-9.-]+',destination):
            raise ValueError('Only this current RAM source-bank file can be uploaded')
        channel=self.port.wrapped.transport.open_session(timeout=5)
        try:
            channel.settimeout(5);channel.exec_command('cat >'+destination)
            channel.sendall(payload);channel.shutdown_write()
            if channel.recv_exit_status()!=0:raise ValueError('RAM upload failed')
        finally:channel.close()
        return dict(transport='explicit_pinned_USB_network',payload_bytes=len(payload),
                    payload_sha256=hashlib.sha256(payload).hexdigest(),remote_SHA_verified_by_this_function=False)

def load_binding():
    pointer=json.loads(BINDING.read_text('utf-8'));path=ROOT/pointer['report']
    if control.sha(path)!=pointer['sha256']:raise ValueError('USB network binding changed')
    proof=json.loads(path.read_text('utf-8'))
    if proof.get('status')!='passed_P79_USB_serial_and_network_same_P201_boot':
        raise ValueError('Verified USB network binding required')
    return proof['binding']

class PanelController(control.Controller):
    @contextmanager
    def board(self,role):
        if role!='TX':
            with super().board(role) as value:yield value
            return
        binding=load_binding();b=None
        folder=self.out/('TX-network-'+uuid.uuid4().hex[:8]);folder.mkdir()
        self.record['TX_job_transport']='explicit_USB_network_no_PTY'
        self.record['TX_network_binding']=binding
        try:
            b=NetworkConsole(binding,self.record,self.save,folder);b.shell()
            identity=b.command('uname -a')
            model=b.command('cat /sys/firmware/devicetree/base/model')
            if 'Linux pzp201' not in identity or 'PUZHI PZSDR P201' not in model:
                raise ValueError('Unexpected network board identity')
            if b.value('/proc/sys/kernel/random/boot_id')!=binding['boot_id']:
                raise ValueError('P201 rebooted; rebind via USB console before RF')
            yield b,identity
        finally:
            if b:b.close()
            self.save()
