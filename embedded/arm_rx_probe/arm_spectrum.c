/* Software ARM FFT reference. Raw signed12-in-int16 I/Q; not an FPGA FFT. */
#define _POSIX_C_SOURCE 200809L
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <math.h>
#include <complex.h>
#ifndef _WIN32
#include <time.h>
#include <sys/resource.h>
#endif

#define N 1024
static double window[N],weight_energy;
static double complex twiddle[N/2],x[N];
static double density[N];
static volatile double sink;

static void setup(void){
    double pi=acos(-1);
    for(int n=0;n<N;n++){window[n]=.5-.5*cos(2*pi*n/N);weight_energy+=window[n]*window[n];}
    for(int n=0;n<N/2;n++)twiddle[n]=cos(-2*pi*n/N)+I*sin(-2*pi*n/N);
}
static __attribute__((noinline)) void calculate(const int16_t *raw,double fs,double *mean,double *weighted){
    *mean=0;*weighted=0;
    for(int n=0;n<N;n++){
        double a=raw[2*n],b=raw[2*n+1],power=a*a+b*b;
        *mean+=power;*weighted+=power*window[n]*window[n];x[n]=(a+I*b)*window[n];
    }
    *mean/=N;*weighted/=weight_energy;
    for(unsigned i=1,j=0;i<N;i++){
        unsigned bit=N>>1;
        while(j&bit){j^=bit;bit>>=1;}j^=bit;
        if(i<j){double complex tmp=x[i];x[i]=x[j];x[j]=tmp;}
    }
    for(int length=2;length<=N;length*=2){
        for(int start=0;start<N;start+=length){
            for(int k=0;k<length/2;k++){
                double complex u=x[start+k],v=x[start+k+length/2]*twiddle[k*N/length];
                x[start+k]=u+v;x[start+k+length/2]=u-v;
            }
        }
    }
    for(int n=0;n<N;n++){
        double a=creal(x[(n+N/2)%N]),b=cimag(x[(n+N/2)%N]);density[n]=(a*a+b*b)/(fs*weight_energy);
    }
    sink=density[17];
}
static double interval_edge(double fraction,double fs,double total){
    double acc=0,target=fraction*total,width=fs/N;
    for(int n=0;n<N;n++){
        double f=(n-N/2)*width,left=fmax(f-width/2,-9e6),right=fmin(f+width/2,9e6);
        double overlap=fmax(right-left,0),mass=density[n]*overlap;
        if(mass>0 && acc+mass>=target)return left+(target-acc)/mass*overlap;
        acc+=mass;
    }
    return 9e6;
}
#ifndef _WIN32
static double seconds(void){struct timespec t;if(clock_gettime(CLOCK_MONOTONIC,&t))exit(2);return t.tv_sec+t.tv_nsec*1e-9;}
static int cmp(const void *a,const void *b){double x=*(const double *)a,y=*(const double *)b;return (x>y)-(x<y);}
#endif
int main(int argc,char **argv){
    if(argc!=4)return 2;
    char *end;double fs=strtod(argv[3],&end);
    if(*end || fs!=30720000){fprintf(stderr,"This validation uses explicit Fs=30720000 only\n");return 2;}
    FILE *input=fopen(argv[1],"rb");if(!input)return 2;
    if(fseek(input,0,SEEK_END)){fclose(input);return 2;}long bytes=ftell(input);rewind(input);
    if(bytes<=0 || bytes%(N*4) || bytes>N*4*64){fclose(input);return 2;}
    char path[1024];if(snprintf(path,sizeof path,"%s.psd",argv[2])>=(int)sizeof path){fclose(input);return 2;}
    FILE *psd=fopen(path,"wbx");if(!psd){fclose(input);return 2;}
    if(snprintf(path,sizeof path,"%s.json",argv[2])>=(int)sizeof path){fclose(input);fclose(psd);return 2;}
    FILE *meta=fopen(path,"wbx");if(!meta){fclose(input);fclose(psd);return 2;}
    setup();int frames=(int)(bytes/(N*4));int16_t raw[2048];double mean,weighted;
    fprintf(meta,"{\"frame_length\":1024,\"frames\":%d,\"sample_rate_hz\":%.0f,\"window\":\"hann_periodic\",\"DC_removed\":false,\"PSD_units\":\"raw_counts_squared_per_Hz\",\"hardware_gaps\":\"unknown\",\"target\":\"unknown\",\"records\":[",frames,fs);
    for(int frame=0;frame<frames;frame++){
        if(fread(raw,sizeof(int16_t),2048,input)!=2048)return 2;
        for(int n=0;n<2048;n++)if(raw[n]< -2048||raw[n]>2047)return 2;
        calculate(raw,fs,&mean,&weighted);double integral=0,roi=0,width=fs/N;
        for(int n=0;n<N;n++){
            integral+=density[n]*width;double f=(n-N/2)*width;
            roi+=density[n]*fmax(fmin(f+width/2,9e6)-fmax(f-width/2,-9e6),0);
        }
        if(fwrite(density,sizeof(double),N,psd)!=N)return 2;
        fprintf(meta,"%s{\"frame\":%d,\"mean_power\":%.17g,\"weighted_power\":%.17g,\"integrated_psd\":%.17g,\"ROI_power\":%.17g",frame?",":"",frame,mean,weighted,integral,roi);
        if(roi>0){double lo=interval_edge(.005,fs,roi),hi=interval_edge(.995,fs,roi);fprintf(meta,",\"ROI_lower_hz\":%.17g,\"ROI_upper_hz\":%.17g,\"ROI_width_hz\":%.17g,\"ROI_midpoint_hz\":%.17g",lo,hi,hi-lo,(lo+hi)/2);}
        else fprintf(meta,",\"ROI_lower_hz\":null,\"ROI_upper_hz\":null,\"ROI_width_hz\":null,\"ROI_midpoint_hz\":null");
        fprintf(meta,"}");
    }
    fprintf(meta,"]");
#ifndef _WIN32
    double d[100],total=0;struct rusage usage;int16_t first=raw[0];
    for(int n=0;n<5;n++)calculate(raw,fs,&mean,&weighted);
    for(int n=0;n<100;n++){
        raw[0]=(int16_t)(first+(n%2 || first==2047?0:1));double before=seconds();calculate(raw,fs,&mean,&weighted);d[n]=(seconds()-before)*1000;total+=d[n];
    }
    qsort(d,100,sizeof(double),cmp);if(getrusage(RUSAGE_SELF,&usage))return 2;
    fprintf(meta,",\"benchmark\":{\"repeats\":100,\"warmup\":5,\"mean_ms\":%.9g,\"p50_ms\":%.9g,\"p95_ms\":%.9g,\"max_ms\":%.9g,\"maxrss_kib\":%ld,\"sink\":%.9g,\"scope\":\"periodic Hann and FFT/PSD; ROI and file IO excluded\"}",total/100,d[50],d[94],d[99],usage.ru_maxrss,(double)sink);
#endif
    fprintf(meta,"}\n");int failed=ferror(psd)||ferror(meta);
    if(fclose(input))failed=1;
    if(fclose(psd))failed=1;
    if(fclose(meta))failed=1;
    return failed?2:0;
}
