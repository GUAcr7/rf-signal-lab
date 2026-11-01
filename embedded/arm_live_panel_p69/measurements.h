#include "roi_math.h"
static struct p69_result p69_result={.status=P69_CAL_REQUIRED};
static double p69_background[FFT_N],p69_lo;
static char p69_cached_token[33];
static FILE *p69_history;
static unsigned p69_records;

static void p69_measure(const double *acc,const float *window) {
    p69_result=(struct p69_result){.status=P69_CAL_REQUIRED};
    if(!p56_ready)return;
    if(strcmp(p69_cached_token,p56_token)) {
        int16_t raw[8192*2];double power[FFT_N];struct metrics m;
        memset(p69_background,0,sizeof p69_background);
        for(int r=0;r<4;r++) {
            for(int n=0;n<8192*2;n++) {
                unsigned v=(p56_reference[r][2*n]|((unsigned)p56_reference[r][2*n+1]<<8))&4095;
                raw[n]=(int16_t)(v>=2048?(int)v-4096:(int)v);
            }
            spectrum(raw,8192,2,8,0,window,power,&m);
            for(int k=0;k<FFT_N;k++)p69_background[k]+=power[k]/4;
        }
        memcpy(p69_cached_token,p56_token,33);
    }
    if(p56_state==P56_NO_SIGNAL){p69_result.status=P69_NO_SIGNAL;return;}
    if(p56_state==P56_CLIPPED){p69_result.status=P69_CLIPPED;return;}
    if(p56_state==P56_STOPPED){p69_result.status=P69_STOPPED;return;}
    int allowed=p56_state==P56_TONE||p56_state==P56_CLASSIFIED||p56_state==P56_UNCERTAIN;
    p69_result=p69_compute(acc,p69_background,FFT_N,panel_sample_rate_hz,p69_lo,ai_if_hz,allowed);
}
static void p69_draw_metrics(void) {
    for(int y=242;y<450;y++)for(int x=448;x<790;x++)put(x,y,C_BG);
    char line[128];text(456,244,"Controlled single-source ROI",C_ACCENT);
    snprintf(line,sizeof line,"Fs %.3f MS/s | bin %.1f kHz",panel_sample_rate_hz/1e6,panel_sample_rate_hz/FFT_N/1000);text(456,268,line,C_DIM);
    snprintf(line,sizeof line,"State: %s",p69_names[p69_result.status]);text(456,286,line,C_FG);
    if(p69_result.status==P69_OK) {
        snprintf(line,sizeof line,"LO+center %.3f MHz",p69_result.rf/1e6);text(456,308,line,C_FG);
        snprintf(line,sizeof line,"99%% ROI BW %.1f kHz",p69_result.width/1000);text(456,328,line,C_FG);
        snprintf(line,sizeof line,"Center offset %+.1f kHz",p69_result.midpoint/1000);text(456,348,line,C_FG);
        snprintf(line,sizeof line,"ROI power %.1f counts^2",p69_result.power);text(456,368,line,C_FG);
        snprintf(line,sizeof line,"Above background %+.1f dB",10*log10(p69_result.ratio));text(456,388,line,C_FG);
    } else {
        text(456,308,"LO+center: unavailable",C_DIM);text(456,328,"99% ROI BW: unavailable",C_DIM);
        text(456,348,"Power/center suppressed",C_DIM);
        text(456,368,"Needs fresh background + pilot",C_DIM);
    }
    text(456,412,"Window: pilot IF +/-600 kHz",C_DIM);
    text(456,430,"No dBm / absolute RF calibration",C_DIM);
}
static void p69_draw(const double *acc,const struct metrics *m,int channels,
        size_t pairs,int iteration,double frame_ms,int frames) {
    p67_draw(acc,m,channels,pairs,iteration,frame_ms,frames);
    for(int y=10;y<22;y++)for(int x=16;x<784;x++)put(x,y,C_BG);
    text(16,10,"RF SIGNAL LAB | RX measurements P69",C_ACCENT);p69_draw_metrics();
}
static int p69_write_json(FILE *f,const char *state) {
    fprintf(f,"{\"schema\":\"rfsig.controlled_ROI.p69.v1\",\"state\":\"%s\","
        "\"source_block_sequence\":%" PRIu64 ",\"elapsed_software_s\":%.12g,"
        "\"calibration_token\":\"%s\",\"AI_state\":\"%s\",\"accepted_class\":%d,"
        "\"measurement_status\":\"%s\",\"valid\":%s,\"sample_rate_hz\":%.12g,"
        "\"fft_spacing_hz\":%.12g,\"rx_LO_readback_hz\":%.12g,",
        state,p67_sequence,p67_elapsed,p56_token,p56_names[p56_state],p56_class,
        p69_names[p69_result.status],p69_result.status==P69_OK?"true":"false",panel_sample_rate_hz,panel_sample_rate_hz/FFT_N,p69_lo);
    if(p69_result.status==P69_OK)fprintf(f,"\"center_offset_hz\":%.17g,\"LO_plus_center_hz\":%.17g,"
        "\"ROI_99_width_hz\":%.17g,\"ROI_power_counts_squared\":%.17g,\"background_ROI_power\":%.17g,"
        "\"power_ratio\":%.17g,",p69_result.midpoint,p69_result.rf,p69_result.width,p69_result.power,p69_result.background,p69_result.ratio);
    else fputs("\"center_offset_hz\":null,\"LO_plus_center_hz\":null,\"ROI_99_width_hz\":null,"
        "\"ROI_power_counts_squared\":null,\"background_ROI_power\":null,\"power_ratio\":null,",f);
    fputs("\"scope\":\"known_single_source_pilot_IF_plus_minus_600kHz\",\"noise_subtracted\":false,"
        "\"absolute_RF_frequency_calibrated\":false,\"RF_power_dbm_calibrated\":false,\"ADC_gaps\":\"unknown\"}\n",f);
    return ferror(f)?1:0;
}
static int p69_evidence(const char *directory,const char *state,int display) {
    if(strcmp(state,"running")){p69_result=(struct p69_result){.status=P69_STOPPED};if(display)p69_draw_metrics();}
    char next[1024],final[1024];
    if(snprintf(next,sizeof next,"%s/metrics.next",directory)>=(int)sizeof next
        ||snprintf(final,sizeof final,"%s/metrics.json",directory)>=(int)sizeof final)return 1;
    FILE *f=new_file(directory,"metrics.next");if(!f)return 1;
    int bad=p69_write_json(f,state);if(fclose(f))bad=1;
    if(bad||rename(next,final)){unlink(next);return 1;}
    if(!p69_history){p69_history=new_file(directory,"metrics-history.jsonl");if(!p69_history)return 1;}
    if(p69_records++>=4096||p69_write_json(p69_history,state)||fflush(p69_history))return 1;
    if(strcmp(state,"running")){bad=fclose(p69_history);p69_history=NULL;return bad;}
    return 0;
}
static int p69_shot(const char *directory) {
    static unsigned last;const char *request=getenv("P56_SHOT_FILE");if(!request)return 0;
    FILE *f=fopen(request,"r");if(!f)return 0;
    unsigned id=0;char extra;int count=fscanf(f,"%u %c",&id,&extra);fclose(f);
    if(count!=1||id<=last||id>16)return 0;
    /* A request can change between the AI shot and this hook. Only attach
     * metrics if that AI snapshot was actually saved from this same block. */
    char ai_path[1024],row[2048];
    if(snprintf(ai_path,sizeof ai_path,"%s/shot-%02u.json",directory,id)>=(int)sizeof ai_path)return 1;
    f=fopen(ai_path,"rb");if(!f)return 0;
    size_t n=fread(row,1,sizeof row-1,f);row[n]=0;fclose(f);
    char *key=strstr(row,"\"source_block_sequence\":");
    if(!key||strtoull(key+24,NULL,10)!=p67_sequence)return 0;
    char name[64];snprintf(name,sizeof name,"shot-%02u.metrics.json",id);
    f=new_file(directory,name);if(!f)return 1;
    int bad=p69_write_json(f,"running");if(fclose(f))bad=1;last=id;return bad;
}
