"""Run only the IO-free panel --selftest on identified P201, using RAM.

This does not deploy a screen driver, open the candidate screen UART, or run RF.
The existing debug console is used under the shared board-operation lock.
"""
import argparse
from datetime import datetime,timezone
import http.server
import importlib.util
import json
from pathlib import Path
import sys
import threading

ROOT=Path(__file__).resolve().parents[1]
sys.path[:0]=[str(ROOT/'src'),str(ROOT/'experiments')]
spec=importlib.util.spec_from_file_location('p63_control',ROOT/'host/board_control.py')
control=importlib.util.module_from_spec(spec);spec.loader.exec_module(control)

def main():
    ap=argparse.ArgumentParser();ap.add_argument('--build-report',type=Path,required=True);args=ap.parse_args()
    reportpath=args.build_report.resolve()
    if ROOT/'results' not in reportpath.parents: raise ValueError('Project results report required')
    report=json.loads(reportpath.read_text())
    if report['status'] not in ('passed_P63_offline_contract_and_ARM_build_not_hardware',
                               'passed_P63_native_wire_contract_and_ARM_build_not_hardware'):
        raise ValueError('Build not accepted')
    for name,wanted in report['inputs_sha256'].items():
        if control.sha(ROOT/name)!=wanted:raise ValueError('Build source changed: '+name)
    binary=ROOT/report['ARM_binary'];payload=binary.read_bytes()
    if control.sha(binary)!=report['ARM_sha256']:raise ValueError('ARM SHA mismatch')
    c=None
    with control.operation_lock():
        try:
            c=control.Controller('p63-logic-selftest');print(c.out,flush=True)
            c.record.update(build_report=str(reportpath.relative_to(ROOT)),build_sha256=control.sha(reportpath),
                            ARM_sha256=report['ARM_sha256'],screen_UART_opened=False,
                            debug_console_used=True,screen_driver_deployed=False)
            c.ports=control.discover_ports(c.record['ports'])
            class Handler(http.server.BaseHTTPRequestHandler):
                def do_GET(self):
                    if self.path!='/logic':self.send_error(404);return
                    self.send_response(200);self.send_header('Content-Length',str(len(payload)))
                    self.end_headers();self.wfile.write(payload)
                def log_message(self,*args):pass
            server=http.server.ThreadingHTTPServer(('192.168.2.10',0),Handler)
            worker=threading.Thread(target=server.serve_forever,daemon=True);worker.start()
            try:
                with c.board('TX') as (b,identity):
                    before=c.inspect('TX',b,identity);control.require_tx_off(before)
                    c.record['before_TX']=before;c.record['resolved_RAM_tmp']=control.board_ram_tmp(b)
                    directory='/tmp/p35-p63-'+datetime.now(timezone.utc).strftime('%H%M%S')
                    c.record['RAM_directory']=directory
                    b.command('d='+directory);b.command('test ! -e $d');b.command('mkdir $d')
                    b.command('u=$d/logic');b.command('h=http://192.168.2.10:'+str(server.server_port)+'/logic')
                    b.command('wget -q -T 10 -O $u $h',timeout=15)
                    if c.digest(b,directory+'/logic')!=report['ARM_sha256']:raise ValueError('Transferred SHA mismatch')
                    b.command('chmod 755 $u')
                    result=control.one_json(b.command('$u --selftest',timeout=5))
                    if result!=report['selftest']:raise ValueError('ARM/host logic selftests differ')
                    c.record['ARM_selftest']=result
                    after=c.inspect('TX',b,identity);control.require_tx_off(after)
                    if after['boot_id']!=before['boot_id'] or after['RF']!=before['RF']:raise ValueError('TX boot/RF changed')
                    c.record['after_TX']=after
            finally:
                server.shutdown();server.server_close();worker.join(2)
            c.record['status']='passed_P63_P201_RAM_logic_selftest_not_screen_UART_or_RF'
        except Exception as error:
            if c:c.record.update(status='failed_or_incomplete_P63_board_logic_selftest',error=repr(error))
            else:raise
        finally:
            if c:c.record['serial_closed']=True;c.save();print(c.record['status'],flush=True)
    return 0 if c.record['status'].startswith('passed_') else 1

if __name__=='__main__':raise SystemExit(main())
