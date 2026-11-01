/* Untrained numerical/operator probe. No RF, IIO, or classification decision. */
#define _POSIX_C_SOURCE 200809L
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#ifndef _WIN32
#include <time.h>
#include <sys/resource.h>
#endif

enum { FRAME=1024, FEATURES=8, KERNEL=5, STRIDE=2, POSITIONS=510 };
static float input[FRAME][2];
static float feature[FEATURES][POSITIONS];
static float output[3];
static volatile float sink;

static __attribute__((noinline)) void infer(void) {
    float pooled[FEATURES];
    for (int o=0;o<FEATURES;o++) {
        pooled[o]=0.0f;
        for (int n=0;n<POSITIONS;n++) {
            float v=(float)(o-3)/64.0f;
            for (int i=0;i<2;i++) for (int k=0;k<KERNEL;k++) {
                float w=(float)((o*11+i*5+k*3)%17-8)/32.0f;
                v += w*input[n*STRIDE+k][i];
            }
            feature[o][n]=v>0.0f?v:0.0f;
            pooled[o]+=feature[o][n];
        }
        pooled[o]/=(float)POSITIONS;
    }
    for (int c=0;c<3;c++) {
        float v=(float)(c-1)/32.0f;
        for (int o=0;o<FEATURES;o++)
            v+=(float)((c*7+o*3)%11-5)/16.0f*pooled[o];
        output[c]=v;
    }
    sink=output[0]+output[1]+output[2];
}

static int load(const char *path) {
    FILE *f=fopen(path,"rb");
    if (!f) { perror(path); return 1; }
    unsigned char bytes[FRAME*4];
    if (fread(bytes,1,sizeof bytes,f)!=sizeof bytes || fgetc(f)!=EOF) {
        fclose(f); fprintf(stderr,"Expected exactly 4096 input bytes\n"); return 1;
    }
    fclose(f);
    for (int n=0;n<FRAME;n++) for (int i=0;i<2;i++) {
        int j=n*4+i*2;
        unsigned int u=(unsigned int)bytes[j]|((unsigned int)bytes[j+1]<<8);
        int v=u>=32768?((int)u-65536):(int)u;
        if (v < -2048 || v > 2047) { fprintf(stderr,"Outside signed 12-bit range\n"); return 1; }
        input[n][i]=(float)v/2048.0f;
    }
    return 0;
}

#ifndef _WIN32
static double seconds(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC,&t)) { perror("clock_gettime"); exit(2); }
    return (double)t.tv_sec+(double)t.tv_nsec*1e-9;
}
static int compare_double(const void *a,const void *b) {
    double x=*(const double *)a,y=*(const double *)b;
    return (x>y)-(x<y);
}
#endif

int main(int argc,char **argv) {
    if (argc<2 || argc>3 || (argc==3 && strcmp(argv[2],"--bench"))) {
        fprintf(stderr,"usage: tiny-cnn-probe input.iq [--bench]\n"); return 2;
    }
    if (load(argv[1])) return 2;
    infer();
    printf("%.9g,%.9g,%.9g\n",output[0],output[1],output[2]);
    if (argc==3) {
#ifdef _WIN32
        fprintf(stderr,"Benchmark requires Linux target\n"); return 2;
#else
        enum { WARMUP=25, REPEATS=300 };
        double times[REPEATS],sum=0;
        struct rusage usage;
        for (int j=0;j<WARMUP;j++) infer();
        float original=input[0][0];
        for (int j=0;j<REPEATS;j++) {
            input[0][0]=original+(j%2?0.0f:1.0f/2048.0f);
            double start=seconds(); infer(); times[j]=(seconds()-start)*1000; sum+=times[j];
        }
        qsort(times,REPEATS,sizeof(double),compare_double);
        if (getrusage(RUSAGE_SELF,&usage)) { perror("getrusage"); return 2; }
        printf("{\"untrained_operator_probe\":true,\"frame\":1024,\"parameters\":115,"
               "\"warmup\":%d,\"repeats\":%d,\"mean_ms\":%.9g,\"p50_ms\":%.9g,"
               "\"p95_ms\":%.9g,\"max_ms\":%.9g,\"maxrss_kib\":%ld,\"sink\":%.9g}\n",
               WARMUP,REPEATS,sum/REPEATS,times[REPEATS/2],times[284],times[299],usage.ru_maxrss,(double)sink);
#endif
    }
    return 0;
}
