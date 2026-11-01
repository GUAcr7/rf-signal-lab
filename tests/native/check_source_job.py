"""Actual Linux child ownership/stop/receipt tests with a fake guard, no RF."""
from datetime import datetime
from pathlib import Path
import json,shutil,subprocess,sys,time

FAKE=r'''
#define _POSIX_C_SOURCE 200809L
#include <signal.h>
#include <stdio.h>
#include <string.h>
#include <time.h>
static volatile sig_atomic_t stopped=0;
static void stop(int n){(void)n;stopped=1;}
int main(void){
    struct sigaction a;memset(&a,0,sizeof a);a.sa_handler=stop;
    sigemptyset(&a.sa_mask);if(sigaction(SIGTERM,&a,0))return 1;
    FILE *f=fopen("mode","r");int hold=f?fgetc(f)=='1':0;if(f)fclose(f);
    puts("CYCLIC_PUSH_SUBMITTED samples=131072 deadline_seconds=8");fflush(stdout);
    struct timespec t={0,10000000};
    for(int i=0;i<(hold?500:20)&&!stopped;i++)nanosleep(&t,0);
    printf("TX_SOFTWARE_DEADLINE_END stop_signal=%d\n",(int)stopped);
    puts("DDS_ZERO_SOURCE_READBACK=PASS");
    puts("TX_CLEANUP buffer_released=true rf_settings_written=false status=0");
    return 0;
}
'''

def main():
    template=Path(sys.argv[1]);out=Path(sys.argv[2]);out.mkdir(exist_ok=False)
    (out/'fake.c').write_text(FAKE)
    subprocess.run(['gcc','-std=c11','-O2','-Wall','-Wextra','-Werror',str(out/'fake.c'),'-o',str(out/'guard')],check=True)
    bank=Path('/tmp')/datetime.now().strftime('p35-p59-%Y%m%dT%H%M%SZ')
    bank.mkdir(exist_ok=False);shutil.copyfile(out/'guard',bank/'guard');(bank/'guard').chmod(0o700)
    boot=Path('/proc/sys/kernel/random/boot_id').read_text().strip()
    rows=[]
    for index,(name,cancel,badboot,badsignal) in enumerate([
        ('natural',False,False,False),('owned_stop',True,False,False),
        ('wrong_boot',False,True,False),('unknown_signal',False,False,True)]):
        nonce=f'{index+1:08x}';job=bank/('job-'+nonce);job.mkdir()
        (bank/'mode').write_text('1' if cancel else '0')
        args=['setsid','timeout','-k','2','12','sh',str(template),str(bank),str(job),
              'bad;reboot' if badsignal else 'tone','8','00000000-0000-0000-0000-000000000000' if badboot else boot,'0'*64,nonce]
        p=subprocess.Popen(args,stdin=subprocess.DEVNULL,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        if cancel:
            deadline=time.monotonic()+4
            while time.monotonic()<deadline:
                if (job/'native.log').is_file() and 'CYCLIC_PUSH_SUBMITTED' in (job/'native.log').read_text():break
                time.sleep(.02)
            else:raise AssertionError('Fake child did not submit')
            (job/'stop').touch()
        stdout,stderr=p.communicate(timeout=10)
        (out/(name+'.stdout')).write_bytes(stdout);(out/(name+'.stderr')).write_bytes(stderr)
        if badboot or badsignal:
            assert p.returncode==2 and not (job/'native.log').exists()
            rows.append(dict(name=name,passed=True,rejected_before_child=True));continue
        receipt=json.loads((job/'receipt.json').read_text())
        native=(job/'native.log').read_text()
        assert p.returncode==0 and receipt['exit_code']==0 and receipt['child_reaped']
        assert receipt['identity_valid'] and receipt['nonce']==nonce and receipt['boot_id']==boot
        assert receipt['stop_seen']==cancel and receipt['signal_sent']==cancel
        assert ('stop_signal=1' in native)==cancel
        assert not Path('/proc/'+str(receipt['child_pid'])).exists()
        shutil.copyfile(job/'receipt.json',out/(name+'-receipt.json'))
        shutil.copyfile(job/'native.log',out/(name+'-native.log'))
        # A completed job cannot be replayed to launch a second child.
        duplicate=subprocess.run(args,stdin=subprocess.DEVNULL,capture_output=True,timeout=3)
        assert duplicate.returncode==2
        rows.append(dict(name=name,passed=True,duplicate_rejected=True))
    (out/'report.json').write_text(json.dumps(dict(status='passed_P79_actual_Linux_supervisor_mock_no_RF',
                                                 cases=rows,board_operations=False,RF_transmissions=0),indent=2))
    print(out/'report.json')

if __name__=='__main__':main()
