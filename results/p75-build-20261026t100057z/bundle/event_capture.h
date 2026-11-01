/* Opt-in RAM diagnostics, after frozen policy/metrics/evidence/draw complete.
 * Twelve IQ+AI+metric triplets maximum: three per decision type/age window.
 * Never changes a prediction, calibration, waveform, PHY or acceptance rule.
 */
struct p73_capture_state {
    unsigned total, count[2][2];
    uint64_t last_sequence;
    double last_time[2][2], active_since;
};
static struct p73_capture_state p73_capture={.active_since=-1};

static int p73_read_row(const char *directory,const char *name,char *row,size_t size,uint64_t sequence) {
    char path[1024];
    if(snprintf(path,sizeof path,"%s/%s",directory,name)>=(int)sizeof path)return 1;
    FILE *f=fopen(path,"rb");if(!f)return 1;
    size_t n=fread(row,1,size-1,f);int bad=ferror(f)||fgetc(f)!=EOF;row[n]=0;
    if(fclose(f))bad=1;
    const char *key=strstr(row,"\"source_block_sequence\":");
    if(!key||strtoull(key+24,NULL,10)!=sequence)bad=1;
    return bad;
}
static int p73_row_file(const char *directory,const char *name,const char *row) {
    FILE *f=new_file(directory,name);if(!f)return 1;
    size_t n=strlen(row);int bad=fwrite(row,1,n,f)!=n;if(fclose(f))bad=1;return bad;
}
static int p73_event(const char *directory,const unsigned char *input) {
    const char *enabled=getenv("P73_EVENT_CAPTURE");
    if(!enabled||strcmp(enabled,"1"))return 0;
    int eligible=p56_ready&&(p56_state==P56_UNCERTAIN||p56_state==P56_CLASSIFIED);
    if(!isfinite(p67_elapsed)||p67_elapsed<0)return 1;
    if(!eligible){p73_capture.active_since=-1;return 0;}
    if(p73_capture.active_since<0)p73_capture.active_since=p67_elapsed;
    if(p67_elapsed-p73_capture.active_since<2)return 0;
    unsigned phase=p67_elapsed>=120,kind=p56_state==P56_UNCERTAIN;
    if(p73_capture.total>=12||p73_capture.count[phase][kind]>=3||
       (p73_capture.count[phase][kind]&&p67_elapsed-p73_capture.last_time[phase][kind]<2)||
       p67_sequence<=p73_capture.last_sequence)return 0;
    /* Validate both current evidence rows before creating a snapshot. */
    char ai[4096],metrics[4096],name[64],path[1024];
    if(p73_read_row(directory,"ai.json",ai,sizeof ai,p67_sequence)||
       p73_read_row(directory,"metrics.json",metrics,sizeof metrics,p67_sequence))return 1;
    unsigned id=p73_capture.total+1;
    snprintf(name,sizeof name,"event-%02u.bin",id);
    FILE *f=new_file(directory,name);if(!f)return 1;
    int bad=fwrite(input,1,262144,f)!=262144;if(fclose(f))bad=1;
    if(bad)return 1;
    snprintf(name,sizeof name,"event-%02u.json",id);
    if(p73_row_file(directory,name,ai))return 1;
    snprintf(name,sizeof name,"event-%02u.metrics.json",id);
    if(p73_row_file(directory,name,metrics))return 1;
    if(snprintf(path,sizeof path,"%s/event-history.jsonl",directory)>=(int)sizeof path)return 1;
    f=fopen(path,"ab");if(!f)return 1;
    bad=fprintf(f,"{\"id\":%u,\"source_block_sequence\":%" PRIu64 ",\"elapsed_s\":%.17g,"
        "\"state\":\"%s\",\"age_window\":%u,\"same_update_capture\":true}\n",
        id,p67_sequence,p67_elapsed,p56_names[p56_state],phase)<0;
    if(fclose(f))bad=1;
    if(bad)return 1;
    p73_capture.total=id;p73_capture.count[phase][kind]++;
    p73_capture.last_sequence=p67_sequence;p73_capture.last_time[phase][kind]=p67_elapsed;
    return 0;
}
