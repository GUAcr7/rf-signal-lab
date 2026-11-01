/* Offline fixture runner. Includes the actual candidate, no substitute policy. */
#include "test_monitor.c"
int main(int argc,char **argv) {
    if(argc!=3||setenv("P56_CONTROL_FILE",argv[2],1)||p56_initialize())return 2;
    FILE *script=fopen(argv[1],"r");if(!script)return 2;
    char operation[8],path[1024];unsigned index=0;
    while(fscanf(script,"%7s %1023s",operation,path)==2) {
        if(strcmp(operation,"keep")) {
            if(!strcmp(operation,"absent"))unlink(argv[2]);
            else {
                FILE *f=fopen(argv[2],"wb");if(!f)return 2;
                const char *boot=!strcmp(operation,"stale")?"00000000-0000-0000-0000-000000000000":p56_boot;
                const char *model=!strcmp(operation,"model")?"bad":AI_MODEL_SHA;
                const char *key=!strcmp(operation,"renew")?"11111111111111111111111111111111":"00000000000000000000000000000000";
                fprintf(f,"P56CAL1 %s %s %s\n",boot,model,key);if(fclose(f))return 2;
            }
        }
        unsigned char input[262144];FILE *f=fopen(path,"rb");if(!f)return 2;
        size_t n=fread(input,1,sizeof input,f);int end=fgetc(f);fclose(f);
        if(n!=sizeof input||end!=EOF||p56_step(input))return 3;
        printf("{\"index\":%u,\"state\":\"%s\",\"accepted_class\":%d,\"common_IF_hz\":%.17g,"
            "\"minimum_power_ratio\":%.17g,\"noise_reference\":%.17g,\"tone_nmse_db\":%.17g,"
            "\"frame_powers\":[%.17g,%.17g,%.17g],\"predictions\":[%d,%d,%d],"
            "\"logits\":[[%.17g,%.17g,%.17g],[%.17g,%.17g,%.17g],[%.17g,%.17g,%.17g]]}\n",
            index++,p56_names[p56_state],p56_class,ai_if_hz,p56_ratio,p56_noise,p56_nmse,
            p56_frame_powers[0],p56_frame_powers[1],p56_frame_powers[2],
            p56_raw_labels[0],p56_raw_labels[1],p56_raw_labels[2],
            ai_logits[0][0],ai_logits[0][1],ai_logits[0][2],ai_logits[1][0],ai_logits[1][1],ai_logits[1][2],ai_logits[2][0],ai_logits[2][1],ai_logits[2][2]);
    }
    fclose(script);return 0;
}
