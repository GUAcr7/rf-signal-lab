/* Bounded evidence: 4096 records at most. No probabilities are displayed. */
static FILE *p56_history;
static unsigned p56_records;
static double p56_begin;
static int p56_evidence(const char *directory,uint64_t sequence) {
    char next[1024],final[1024],row[2048];
    if(snprintf(next,sizeof next,"%s/ai.next",directory)>=(int)sizeof next
       ||snprintf(final,sizeof final,"%s/ai.json",directory)>=(int)sizeof final)return 1;
    int n=snprintf(row,sizeof row,
        "{\"schema\":\"rfsig.runtime_AI.v1\",\"state\":\"%s\",\"accepted_class\":%d,"
        "\"source_block_sequence\":%" PRIu64 ",\"elapsed_s\":%.9g,\"common_IF_hz\":%.17g,"
        "\"boot_id\":\"%s\",\"calibration_token\":\"%s\",\"model_sha256\":\"%s\","
        "\"ready\":%s,\"background_power_reference\":%.17g,\"minimum_power_ratio\":%.17g,"
        "\"frame_powers\":[%.17g,%.17g,%.17g],\"raw_predictions\":[%d,%d,%d],"
        "\"full_policy_frontend_CNN_ms\":%.9g,\"pilot_fits\":%d,\"references\":%d,"
        "\"universal_unknown_rejection\":false,\"confidence_calibrated\":false}\n",
        p56_names[p56_state],p56_class,sequence,now_s()-p56_begin,ai_if_hz,
        p56_boot,p56_token,AI_MODEL_SHA,p56_ready?"true":"false",p56_noise,p56_ratio,
        p56_frame_powers[0],p56_frame_powers[1],p56_frame_powers[2],
        p56_raw_labels[0],p56_raw_labels[1],p56_raw_labels[2],ai_ms,p56_pilot_count,p56_reference_count);
    if(n<0||n>=(int)sizeof row)return 1;
    FILE *f=new_file(directory,"ai.next");if(!f)return 1;
    int bad=fwrite(row,1,n,f)!=(size_t)n;if(fclose(f))bad=1;
    if(bad||rename(next,final)){unlink(next);return 1;}
    if(!p56_history){p56_history=new_file(directory,"ai-history.jsonl");if(!p56_history)return 1;}
    if(p56_records>=4096)return 1; /* stop rather than silently discard evidence */
    p56_records++;
    return fwrite(row,1,n,p56_history)!=(size_t)n||fflush(p56_history);
}
static void p56_line(void) {
    const char *names[]={"BPSK","QPSK","16QAM"};char line[128];
    if(p56_class>=0)snprintf(line,sizeof line,"AI: %s | %.1f ms | controlled 3 classes",names[p56_class],ai_ms);
    else snprintf(line,sizeof line,"AI: %s | controlled 3 classes",p56_names[p56_state]);
    latest_line(PANEL_H-24,line);
}
/* Up to sixteen explicitly requested, same-update IQ/pixel/decision triplets. */
static int p56_shot(const char *directory,const unsigned char *input,int have_fb) {
    static unsigned last;
    const char *path=getenv("P56_SHOT_FILE");if(!path)return 0;
    FILE *request=fopen(path,"r");if(!request)return 0;
    unsigned id=0;char extra;int count=fscanf(request,"%u %c",&id,&extra);fclose(request);
    if(count!=1||id<=last||id>16)return 0;
    char name[64];snprintf(name,sizeof name,"shot-%02u.bin",id);
    FILE *f=new_file(directory,name);if(!f)return 1;
    int bad=fwrite(input,1,262144,f)!=262144;if(fclose(f))bad=1;
    if(have_fb) {
        snprintf(name,sizeof name,"shot-%02u.raw",id);f=new_file(directory,name);if(!f)return 1;
        for(int y=0;y<PANEL_H;y++)if(fwrite(fb+(size_t)y*fb_stride_words,4,PANEL_W,f)!=PANEL_W)bad=1;
        if(fclose(f))bad=1;
    }
    snprintf(name,sizeof name,"shot-%02u.json",id);f=new_file(directory,name);if(!f)return 1;
    char source[1024];snprintf(source,sizeof source,"%s/ai.json",directory);
    FILE *in=fopen(source,"rb");if(!in){fclose(f);return 1;}
    char bytes[2048];size_t n=fread(bytes,1,sizeof bytes,in);
    if(ferror(in)||!feof(in)||fwrite(bytes,1,n,f)!=n)bad=1;
    if(fclose(in))bad=1;
    if(fclose(f))bad=1;
    last=id;return bad;
}
