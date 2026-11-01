/* Label-free controlled RF frontend + frozen model; files only, no IIO/RF writes. */
#define main single_frame_cli_main
#include "trained_cnn_infer.c"
#undef main
#include "phase_pool.h"
#include "rf_frontend.h"

static uint16_t packed[131072];
static double mixed_i[65536],mixed_q[65536];
static void mix_block(double frequency) {
    double c=cos(-2*3.14159265358979323846*frequency/30720000.0);
    double s=sin(-2*3.14159265358979323846*frequency/30720000.0),a=1,b=0;
    for(int n=0;n<65536;n++) {
        int i=(int)((packed[2*n]&4095)^2048)-2048;
        int q=(int)((packed[2*n+1]&4095)^2048)-2048;
        mixed_i[n]=i*a-q*b;mixed_q[n]=i*b+q*a;
        double next=a*c-b*s;b=a*s+b*c;a=next;
        if((n&4095)==4095){double norm=hypot(a,b);a/=norm;b/=norm;}
    }
}
static int infer_block(double frequency,int quantized,int emit) {
    mix_block(frequency);
    for(int frame=0;frame<3;frame++) {
        for(int n=0;n<1024;n++) {
            int start=16*(frame*1024+n);double i=0,q=0;
            for(int k=0;k<513;k++) {
                int at=start+512-k;i+=rf_taps[k]*mixed_i[at];q+=rf_taps[k]*mixed_q[at];
            }
            original[2*n]=(float)i;original[2*n+1]=(float)q;
        }
        if(p74_infer(quantized)) return 2;
        int predicted=0;for(int k=1;k<3;k++)if(logits[k]>logits[predicted])predicted=k;
        if(emit) printf("%d,%.17g,%.17g,%.17g,%d\n",frame,logits[0],logits[1],logits[2],predicted);
    }
    return 0;
}
int main(int argc,char **argv) {
    if(argc<4 || argc>5 || (strcmp(argv[3],"fp32") && strcmp(argv[3],"int8")) || (argc==5 && strcmp(argv[4],"--bench")))return 2;
    char *end=NULL;double frequency=strtod(argv[2],&end);
    if(!*argv[2] || *end || !isfinite(frequency) || fabs(frequency-960000)>50000 || fesetround(FE_TONEAREST))return 2;
    FILE *f=fopen(argv[1],"rb");if(!f)return 2;
    int complete=fread(packed,sizeof(uint16_t),131072,f)==131072 && fgetc(f)==EOF;fclose(f);
    if(!complete)return 2;
    int q=!strcmp(argv[3],"int8");if(infer_block(frequency,q,1))return 2;
    if(argc==5) {
#ifdef _WIN32
        return 2;
#else
        double total=0,max=0;
        for(int i=0;i<10;i++) {
            double t=seconds();if(infer_block(frequency,q,0))return 2;
            double ms=1000*(seconds()-t);total+=ms;if(ms>max)max=ms;
        }
        struct rusage usage;if(getrusage(RUSAGE_SELF,&usage))return 2;
        printf("{\"repeats\":10,\"mean_block_ms\":%.9g,\"max_block_ms\":%.9g,\"frames_per_block\":3,\"maxrss_kib\":%ld,\"scope\":\"mix/FIR/decimation/DC/RMS/CNN; file IO excluded\"}\n",total/10,max,usage.ru_maxrss);
#endif
    }
    return 0;
}
