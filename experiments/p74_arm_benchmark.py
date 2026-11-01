"""Hash-checked RAM-only P74 ARM parity/latency; RF/DMA stay stopped.

This executes saved adapted frames, not a live receiver or independent AI test.
"""
import argparse, re, sys
from datetime import datetime, timezone
from pathlib import Path
import numpy as np
from p45_checkpoint import ROOT, read, write, sha, rel
sys.path.insert(0,str(ROOT/'host'))
from board_control import Controller, operation_lock
from rfsig.board_session import require_rx_control, require_tx_off
from p35_uart_files import upload
from p52_ram import board_ram_tmp


def main():
    ap=argparse.ArgumentParser();ap.add_argument('--native',type=Path,required=True)
    a=ap.parse_args();native=read(a.native)
    if native['status']!='passed_P74_native_host_Python_parity_ARM_crossbuild_pending_execution':
        raise ValueError('offline native parity required')
    for path, digest in native['inputs_sha256'].items():
        if sha(ROOT/path)!=digest:raise ValueError('native build input changed')
    binary=ROOT/native['ARM_binary']
    if sha(binary)!=native['ARM_binary_sha256']:raise ValueError('ARM binary changed')
    frozen_trial=read(ROOT/'results/p59-p73-native-events-20261026T092426541601Z/report.json')
    expected_boot=frozen_trial['after_RX']['boot_id']
    with operation_lock():
        c=Controller('p74-ARM-phase-parity');r=c.record
        (c.out/'executed_p74.py').write_bytes(Path(__file__).read_bytes())
        r.update(native=rel(a.native),native_sha256=sha(a.native),expected_RX_boot=expected_boot,
                 actual_RX_acquisition=False,live_panel_changed=False,classification_fix_deployed=False,
                 protocol=dict(events=['event-01','event-04','event-07','event-10'],
                               validation_indices=[0,6,12],benchmark_repeats=20,
                               latency_gate_max_three_frame_ms=200),checks=[],benchmarks=[])
        c.save()
        try:
            c.status();tx=r['boards']['TX'];rx=r['boards']['RX']
            require_tx_off(tx);require_rx_control(rx,running=False)
            if rx['boot_id']!=expected_boot:raise ValueError('RX rebooted; re-establish session first')
            with c.board('RX') as (b,identity):
                before=c.inspect('RX',b,identity)
                require_rx_control(before,running=False)
                process=b.command('ps -ef')
                if re.search(r'\bmonitor-arm\b|\bphase-ARM\b|/run/p42-\d+/monitor',process):
                    raise ValueError('another receiver or candidate process exists')
                r['RAM_tmp']=board_ram_tmp(b)
                remote='/tmp/p35-p74-'+datetime.now(timezone.utc).strftime('%H%M%S')
                r['stage']=remote;c.save();b.command('mkdir '+remote)
                b.command("PS1='# '")
                upload(b,remote+'/a',binary.read_bytes());b.command('stty -echo')
                b.command('chmod 755 '+remote+'/a');b.command('b='+remote+'/a');b.command('x='+remote+'/x')
                fixtures=[]
                val=next(v for v in native['checks'] if v['name']=='validation')
                val_bytes=(ROOT/val['path']).read_bytes()
                if sha(ROOT/val['path'])!=val['sha256']:raise ValueError('validation fixture changed')
                indices=[0,6,12]
                fixtures.append(dict(name='validation-one-per-class',raw=b''.join(val_bytes[k*8192:(k+1)*8192] for k in indices),
                    modes={mode:dict(expected_logits=[val['modes'][mode]['expected_logits'][k] for k in indices],
                                     predictions=[val['modes'][mode]['predictions'][k] for k in indices])
                           for mode in ('baseline','pool')}))
                for name in r['protocol']['events']:
                    fixture=next(v for v in native['checks'] if v['name']==name)
                    if sha(ROOT/fixture['path'])!=fixture['sha256']:raise ValueError('event fixture changed')
                    fixtures.append(dict(name=name,raw=(ROOT/fixture['path']).read_bytes(),modes=fixture['modes']))
                for fixture in fixtures:
                    # Separate small RAM files; old evidence is never overwritten.
                    if fixture is not fixtures[0]:b.command('rm '+remote+'/x')
                    b.command("PS1='# '")
                    upload(b,remote+'/x',fixture['raw']);b.command('stty -echo');b.command("PS1=''")
                    for mode in ('baseline','pool'):
                        bench=fixture is fixtures[0]
                        text=b.command('timeout -k 2 30 $b $x '+mode+(' --bench' if bench else ''),timeout=35)
                        (c.out/(fixture['name']+'-'+mode+'.stdout')).write_text(text,encoding='utf-8')
                        rows=[];measurements=[]
                        for line in text.splitlines():
                            if re.fullmatch(r'[012],[-+0-9.eE]+,[-+0-9.eE]+,[-+0-9.eE]+,[012]',line):
                                rows.append(np.fromstring(line,sep=','))
                            elif line.startswith('{'):measurements.append(__import__('json').loads(line))
                        values=np.asarray(rows);expected=np.asarray(fixture['modes'][mode]['expected_logits'])
                        if values.shape!=(3,5) or not np.isfinite(values).all():raise ValueError('ARM rows malformed')
                        np.testing.assert_array_equal(values[:,0],[0,1,2])
                        np.testing.assert_allclose(values[:,1:4],expected,rtol=1e-4,atol=5e-4)
                        np.testing.assert_array_equal(values[:,4],fixture['modes'][mode]['predictions'])
                        r['checks'].append(dict(name=fixture['name'],mode=mode,frames=3,
                            max_logit_error=float(abs(values[:,1:4]-expected).max()),predictions=values[:,4].astype(int).tolist(),matched=True))
                        if bench:
                            if len(measurements)!=1:raise ValueError('benchmark absent or duplicate')
                            m=measurements[0]
                            if (m['repeats']!=20 or m['frames_per_batch']!=3 or m['warmup']!=3
                                or not 0<m['mean_batch_ms']<=m['max_batch_ms']<200):
                                raise ValueError('compute latency gate failed')
                            r['benchmarks'].append(m)
                        elif measurements:raise ValueError('unexpected benchmark')
                        c.save()
                after=c.inspect('RX',b,identity);require_rx_control(after,running=False)
                if after['boot_id']!=before['boot_id'] or after['RF']!=before['RF']:
                    raise ValueError('RX boot/RF changed during saved-frame inference')
                r['before_RX']=before;r['after_RX']=after
            with c.board('TX') as (b,identity):
                after=c.inspect('TX',b,identity);require_tx_off(after)
                if after['boot_id']!=tx['boot_id'] or after['RF']!=tx['RF']:raise ValueError('TX changed')
                r['after_TX']=after
            r.update(status='passed_P74_actual_ARM_parity_latency_RAM_only_no_RF',
                     TX_stopped=True,RX_stopped=True,serial_closed=True,
                     scope='15 saved adapted frames per mode; benchmark excludes RF/FIR/IO/display, not end-to-end timing')
        except Exception as exc:r.update(status='failed_or_unconfirmed_P74_ARM_parity',error=repr(exc))
        finally:r['serial_closed']=True;c.save()
        print(c.out);print(r['status'])


if __name__=='__main__':main()
