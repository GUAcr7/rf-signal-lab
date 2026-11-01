/* Standalone offline/buffer-only parity and latency tool. No IIO or display IO. */
#define main frozen_p52_cli_main
#include "trained_cnn_infer.c"
#undef main
#include "phase_pool.h"

static float frames[54][2048];
static int run_batch(int count,int phase_pool,int emit) {
    for(int n=0;n<count;n++) {
        memcpy(original,frames[n],sizeof original);
        if(phase_pool?p74_infer(1):infer(1))return 1;
        int pred=0;for(int k=1;k<3;k++)if(logits[k]>logits[pred])pred=k;
        if(emit)printf("%d,%.17g,%.17g,%.17g,%d\n",n,logits[0],logits[1],logits[2],pred);
    }
    return 0;
}

int main(int argc,char **argv) {
    if(argc<3||argc>4||(strcmp(argv[2],"baseline")&&strcmp(argv[2],"pool"))||
       (argc==4&&strcmp(argv[3],"--bench")))return 2;
    if(fesetround(FE_TONEAREST))return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    if(fseek(f,0,SEEK_END)){fclose(f);return 2;}
    long size=ftell(f);
    if(size<=0||size%(2048*4)||size>(long)sizeof frames){fclose(f);return 2;}
    rewind(f);int count=(int)(size/(2048*4));
    if(fread(frames,2048*4,count,f)!=(size_t)count||fgetc(f)!=EOF){fclose(f);return 2;}
    fclose(f);
    for(int n=0;n<count;n++)for(int k=0;k<2048;k++)if(!isfinite(frames[n][k]))return 2;
    int pooled=!strcmp(argv[2],"pool");if(run_batch(count,pooled,1))return 2;
    if(argc==4) {
        double duration[20],total=0;struct rusage usage;
        for(int n=0;n<3;n++)if(run_batch(count,pooled,0))return 2;
        for(int n=0;n<20;n++) {
            double start=seconds();if(run_batch(count,pooled,0))return 2;
            duration[n]=1000*(seconds()-start);total+=duration[n];
        }
        qsort(duration,20,sizeof(double),cmp);if(getrusage(RUSAGE_SELF,&usage))return 2;
        printf("{\"mode\":\"%s\",\"frames_per_batch\":%d,\"repeats\":20,"
               "\"warmup\":3,\"mean_batch_ms\":%.9g,\"p95_batch_ms\":%.9g,"
               "\"max_batch_ms\":%.9g,\"maxrss_kib\":%ld,"
               "\"scope\":\"DC/RMS plus CNN with optional phase pooling; no FIR, IO or display\"}\n",
               argv[2],count,total/20,duration[18],duration[19],usage.ru_maxrss);
    }
    return 0;
}
