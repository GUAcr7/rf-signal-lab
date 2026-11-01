/* P67 receive dashboard. Included after the frozen P56 policy and telemetry.
 * 8192 samples / eight Hann FFTs from the SAME source block as AI.
 * Record equal-tail 99% spectral interval is NOT detected-signal OBW.
 * Waterfall rows are displayed snapshots, never a continuous ADC time axis.
 */
#define P67_ROWS 96
#define P67_COLS 384
static unsigned char p67_history[P67_ROWS][P67_COLS];
static unsigned p67_rows, p67_head;
static double p67_times[P67_ROWS];
static uint64_t p67_sequences[P67_ROWS];
static double p67_power, p67_reference, p67_relative;
static double p67_low, p67_high, p67_mid, p67_width;
static int p67_nonzero;
static const int16_t *p67_iq;
static uint64_t p67_sequence;
static double p67_elapsed;

/* Piecewise constant power density inside FFT bins, in shifted-bin order. */
static double p67_quantile(const double *acc, double total, double fraction) {
    double cumulative=0, goal=total*fraction;
    for(int k=0;k<FFT_N;k++) {
        double power=acc[(k+FFT_N/2)%FFT_N];
        if(power>0 && cumulative+power>=goal)
            return k-.5+(goal-cumulative)/power;
        cumulative+=power;
    }
    return FFT_N-.5;
}
static void p67_measure(const int16_t *iq, const double *acc,
                        uint64_t sequence, double elapsed) {
    p67_iq=iq;p67_sequence=sequence;p67_elapsed=elapsed;
    p67_power=0;
    for(int n=0;n<8192;n++) {
        double i=iq[2*n],q=iq[2*n+1];p67_power+=i*i+q*q;
    }
    p67_power/=8192;
    double total=0;
    for(int k=0;k<FFT_N;k++)total+=acc[k];
    p67_nonzero=total>0 && isfinite(total) && panel_sample_rate_hz>0;
    p67_low=p67_high=p67_mid=p67_width=0;
    if(p67_nonzero) {
        double spacing=panel_sample_rate_hz/FFT_N;
        p67_low=(p67_quantile(acc,total,.005)-FFT_N/2)*spacing;
        p67_high=(p67_quantile(acc,total,.995)-FFT_N/2)*spacing;
        p67_mid=(p67_low+p67_high)/2;p67_width=p67_high-p67_low;
    }
    if(!p67_reference && p67_power>0)p67_reference=p67_power;
    p67_relative=p67_power>0 && p67_reference>0 ? 10*log10(p67_power/p67_reference) : 0;
    /* Fixed -20..70 dB re 1 count^2/bin; maximum bin for each display column. */
    for(int x=0;x<P67_COLS;x++) {
        int first=x*FFT_N/P67_COLS,last=(x+1)*FFT_N/P67_COLS;
        double maximum=0;
        for(int k=first;k<last;k++)maximum=fmax(maximum,acc[(k+FFT_N/2)%FFT_N]);
        double db=maximum>0?10*log10(maximum):-300;
        double level=(db+20)/90;
        p67_history[p67_head][x]=(unsigned char)lrint(255*fmax(0,fmin(1,level)));
    }
    p67_times[p67_head]=elapsed;p67_sequences[p67_head]=sequence;
    p67_head=(p67_head+1)%P67_ROWS;if(p67_rows<P67_ROWS)p67_rows++;
}
static uint32_t p67_colour(unsigned v) {
    if(v<64)return rgb(12,12+v,28+2*v);
    if(v<128)return rgb(12,76+2*(v-64),156);
    if(v<192)return rgb(12+3*(v-128),204,156-2*(v-128));
    return rgb(204+(v-192)*51/63,204+(v-192)*51/63,28);
}
static void p67_plot_line(int left,int top,int right,int bottom,
                          const double *values,int count,double low,double high,
                          uint32_t colour) {
    int px=0,py=0;
    for(int n=0;n<count;n++) {
        double fraction=fmax(0,fmin(1,(values[n]-low)/(high-low)));
        int x=left+(right-left)*n/(count-1);
        int y=bottom-(int)lrint((bottom-top)*fraction);
        if(n)bresenham(px,py,x,y,colour);
        px=x;py=y;
    }
}
static void p67_draw(const double *acc,const struct metrics *m,int channels,
                     size_t pairs,int iteration,double frame_ms,int frames) {
    (void)channels;(void)pairs;(void)iteration;(void)frame_ms;(void)frames;
    char line[128];fill(C_BG);
    text(16,10,"RF SIGNAL LAB | RX dashboard P67",C_ACCENT);
    hline(16,784,46,C_GRID);
    text(48,58,"I/Q: first 64 samples | counts",C_DIM);
    rect(48,78,368,208,C_GRID);hline(49,367,143,C_GRID);
    double iv[64],qv[64],limit=1;
    for(int n=0;n<64;n++) {
        iv[n]=p67_iq[2*n];qv[n]=p67_iq[2*n+1];
        limit=fmax(limit,fmax(fabs(iv[n]),fabs(qv[n])));
    }
    p67_plot_line(49,79,367,207,iv,64,-limit,limit,C_ACCENT);
    p67_plot_line(49,79,367,207,qv,64,-limit,limit,rgb(255,170,70));
    snprintf(line,sizeof line,"+/-%.0f | I blue Q orange | %.3f us",limit,63e6/panel_sample_rate_hz);
    text(48,214,line,C_DIM);
    text(448,58,"Spectrum | dB re 1 count^2/bin",C_DIM);
    rect(448,78,780,208,C_GRID);
    for(int g=1;g<3;g++)hline(449,779,78+130*g/3,C_GRID);
    double bins[FFT_N];
    for(int k=0;k<FFT_N;k++) {
        double p=acc[(k+FFT_N/2)%FFT_N];bins[k]=p>0?10*log10(p):-300;
    }
    p67_plot_line(449,79,779,207,bins,FFT_N,-20,70,C_TRACE);
    snprintf(line,sizeof line,"-%.2f .. +%.2f MHz | -20..70 dB",panel_sample_rate_hz/2e6,(FFT_N/2-1)*panel_sample_rate_hz/FFT_N/1e6);
    text(448,214,line,C_DIM);
    text(48,244,"Waterfall: displayed snapshots",C_DIM);
    rect(47,267,432,414,C_GRID);
    for(int y=268;y<=413;y++) {
        unsigned age=(unsigned)(413-y)*P67_ROWS/146;
        for(int x=0;x<P67_COLS;x++) {
            uint32_t c=C_BG;
            if(age<p67_rows) {
                unsigned row=(p67_head+P67_ROWS-1-age)%P67_ROWS;
                c=p67_colour(p67_history[row][x]);
            }
            put(48+x,y,c);
        }
    }
    text(48,420,"older top / newest bottom | gaps unknown",C_DIM);
    snprintf(line,sizeof line,"fixed colour: -20..70 dB | %u rows",p67_rows);
    text(48,436,line,C_DIM);
    text(456,244,"Record statistics (not target OBW)",C_ACCENT);
    snprintf(line,sizeof line,"Fs %.3f MS/s | FFT %d",panel_sample_rate_hz/1e6,FFT_N);text(456,268,line,C_FG);
    snprintf(line,sizeof line,"Spacing %.1f kHz | mean I^2+Q^2",panel_sample_rate_hz/FFT_N/1000);text(456,286,line,C_DIM);
    snprintf(line,sizeof line,"%.1f counts^2 | ref %.1f",p67_power,p67_reference);text(456,304,line,C_FG);
    if(p67_power>0)snprintf(line,sizeof line,"Relative %+.2f dB (first nonzero)",p67_relative);
    else snprintf(line,sizeof line,"Relative unavailable (zero input)");
    text(456,322,line,C_FG);
    if(p67_nonzero)snprintf(line,sizeof line,"Record 99%% width %.3f MHz",p67_width/1e6);
    else snprintf(line,sizeof line,"Record 99%% width unavailable");
    text(456,340,line,C_FG);
    if(p67_nonzero)snprintf(line,sizeof line,"Record midpoint %+.1f kHz",p67_mid/1000);
    else snprintf(line,sizeof line,"Record midpoint unavailable");
    text(456,358,line,C_FG);
    peak_offset_label(line,sizeof line,m->peak_offset_bins,m->peak_valid);
    char peak[128];snprintf(peak,sizeof peak,"Peak offset %.80s",line);text(456,376,peak,C_FG);
    snprintf(line,sizeof line,"8 FFTs / 8192 samples | %.3f ms",8192e3/panel_sample_rate_hz);text(456,394,line,C_DIM);
    text(456,412,"Power is digital, not calibrated dBm",C_DIM);
    text(456,430,"AI shares block; uses 65536 samples",C_DIM);
}
static int p67_evidence(const char *directory,const char *state) {
    char next[1024],final[1024];
    if(snprintf(next,sizeof next,"%s/dashboard.next",directory)>=(int)sizeof next
       ||snprintf(final,sizeof final,"%s/dashboard.json",directory)>=(int)sizeof final)return 1;
    FILE *f=new_file(directory,"dashboard.next");if(!f)return 1;
    fprintf(f,"{\"schema\":\"rfsig.dashboard.p67.v1\",\"state\":\"%s\","
        "\"source_block_sequence\":%" PRIu64 ",\"elapsed_software_s\":%.12g,"
        "\"sample_rate_hz\":%.12g,\"fft_spacing_hz\":%.12g,\"display_samples\":8192,"
        "\"iq_plot_samples\":64,\"AI_samples\":65536,\"mean_i2_q2_counts_squared\":%.17g,"
        "\"reference_first_nonzero_counts_squared\":%.17g,\"relative_power_db\":",
        state,p67_sequence,p67_elapsed,panel_sample_rate_hz,panel_sample_rate_hz/FFT_N,p67_power,p67_reference);
    if(p67_power>0 && p67_reference>0)fprintf(f,"%.17g",p67_relative);else fputs("null",f);
    fputs(",\"record_99_percent_width_hz\":",f);
    if(p67_nonzero)fprintf(f,"%.17g",p67_width);else fputs("null",f);
    fputs(",\"record_interval_midpoint_hz\":",f);
    if(p67_nonzero)fprintf(f,"%.17g",p67_mid);else fputs("null",f);
    fprintf(f,",\"waterfall_rows\":%u,\"waterfall_max_rows\":%d,"
        "\"waterfall_axis\":\"displayed_snapshots_not_ADC_time\","
        "\"target_bandwidth_validated\":false,\"absolute_RF_power_calibrated\":false,"
        "\"ADC_gaps\":\"unknown\",\"AI_state\":\"%s\",\"accepted_class\":%d}\n",
        p67_rows,P67_ROWS,p56_names[p56_state],p56_class);
    int bad=ferror(f);if(fclose(f))bad=1;
    if(bad||rename(next,final)){unlink(next);return 1;}return 0;
}
