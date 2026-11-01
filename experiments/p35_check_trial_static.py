"""Offline-only gates for the one-shot trial; never construct a serial object."""
import ast
from datetime import datetime,timezone
import hashlib
import importlib.util
import json
from pathlib import Path
import subprocess

ROOT=Path(__file__).resolve().parents[1]

def main():
    path=ROOT/'experiments/p35_once_merged_trial.py'
    out=ROOT/'results'/datetime.now(timezone.utc).strftime('p35-once-static-%Y%m%dT%H%M%SZ')
    out.mkdir(exist_ok=False)
    source=path.read_text('utf-8')
    ast.parse(source)
    spec=importlib.util.spec_from_file_location('trial',path)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    report=dict(status='running',checks=[],board_operations=False,runtime_trial_executed=False,
        source_sha256=hashlib.sha256(path.read_bytes()).hexdigest())
    def check(name,condition):
        report['checks'].append(dict(name=name,passed=bool(condition)))
        if not condition:raise RuntimeError(name)
    try:
        boot='8033ec3f-0588-4e7a-8572-e440c547cf43'
        hold=module.render_hold('/etc/p35-guard-20261020T163000Z','a'*64,boot)
        rendered=out/'hold.rendered.sh';rendered.write_bytes(hold)
        check('no unresolved substitutions',b'@@' not in hold)
        check('fresh boot condition retained',b'"$CURRENT" != "$ARMED_BOOT"' in hold)
        check('guard restore precedes hold marker',hold.index(b'mv "$RESTORE" "$INSTALL"')<hold.index(b'> /run/p35-hold-boot'))
        check('fan retained',b'/sys/class/gpio/gpio914/value' in hold)
        check('no configuration in hold',b'fpga_manager' not in hold and b'overlays/' not in hold and b'echo rf' not in hold)
        p=rendered.as_posix();p='/mnt/'+p[0].lower()+p[2:]
        result=subprocess.run(['wsl.exe','--exec','/bin/sh','-n',p],capture_output=True,timeout=60)
        (out/'sh-n.stdout').write_bytes(result.stdout);(out/'sh-n.stderr').write_bytes(result.stderr)
        check('POSIX shell syntax',result.returncode==0)
        for label,backup,digest,bid in [('backup','/etc/S99board','a'*64,boot),('SHA','/etc/p35-guard-20261020T163000Z','A'*64,boot),('boot','/etc/p35-guard-20261020T163000Z','a'*64,'bad')]:
            try:module.render_hold(backup,digest,bid)
            except ValueError:check('reject bad '+label,True)
            else:check('reject bad '+label,False)
        header='clock enable_cnt prepare_cnt rate accuracy phase\n'
        check('clock column parsing',module.clock_rates(header+' fclk0 1 1 99999999 0 0\n')['fclk0']==99999999)
        for label,text in [('unknown','unknown 1 1 100 0 0\n'),('duplicate',header+'fclk0 1 1 100 0 0\nfclk0 1 1 100 0 0\n')]:
            try:module.clock_rates(text)
            except RuntimeError:check('reject '+label+' clock contract',True)
            else:check('reject '+label+' clock contract',False)
        invalid=out/'rejected-input.json';invalid.write_text('{}\n',encoding='ascii')
        try:module.validate_inputs(invalid,invalid)
        except RuntimeError:check('reject unvalidated input reports before UART',True)
        else:check('reject unvalidated input reports before UART',False)
        class FakePort:
            def __init__(self):self.sent=[];self.chunks=[b'Password:',b'\r\nUART\x00bytes\xff']
            def read(self,*_):return self.chunks.pop(0)
            def write(self,data):self.sent.append(data);return len(data)
            def close(self):pass
        fake=FakePort();audit=module.AuditPort(fake,out)
        audit.read(9);audit.write(b'test-password\r');audit.read(99);audit.write(b'echo hello\r');audit.close()
        check('RX bytes retained exactly',(out/'uart.rx.bin').read_bytes()==b'Password:\r\nUART\x00bytes\xff')
        check('password redacted from TX evidence',b'test-password' not in (out/'uart.tx.bin').read_bytes() and b'<credential redacted>' in (out/'uart.tx.bin').read_bytes())
        check('wire write unchanged by redaction',fake.sent==[b'test-password\r',b'echo hello\r'])
        check('no hot removal code', 'rmdir' not in source and 'unbind' not in source)
        check('single PL attempt declaration',source.count("report['PL_programming_attempts']=1")==1)
        check('single overlay attempt declaration',source.count("report['overlay_apply_attempts']=1")==1)
        commands=['p=/lib/firmware/p35-merged-20261020T163000Z.dtbo','echo p35-ttl-20261020T163000Z.bin > $f/firmware',
            'a=/sys/devices/system/clocksource/clocksource0/current_clocksource']
        check('long generated command boundaries',all(len(c)<=72 for c in commands))
        constants=[node.args[0].value for node in ast.walk(ast.parse(source)) if isinstance(node,ast.Call) and isinstance(node.func,ast.Attribute) and node.func.attr=='command' and node.args and isinstance(node.args[0],ast.Constant) and isinstance(node.args[0].value,str)]
        check('literal command boundaries',all(len(c)<=72 and '\n' not in c for c in constants))
        report['status']='passed_offline_static_and_helper_checks_not_runtime_test'
    except Exception as exc:report.update(status='failed',error=repr(exc))
    finally:
        (out/'trial.py').write_bytes(path.read_bytes())
        (out/'static-checker.py').write_bytes(Path(__file__).read_bytes())
        (out/'report.json').write_text(json.dumps(report,indent=2)+'\n',encoding='utf-8')
        print(out);print(report['status'])
    return 0 if report['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
