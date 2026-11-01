
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
