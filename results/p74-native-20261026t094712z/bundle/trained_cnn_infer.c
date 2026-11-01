/* Frozen REAL-RF-trained CNN. No IIO, RF writes or confidence calibration. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include <math.h>
#include <fenv.h>
#ifndef _WIN32
#include <time.h>
#include <sys/resource.h>
#endif
#include "trained_model.h"

static float original[2048],normalized[2048];
static double logits[3];
static volatile double sink;

static int preprocess(void) {
    double mi=0,mq=0,power=0;
    for(int n=0;n<1024;n++){mi+=original[2*n];mq+=original[2*n+1];}
    mi/=1024;mq/=1024;
    for(int n=0;n<1024;n++){
        double a=original[2*n]-mi,b=original[2*n+1]-mq;
        power+=a*a+b*b;
    }
    power/=1024;
    if(!isfinite(power)||power<=1e-20)return 1;
    double scale=sqrt(power);
    for(int n=0;n<1024;n++){
        normalized[2*n]=(float)((original[2*n]-mi)/scale);
        normalized[2*n+1]=(float)((original[2*n+1]-mq)/scale);
    }
    return 0;
}

static __attribute__((noinline)) int infer(int quantized) {
    if(preprocess())return 1;
    if(!quantized){
        float pooled[8]={0};
        for(int t=0;t<510;t++){
            for(int ch=0;ch<8;ch++){
                float z=conv_bias[ch];
                for(int k=0;k<10;k++)z+=normalized[4*t+k]*conv_weights[k][ch];
                pooled[ch]+=z>0?z:0;
            }
        }
        for(int ch=0;ch<8;ch++)pooled[ch]/=510;
        for(int c=0;c<3;c++){
            float z=dense_bias[c];
            for(int ch=0;ch<8;ch++)z+=pooled[ch]*dense_weights[ch][c];
            logits[c]=z;
        }
    }else{
        int8_t x[2048];int32_t pooled[8]={0};
        for(int n=0;n<2048;n++){
            double q=nearbyint((double)normalized[n]/input_scale);
            x[n]=(int8_t)(q>127?127:(q< -127?-127:q));
        }
        double rescale=input_scale*conv_weight_scale/activation_scale;
        for(int t=0;t<510;t++){
            for(int ch=0;ch<8;ch++){
                int32_t z=quant_conv_bias[ch];
                for(int k=0;k<10;k++)z+=(int32_t)x[4*t+k]*quant_conv_weights[k][ch];
                double q=nearbyint(z*rescale);
                pooled[ch]+=(int32_t)(q>127?127:(q<0?0:q));
            }
        }
        for(int c=0;c<3;c++){
            int32_t z=0;
            for(int ch=0;ch<8;ch++)z+=pooled[ch]*(int32_t)quant_dense_weights[ch][c];
            logits[c]=z*(activation_scale*dense_weight_scale/510)+(double)dense_bias[c];
        }
    }
    sink=logits[0]+logits[1]+logits[2];return 0;
}
#ifndef _WIN32
static double seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(2);return t.tv_sec+t.tv_nsec*1e-9;}
static int cmp(const void *a,const void *b){double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);}
#endif
int main(int argc,char **argv){
    if(argc<3||argc>4||(strcmp(argv[2],"fp32")&&strcmp(argv[2],"int8"))||(argc==4&&strcmp(argv[3],"--bench")))return 2;
    if(fesetround(FE_TONEAREST))return 2;
    FILE *f=fopen(argv[1],"rb");if(!f){perror(argv[1]);return 2;}
    if(fread(original,sizeof(float),2048,f)!=2048||fgetc(f)!=EOF){fclose(f);return 2;}fclose(f);
    for(int n=0;n<2048;n++)if(!isfinite(original[n]))return 2;
    int q=!strcmp(argv[2],"int8");if(infer(q))return 2;
    int pred=0;for(int c=1;c<3;c++)if(logits[c]>logits[pred])pred=c;
    printf("%.17g,%.17g,%.17g,%d\n",logits[0],logits[1],logits[2],pred);
    if(argc==4){
#ifdef _WIN32
        return 2;
#else
        double d[100],total=0;float first=original[0];struct rusage usage;
        for(int n=0;n<5;n++)if(infer(q))return 2;
        for(int n=0;n<100;n++){
            original[0]=first+(n%2?0:1e-6f);
            double before=seconds();if(infer(q))return 2;d[n]=(seconds()-before)*1000;total+=d[n];
        }
        qsort(d,100,sizeof(double),cmp);if(getrusage(RUSAGE_SELF,&usage))return 2;
        printf("{\"mode\":\"%s\",\"repeats\":100,\"warmup\":5,\"mean_ms\":%.9g,\"p50_ms\":%.9g,\"p95_ms\":%.9g,\"max_ms\":%.9g,\"maxrss_kib\":%ld,\"sink\":%.9g,\"scope\":\"DC/RMS preprocessing plus CNN; file IO excluded\"}\n",argv[2],total/100,d[50],d[94],d[99],usage.ru_maxrss,(double)sink);
#endif
    }
    return 0;
}
