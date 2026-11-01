#define AI_IF_HZ 993800.0
#define AI_MODE "int8"
#define AI_MODEL_SHA "old_weights_probe_only"
/* Label-free controlled RF frontend + frozen model; files only, no IIO/RF writes. */
#define main single_frame_cli_main
#include "trained_cnn_infer.c"
#undef main
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
        if(infer(quantized)) return 2;
        int predicted=0;for(int k=1;k<3;k++)if(logits[k]>logits[predicted])predicted=k;
        ai_predictions[frame]=predicted;memcpy(ai_logits[frame],logits,sizeof logits);
        if(emit) printf("%d,%.17g,%.17g,%.17g,%d\n",frame,logits[0],logits[1],logits[2],predicted);
    }
    return 0;
}
