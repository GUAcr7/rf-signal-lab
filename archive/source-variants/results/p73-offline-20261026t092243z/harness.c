#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=4||p56_initialize())return 2;
    FILE *steps=fopen(argv[2],"r");if(!steps)return 2;
    p56_begin=now_s();panel_sample_rate_hz=30720000;p69_lo=2450000000;
    unsigned seq,state,ready,enabled,value,damage;double elapsed;
    unsigned char input[262144];
    while(fscanf(steps,"%lf %u %u %u %u %u %u",&elapsed,&seq,&state,&ready,&enabled,&value,&damage)==7) {
        if(setenv("P73_EVENT_CAPTURE",enabled?"1":"0",1))return 2;
        p56_ready=(int)ready;p56_state=(enum p56_state)state;p56_class=state==P56_CLASSIFIED?2:-1;
        p67_sequence=seq;p67_elapsed=elapsed;memset(input,(int)value,sizeof input);
        if(p56_evidence(argv[1],seq)||p69_evidence(argv[1],"running",0))return 3;
        if(damage) {
            char path[1024];snprintf(path,sizeof path,"%s/metrics.json",argv[1]);
            FILE *f=fopen(path,"wb");if(!f)return 3;fputs("{\"source_block_sequence\":999999}\n",f);fclose(f);
        }
        int result=p73_event(argv[1],input);
        printf("{\"sequence\":%u,\"result\":%d,\"total\":%u}\n",seq,result,p73_capture.total);
    }
    fclose(steps);if(p56_history)fclose(p56_history);if(p69_history)fclose(p69_history);
    return 0;
}