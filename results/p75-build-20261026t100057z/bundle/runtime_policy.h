/* P56 quality/calibration policy. Frozen model and FIR math are unchanged.
 * Closed three-class operation only; these checks are not universal OOD detection.
 */
#include <ctype.h>
enum p56_state {P56_CAL_REQUIRED,P56_REFERENCE,P56_WAIT_PILOT,P56_NO_SIGNAL,
    P56_TONE,P56_UNCERTAIN,P56_CLASSIFIED,P56_CLIPPED,P56_STOPPED};
static const char *p56_names[]={"CALIBRATION_REQUIRED","REFERENCE","WAIT_PILOT",
    "NO_USABLE_SIGNAL","UNSUPPORTED_TONE","UNCERTAIN","CLASSIFIED","CLIPPED","STOPPED"};
static enum p56_state p56_state=P56_CAL_REQUIRED;
static char p56_boot[37],p56_token[33];
static unsigned char p56_reference[4][262144];
static int p56_reference_count,p56_pilot_count,p56_ready,p56_class=-1;
static double p56_fits[2],p56_noise,p56_ratio,p56_power,p56_cw,p56_nmse;
static double p56_fit_frequency;
static int p56_raw_labels[3]={-1,-1,-1};

static int p56_request_valid(const char *text,const char *boot,char *token) {
    char version[12],id[40],model[68],key[36],extra[2];
    if(sscanf(text,"%11s %39s %67s %35s %1s",version,id,model,key,extra)!=4
        ||strcmp(version,"P56CAL1")||strcmp(id,boot)||strcmp(model,AI_MODEL_SHA)||strlen(key)!=32)return 0;
    for(int i=0;i<32;i++)if(!isxdigit((unsigned char)key[i]))return 0;
    memcpy(token,key,33);return 1;
}
static int p56_read_request(char *token) {
    const char *path=getenv("P56_CONTROL_FILE");if(!path)path="/run/rfsig-ai/control";
    FILE *f=fopen(path,"rb");if(!f)return 0;
    char text[256];size_t n=fread(text,1,sizeof text-1,f);int eof=fgetc(f)==EOF;fclose(f);text[n]=0;
    return eof && !memchr(text,0,n) && p56_request_valid(text,p56_boot,token);
}
static void p56_reset(void) {
    p56_reference_count=p56_pilot_count=p56_ready=0;p56_noise=0;ai_if_hz=0;p56_class=-1;
    p56_state=P56_CAL_REQUIRED;
    memset(p56_frame_powers,0,sizeof p56_frame_powers);
    memset(ai_logits,0,sizeof ai_logits);
}
static int p56_initialize(void) {
    FILE *f=fopen("/proc/sys/kernel/random/boot_id","r");if(!f)return 1;
    int ok=fscanf(f,"%36s",p56_boot)==1;fclose(f);
    if(!ok||strlen(p56_boot)!=36)return 1;
    p56_reset();return 0;
}
/* Same linear-phase tone fit as the Python reference. No classifier scores,
 * modulation labels, pilot payload matching or absolute RF calibration. */
static int p56_fit_tone(void) {
    double previous=0,unwrapped=0,sum=0,sum_ny=0;
    for(int n=0;n<65536;n++) {
        int i=(int)((packed[2*n]&4095)^2048)-2048;
        int q=(int)((packed[2*n+1]&4095)^2048)-2048;
        double angle=atan2(q,i);
        if(n){double d=angle-previous;if(d>M_PI)d-=2*M_PI;if(d< -M_PI)d+=2*M_PI;unwrapped+=d;}
        else unwrapped=angle;
        previous=angle;sum+=unwrapped;sum_ny+=n*unwrapped;
    }
    const double center=32767.5,ss=65536.0*(65536.0*65536.0-1)/12;
    double frequency=(sum_ny-center*sum)/ss*30720000/(2*M_PI);
    if(!isfinite(frequency)||fabs(frequency-960000)>50000)return 0;
    mix_block(frequency);double mi=0,mq=0,power=0;
    for(int n=0;n<65536;n++){mi+=mixed_i[n];mq+=mixed_q[n];power+=mixed_i[n]*mixed_i[n]+mixed_q[n]*mixed_q[n];}
    mi/=65536;mq/=65536;power/=65536;
    double coherent=mi*mi+mq*mq;
    if(!(power>0)||!(coherent>0))return 0;
    double residual=fmax(0,power-coherent),nmse=10*log10(fmax(residual/coherent,1e-30));
    p56_cw=coherent/power;p56_nmse=nmse;p56_fit_frequency=frequency;
    return nmse<=-20;
}
static int p56_clipped(void) {
    for(int n=0;n<131072;n++){int v=packed[n]&4095;if(v==2047||v==2048)return 1;}
    return 0;
}
static int p56_step(const unsigned char *input) {
    p56_class=-1;p56_ratio=p56_power=p56_cw=0;p56_nmse=0;
    for(int i=0;i<3;i++)p56_raw_labels[i]=-1;
    char token[33];
    if(!p56_read_request(token)){p56_reset();return 0;}
    if(strcmp(token,p56_token)){strcpy(p56_token,token);p56_reset();p56_state=P56_REFERENCE;}
    if(p56_reference_count<4){memcpy(p56_reference[p56_reference_count++],input,262144);p56_state=p56_reference_count==4?P56_WAIT_PILOT:P56_REFERENCE;return 0;}
    memcpy(packed,input,262144);
    if(!p56_ready) {
        p56_state=P56_WAIT_PILOT;
        if(!p56_fit_tone()){p56_pilot_count=0;return 0;}
        p56_fits[p56_pilot_count++]=p56_fit_frequency;
        if(p56_pilot_count<2)return 0;
        p56_pilot_count=0;
        if(fabs(p56_fits[0]-p56_fits[1])>100)return 0;
        ai_if_hz=(p56_fits[0]+p56_fits[1])/2;
        p56_noise=0;
        for(int k=0;k<4;k++) {
            memcpy(packed,p56_reference[k],262144);
            if(infer_block(ai_if_hz,!strcmp(AI_MODE,"int8"),0))return 1;
            for(int j=0;j<3;j++)p56_noise=fmax(p56_noise,p56_frame_powers[j]);
        }
        if(!isfinite(p56_noise)||p56_noise<=1e-20){p56_reset();return 0;}
        p56_ready=1;
    }
    memcpy(packed,input,262144);
    if(p56_clipped()){p56_state=P56_CLIPPED;return 0;}
    int tone=p56_fit_tone();
    if(infer_block(ai_if_hz,!strcmp(AI_MODE,"int8"),0))return 1;
    double minimum=p56_frame_powers[0];p56_power=0;
    for(int j=0;j<3;j++){minimum=fmin(minimum,p56_frame_powers[j]);p56_power+=p56_frame_powers[j]/3;p56_raw_labels[j]=ai_predictions[j];}
    p56_ratio=minimum/p56_noise;
    if(tone){p56_state=P56_TONE;return 0;}
    if(!isfinite(p56_ratio)||p56_ratio<10){p56_state=P56_NO_SIGNAL;return 0;}
    if(ai_predictions[0]<0||ai_predictions[0]!=ai_predictions[1]||ai_predictions[1]!=ai_predictions[2]){p56_state=P56_UNCERTAIN;return 0;}
    p56_class=ai_predictions[0];p56_state=P56_CLASSIFIED;return 0;
}
