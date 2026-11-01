"""Linux PTY tests only, no board. Run via WSL with explicit output directory."""
import errno,json,os,pty,select,signal,subprocess,sys,termios,threading,time
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
out=Path(sys.argv[1]);out.mkdir(parents=True,exist_ok=True)
source=ROOT/'embedded/p201_uart/uart_loopback.c'
binary=out/'uart-loopback-host'
subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror','-DUART_HOST_TEST',str(source),'-o',str(binary)],check=True)
rows=[]
def case(mode,expected):
    master,slave=pty.openpty();dev=os.ttyname(slave);before=termios.tcgetattr(slave);stop=threading.Event()
    def peer():
        corrupt=False
        while not stop.is_set():
            if not select.select([master],[],[],.02)[0]:continue
            try:data=os.read(master,4096)
            except OSError as e:
                if e.errno==errno.EIO:continue
                raise
            if mode in ('silent','interrupt'):continue
            if mode=='corrupt' and not corrupt:
                data=bytes([data[0]^1])+data[1:];corrupt=True
            # Deliberately exercise fragmented reads, not just one write/read.
            for start in range(0,len(data),7):
                if stop.is_set():break
                os.write(master,data[start:start+7]);time.sleep(.0005)
    worker=threading.Thread(target=peer,daemon=True);worker.start()
    started=time.monotonic()
    p=subprocess.Popen([str(binary),'--device',dev,'--run-loopback','--test-pty','--bytes','1024','--timeout-ms','500'],stdout=subprocess.PIPE,stderr=subprocess.PIPE)
    if mode=='interrupt':time.sleep(.1);p.send_signal(signal.SIGINT)
    stdout,stderr=p.communicate(timeout=3);elapsed=time.monotonic()-started
    stop.set();worker.join(1)
    restored=termios.tcgetattr(slave)==before
    os.close(master);os.close(slave)
    row=dict(case=mode,exit_code=p.returncode,expected=expected,elapsed_s=elapsed,termios_restored=restored,stdout=stdout.decode(),stderr=stderr.decode())
    rows.append(row)
    assert p.returncode==expected and restored and elapsed<2,row
for mode,code in [('fragmented_echo',0),('corrupt',5),('silent',4),('interrupt',130)]:case(mode,code)
for label,args in [('missing',[]),('console',['--device','/dev/ttyPS0','--run-loopback']),('invalid_timeout',['--device','/dev/pts/1','--test-pty','--run-loopback','--timeout-ms','0'])]:
    p=subprocess.run([str(binary),*args],capture_output=True,timeout=2)
    rows.append(dict(case=label,exit_code=p.returncode,expected=2));assert p.returncode==2
(out/'pty-tests.json').write_text(json.dumps(dict(status='passed_seven_Linux_PTY_cases_not_physical_UART',cases=rows),indent=2)+'\n')
print('7 UART PTY cases passed; not physical UART validation')
