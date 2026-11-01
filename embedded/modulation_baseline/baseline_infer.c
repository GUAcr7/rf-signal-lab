/* Frozen traditional model. Synthetic test inference only; no unknown rejection. */
#define _POSIX_C_SOURCE 200809L
#include <complex.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <math.h>
#ifndef _WIN32
#include <time.h>
#include <sys/resource.h>
#endif
#include "model.h"

static double complex input[1024];
static double feature[14],logits[3];
static volatile double sink;
static int cmp_double(const void *a,const void *b){double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);}
static double quantile(double *sorted,double q){double pos=1023*q;int i=(int)pos;double fraction=pos-i;return sorted[i]*(1-fraction)+sorted[i+1]*fraction;}
static __attribute__((noinline)) int infer(void){
    double complex x[1024],mean=0,m2=0,m4=0;double radius[1024],power=0;
    for(int n=0;n<1024;n++)mean+=input[n];mean/=1024;
    for(int n=0;n<1024;n++){x[n]=input[n]-mean;power+=creal(x[n])*creal(x[n])+cimag(x[n])*cimag(x[n]);}power/=1024;
    if(!isfinite(power)||power<=1e-20)return 1;
    double scale=sqrt(power);double moments[4]={0};
    for(int n=0;n<1024;n++){
        x[n]/=scale;double r=cabs(x[n]),r2=r*r;radius[n]=r;
        moments[0]+=r;moments[1]+=r*r2;moments[2]+=r2*r2;moments[3]+=r2*r2*r2;
        m2+=x[n]*x[n];m4+=x[n]*x[n]*x[n]*x[n];
    }
    for(int j=0;j<4;j++)feature[j]=moments[j]/1024;
    qsort(radius,1024,sizeof(double),cmp_double);
    double qs[4]={.1,.5,.9,.99};for(int j=0;j<4;j++)feature[4+j]=quantile(radius,qs[j]);
    feature[8]=cabs(m2/1024);feature[9]=cabs(m4/1024);
    int lags[3]={1,2,4};
    for(int j=0;j<3;j++){int k=lags[j];double complex sum=0;for(int n=k;n<1024;n++)sum+=x[n]*conj(x[n-k]);feature[10+j]=cabs(sum/(1024-k));}
    double complex sum=0;for(int n=1;n<1024;n++)sum+=x[n]*x[n]*conj(x[n-1]*x[n-1]);feature[13]=cabs(sum/1023);
    for(int c=0;c<3;c++){logits[c]=model_bias[c];for(int j=0;j<14;j++)logits[c]+=(feature[j]-model_mean[j])/model_scale[j]*model_weights[j][c];}
    sink=logits[0]+logits[1]+logits[2];return 0;
}
#ifndef _WIN32
static double seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(2);return (double)t.tv_sec+(double)t.tv_nsec*1e-9;}
#endif
int main(int argc,char **argv){
    if(argc<2||argc>3||(argc==3&&strcmp(argv[2],"--bench")))return 2;
    FILE *f=fopen(argv[1],"rb");if(!f){perror(argv[1]);return 2;}
    float raw[2048];
    if(fread(raw,sizeof(float),2048,f)!=2048||fgetc(f)!=EOF){fclose(f);return 2;}fclose(f);
    for(int n=0;n<1024;n++){if(!isfinite(raw[2*n])||!isfinite(raw[2*n+1]))return 2;input[n]=(double)raw[2*n]+I*(double)raw[2*n+1];}
    if(infer())return 2;
    int predicted=0;for(int c=1;c<3;c++)if(logits[c]>logits[predicted])predicted=c;
    for(int j=0;j<14;j++)printf("%.17g,",feature[j]);for(int c=0;c<3;c++)printf("%.17g,",logits[c]);printf("%d\n",predicted);
    if(argc==3){
#ifdef _WIN32
        return 2;
#else
        double duration[100],total=0;double complex original=input[0];struct rusage usage;
        for(int n=0;n<5;n++)if(infer())return 2;
        for(int n=0;n<100;n++){input[0]=original+(n%2?0:1e-6);double before=seconds();if(infer())return 2;duration[n]=(seconds()-before)*1000;total+=duration[n];}
        qsort(duration,100,sizeof(double),cmp_double);if(getrusage(RUSAGE_SELF,&usage))return 2;
        printf("{\"repeats\":100,\"warmup\":5,\"mean_ms\":%.9g,\"p50_ms\":%.9g,\"p95_ms\":%.9g,\"max_ms\":%.9g,\"maxrss_kib\":%ld,\"sink\":%.9g,\"scope\":\"FP64 features plus frozen linear head; file IO excluded\"}\n",total/100,duration[50],duration[94],duration[99],usage.ru_maxrss,(double)sink);
#endif
    }
    return 0;
}
