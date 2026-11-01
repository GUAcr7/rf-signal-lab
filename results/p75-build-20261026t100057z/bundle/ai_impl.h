static double ai_if_hz;
#define AI_IF_HZ ai_if_hz
#define AI_MODE "int8"
#define AI_MODEL_SHA "bd571ef0d30b76cdb8138d3ebd90f55463eb5439bd4c78636555bc8800873457"
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
static double p56_frame_powers[3];
static int ai_predictions[3];
static double ai_logits[3][3];
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
        double mi=0,mq=0,p=0;
        for(int j=0;j<1024;j++){mi+=original[2*j];mq+=original[2*j+1];}
        mi/=1024;mq/=1024;
        for(int j=0;j<1024;j++){double i=original[2*j]-mi,q=original[2*j+1]-mq;p+=i*i+q*q;}
        p56_frame_powers[frame]=p/1024;
        if(p74_infer(quantized)){ai_predictions[frame]=-1;memset(ai_logits[frame],0,sizeof ai_logits[frame]);continue;}
        int predicted=0;for(int k=1;k<3;k++)if(logits[k]>logits[predicted])predicted=k;
        ai_predictions[frame]=predicted;memcpy(ai_logits[frame],logits,sizeof logits);
        if(emit) printf("%d,%.17g,%.17g,%.17g,%d\n",frame,logits[0],logits[1],logits[2],predicted);
    }
    return 0;
}
