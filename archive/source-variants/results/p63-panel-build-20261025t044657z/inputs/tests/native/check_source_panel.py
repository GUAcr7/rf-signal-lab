"""Independent event/contract checks. Native logic subprocesses; no board IO."""
import json
import importlib.util
import random
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
# Import the IO-free codec directly; package __init__ pulls DSP/numpy, which
# this WSL logic-only check deliberately does not need.
spec=importlib.util.spec_from_file_location('p63_tjc_codec',ROOT/'src/rfsig/tjc_protocol.py')
codec=importlib.util.module_from_spec(spec);sys.modules[spec.name]=codec;spec.loader.exec_module(codec)
ReturnParser,ProtocolError,END=codec.ReturnParser,codec.ProtocolError,codec.END


def main():
    binary, out = Path(sys.argv[1]), Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=False)
    rows = []

    def replay(name, commands, expect):
        p = subprocess.run([str(binary), '--replay'], input='\n'.join(commands)+'\n',
                           text=True, capture_output=True, timeout=4)
        (out / (name+'.input')).write_text('\n'.join(commands)+'\n')
        (out / (name+'.stdout')).write_text(p.stdout)
        (out / (name+'.stderr')).write_text(p.stderr)
        assert p.returncode == 0, (name, p.stderr)
        states = [json.loads(line) for line in p.stdout.splitlines()]
        assert len(states) == len(commands)+1
        assert all(v['mode'] == 'LOGIC_ONLY_NO_RF' for v in states)
        for index, wanted in expect.items():
            actual = states[index]
            assert all(actual[k] == v for k, v in wanted.items()), (name, index, wanted, actual)
        rows.append(dict(name=name, events=len(commands), passed=True))
        return states

    ready = ['LINK 0', 'TOUCH 100 0 5 0', 'CHECKED 110 1']
    running = ready + ['TOUCH 200 0 6 0', 'SUBMITTED 210']
    replay('offline_and_unapplied', ['TOUCH 0 0 6 0','LINK 10','TOUCH 300 0 6 0'],
           {-1:dict(state='IDLE',child_active=0,effect='NONE',applied=-1)})
    replay('happy', running+['TOUCH 400 0 7 0','FINISHED 410 1'],
           {4:dict(state='STARTING',effect='START'),5:dict(state='RUNNING'),
            6:dict(state='STOPPING',effect='STOP'),7:dict(state='IDLE',applied=-1)})
    replay('failed_apply', ready[:2]+['CHECKED 110 0','TOUCH 200 0 6 0','LINK 300'],
           {-1:dict(state='FAULT',child_active=0,fault=1)})
    replay('press_other_page_unknown', ['LINK 0','TOUCH 100 0 5 1','TOUCH 200 1 5 0','TOUCH 300 0 99 0'],
           {-1:dict(state='IDLE',effect='NONE')})
    replay('duplicate_start', running+['TOUCH 220 0 6 0','TOUCH 600 0 6 0'],
           {-1:dict(state='RUNNING',effect='NONE',active=0)})
    replay('stop_before_submit', ready+['TOUCH 200 0 6 0','TOUCH 210 0 7 0','SUBMITTED 220'],
           {-1:dict(state='STOPPING',effect='NONE',child_active=1)})
    replay('stop_not_debounced', ready+['TOUCH 120 0 7 0','TOUCH 400 0 5 0','CHECKED 410 1',
                                      'TOUCH 420 0 6 0','TOUCH 430 0 7 0'],
           {-1:dict(state='STOPPING',effect='STOP')})
    replay('change_signal_stops_old', running+['TOUCH 300 0 4 0','TOUCH 400 0 6 0','FINISHED 500 1'],
           {6:dict(state='STOPPING',effect='STOP',selected=3,active=0),
            -1:dict(state='IDLE',effect='NONE',applied=-1,child_active=0)})
    replay('change_duration_stops_old', running+['TOUCH 300 0 9 0'],
           {-1:dict(state='STOPPING',effect='STOP',seconds=20,active_seconds=15)})
    replay('stale_apply', ready[:2]+['TOUCH 200 0 3 0','CHECKED 210 1','TOUCH 300 0 6 0'],
           {-1:dict(state='IDLE',effect='NONE',applied=-1)})
    replay('old_check_cannot_arm_new', ready+['TOUCH 400 0 5 0','CHECKED_GEN 410 2 1'],
           {-1:dict(state='CHECKING',applied=-1)})
    replay('expiry_and_reconnect', running+['TICK 2500','LINK 2600','TOUCH 2700 0 6 0','FINISHED 2800 1'],
           {6:dict(state='STOPPING',effect='STOP'),7:dict(state='STOPPING'),
            -1:dict(state='IDLE',applied=-1)})
    replay('late_heartbeat_cannot_preserve_ready', ready+['LINK 2500','TOUCH 2600 0 6 0'],
           {-1:dict(state='IDLE',applied=-1,effect='NONE')})
    replay('late_heartbeat_stops_running', running+['LINK 2500'],
           {-1:dict(state='STOPPING',effect='STOP')})
    replay('explicit_disconnect', running+['LOST 300','FINISHED 400 1'],
           {-1:dict(state='OFFLINE',child_active=0,applied=-1)})
    replay('cleanup_failure_latched', running+['TOUCH 300 0 7 0','FINISHED 400 0','LINK 500','TOUCH 600 0 5 0'],
           {-1:dict(state='FAULT',fault=1,child_active=0)})
    replay('clock_backwards', running+['TICK 100','LINK 400','FINISHED 500 1'],
           {6:dict(state='STOPPING',effect='STOP',fault=1),-1:dict(state='FAULT')})
    replay('check_timeout', ready[:2]+['LINK 1000','LINK 2000','LINK 3000','TICK 3100'],
           {-1:dict(state='FAULT',fault=1)})
    replay('start_timeout', ready+['TOUCH 200 0 6 0','LINK 1000','LINK 2000','LINK 3000','TICK 3200'],
           {-1:dict(state='STOPPING',effect='STOP',fault=1)})
    replay('duration_deadline', running+[f'LINK {t}' for t in range(1000,17001,1000)]+['TICK 17200'],
           {-1:dict(state='STOPPING',effect='STOP')})
    boundcmd=['LINK 0']
    for index in range(1,5): boundcmd += [f'LINK {index*400}',f'TOUCH {index*400} 0 8 0']
    for index in range(5,20): boundcmd += [f'LINK {index*400}',f'TOUCH {index*400} 0 9 0']
    replay('duration_clamps', boundcmd, {9:dict(seconds=8),-1:dict(seconds=60)})

    # Actual official wire-format returns, fragmented across arbitrary boundaries.
    # Only touch events are forwarded by this test harness; numeric/status are not LINK.
    wire = (bytes([0x65,0,5,1])+END + bytes([0x65,0,5,0])+END
            + bytes([0x71,255,255,255,255])+END + bytes([0x65,1,6,0])+END)
    parser=ReturnParser(); events=[]
    for begin in range(0,len(wire),2): events += parser.feed(wire[begin:begin+2])
    commands=['LINK 0']; time=100
    for event in events:
        if event.kind=='touch':
            page,component,edge=event.payload
            commands.append(f'TOUCH {time} {page} {component} {edge}');time+=100
    replay('fragmented_wire_to_logic', commands, {-1:dict(state='CHECKING',child_active=0)})
    try: ReturnParser().feed(b'\x65\x00\x06\x02'+END)
    except ProtocolError: pass
    else: raise AssertionError('Malformed wire event accepted')

    # Reproducible event fuzzing checks safety properties, independent of internals.
    rng=random.Random(20261025);commands=[]
    for i in range(1,801):
        now=i*100
        if i%10==0: commands.append(f'LINK {now}')
        else: commands.append(rng.choice([f'TOUCH {now} 0 {rng.randrange(1,10)} 0',
                                         f'CHECKED {now} 1',f'SUBMITTED {now}',f'TICK {now}']))
    states=replay('random_contract',commands,{})
    for previous,current in zip(states,states[1:]):
        assert 8<=current['seconds']<=60
        if current['effect']=='START':
            assert previous['state']=='READY' and previous['applied']==previous['selected']
            assert current['state']=='STARTING' and current['child_active']==1
        if current['state']=='RUNNING': assert current['child_active']==1
        if previous['state']=='STOPPING': assert current['state']!='RUNNING'
        if previous['fault']: assert current['fault'] and current['effect']!='START'
    refusals=[]
    for name,args,data in [('hardware_mode',['--device','/dev/ttyPS0'],''),
                           ('injected_line',['--replay'],'LINK 1 extra\n'),
                           ('truncated',['--replay'],'LINK 1'),
                           ('oversize',['--replay'],'X'*200+'\n')]:
        p=subprocess.run([str(binary),*args],input=data,text=True,capture_output=True,timeout=3)
        assert p.returncode==2,(name,p.returncode)
        refusals.append(dict(name=name,exit_code=p.returncode))
    report=dict(status='passed_OFFLINE_logic_contract',cases=rows,refusals=refusals,
                randomized_events=800,board_operations=False,UART_opened=False,RF_operations=False)
    (out/'report.json').write_text(json.dumps(report,indent=2)+'\n')
    print(json.dumps(dict(status=report['status'],cases=len(rows),refusals=len(refusals))))

if __name__=='__main__': main()
