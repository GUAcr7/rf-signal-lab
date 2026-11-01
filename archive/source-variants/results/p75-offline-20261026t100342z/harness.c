#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=3||setenv("P56_CONTROL_FILE",argv[2],1)||p56_initialize())return 2;
    panel_sample_rate_hz=30720000;p69_lo=2450000000;
    char request[1024];snprintf(request,sizeof request,"%s/shot",argv[1]);
    if(setenv("P56_SHOT_FILE",request,1))return 2;
    FILE *script=fopen("/mnt/c/Users/LENOVO/Documents/Codex/2026-09-09/2026-fpga-fmql30tai-fpai-python-c/outputs/rf-signal-lab/results/p75-offline-20261026T100342Z/steps.txt","r");if(!script)return 2;
    fb=calloc(PANEL_W*PANEL_H,4);fb_stride_words=PANEL_W;if(!fb)return 2;
    unsigned char input[262144];int16_t iq[131072];float window[FFT_N];double acc[FFT_N];
    for(int n=0;n<FFT_N;n++)window[n]=.5f-.5f*(float)cos(2*M_PI*n/FFT_N);
    char op[8],path[1024];unsigned index=0;
    while(fscanf(script,"%7s %1023s",op,path)==2) {
        if(!strcmp(op,"absent"))unlink(argv[2]);
        else if(strcmp(op,"keep")) {
            FILE *f=fopen(argv[2],"wb");if(!f)return 2;
            const char *boot=!strcmp(op,"stale")?"00000000-0000-0000-0000-000000000000":p56_boot;
            fprintf(f,"P56CAL1 %s %s %s\n",boot,AI_MODEL_SHA,"11111111111111111111111111111111");fclose(f);
        }
        FILE *f=fopen(path,"rb");if(!f)return 2;
        if(fread(input,1,sizeof input,f)!=sizeof input)return 2;
        fclose(f);if(p56_step(input))return 3;
        decode_latest(input,iq);struct metrics m={0};spectrum(iq,8192,2,8,0,window,acc,&m);
        p67_measure(iq,acc,index+1,index*.5);p69_measure(acc,window);
        if(p56_evidence(argv[1],index+1)||p69_evidence(argv[1],"running",0))return 3;
        p69_draw(acc,&m,2,8192,index,0,8);p56_line();
        f=fopen(request,"w");if(!f)return 3;fprintf(f,"%u\n",index+1);fclose(f);
        if(p56_shot(argv[1],input,1)||p69_shot(argv[1]))return 3;
        index++;
    }
    fclose(script);p56_state=P56_STOPPED;p56_class=-1;
    if(p69_evidence(argv[1],"finished",1))return 3;
    if(p56_history)fclose(p56_history);
    free(fb);return 0;
}