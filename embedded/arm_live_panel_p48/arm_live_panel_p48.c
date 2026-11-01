/* P48 display revision of the P42 RX engine. Acquisition/lifecycle unchanged.
 * One RX context/buffer for a bounded session or until SIGTERM (duration=0).
 * Constant-size atomic progress replaces per-frame stdout history.
 * separates refill from LCD pacing. UI overwrites are counted explicitly.
 * No ADC counter is present: hardware gaps and losslessness remain unproven.
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#define main full_recorder_main
#include "../arm_rx_full_p36/arm_rx_full_p36.c"
#undef main
#define main saved_panel_main
#include "../arm_panel_p48/arm_panel.c"
#undef main
#include <stdatomic.h>
#include <inttypes.h>

#define PREFIX_FRAMES 8192u
#define PREFIX_BYTES (PREFIX_FRAMES * FRAME_BYTES)
struct latest {
    struct iio_buffer *buffer;
    struct iio_channel *i, *q;
    pthread_mutex_t mutex;
    atomic_bool stop;
    int done, error;
    uint64_t published, consumed, consumed_sequence, overwritten;
    unsigned char packed[PREFIX_BYTES];
};

static void *latest_worker(void *opaque) {
    struct latest *s = opaque;
    int error = 0;
    while (!atomic_load(&s->stop)) {
        ssize_t count = fn_iio_buffer_refill(s->buffer);
        if (count < 0) { if (!atomic_load(&s->stop)) error = (int)count; break; }
        unsigned char *i = fn_iio_buffer_first(s->buffer, s->i);
        unsigned char *q = fn_iio_buffer_first(s->buffer, s->q);
        unsigned char *end = fn_iio_buffer_end(s->buffer);
        if (count != BLOCK_BYTES || !i || !q || !end || q != i+2
                || end-i != BLOCK_BYTES || fn_iio_buffer_step(s->buffer) != FRAME_BYTES) {
            error = -EINVAL; break;
        }
        pthread_mutex_lock(&s->mutex);
        if (s->published != s->consumed_sequence) s->overwritten++;
        memcpy(s->packed, i, PREFIX_BYTES);
        s->published++;
        pthread_mutex_unlock(&s->mutex);
    }
    pthread_mutex_lock(&s->mutex); s->error = error; s->done = 1; pthread_mutex_unlock(&s->mutex);
    return NULL;
}

static void latest_line(int y, const char *line) {
    for (int r = y; r < y+FONT_H && r < PANEL_H; r++)
        for (int x = 16; x < PANEL_W-16; x++) put(x, r, C_BG);
    text(16, y, line, C_DIM);
}

static void decode_latest(const unsigned char *packed, int16_t *iq) {
    for (size_t n = 0; n < PREFIX_FRAMES*2; n++) {
        int low = (packed[n*2] | ((unsigned int)packed[n*2+1]<<8)) & 4095u;
        iq[n] = (int16_t)(low >= 2048 ? low-4096 : low);
    }
}

static int save_progress(const char *directory, struct latest *s, int mutex_ready,
                         const char *state, const char *reason, int duration_ms,
                         int updates, double elapsed, const struct metrics *m) {
    uint64_t published, consumed, sequence, skipped;
    if (mutex_ready) pthread_mutex_lock(&s->mutex);
    published=s->published; consumed=s->consumed; sequence=s->consumed_sequence; skipped=s->overwritten;
    if (mutex_ready) pthread_mutex_unlock(&s->mutex);
    struct rusage resources = {0};
    if (getrusage(RUSAGE_SELF, &resources)) return 1;
    char temporary[1024], final[1024];
    if (snprintf(temporary, sizeof temporary, "%s/progress.next", directory) >= (int)sizeof temporary
        || snprintf(final, sizeof final, "%s/progress.json", directory) >= (int)sizeof final) return 1;
    FILE *f = new_file(directory, "progress.next");
    if (!f) return 1;
    fprintf(f, "{\"schema\":\"rfsig.live_progress.v1\",\"state\":\"%s\",\"reason\":\"%s\","
        "\"duration_ms_requested\":%d,\"elapsed_software_s\":%.9g,\"display_updates\":%d,"
        "\"published_prefixes\":%" PRIu64 ",\"consumed_prefixes\":%" PRIu64 ","
        "\"last_display_sequence\":%" PRIu64 ",\"UI_overwritten_prefixes\":%" PRIu64 ","
        "\"pending_prefixes\":%d,\"maxrss_kib\":%ld,\"peak_db\":%.9g,"
        "\"rms_per_component_counts\":%.12g,\"ADC_gaps\":\"unknown\",\"lossless_proven\":false}\n",
        state,reason,duration_ms,elapsed,updates,published,consumed,sequence,skipped,published!=sequence,
        resources.ru_maxrss,m->peak_db,m->rms);
    long bytes=ftell(f);int bad=ferror(f) || bytes<0 || bytes>4096;
    if (fclose(f)) bad=1;
    if (bad || rename(temporary,final)) { unlink(temporary); return 1; }
    return 0;
}

int main(int argc, char **argv) {
    int arg = 1, analyse_only = 0, duration_ms, interval_ms;
    if (argc > 1 && !strcmp(argv[1], "--analyse-only")) { analyse_only = 1; arg++; }
    if (argc != arg+3 || number(argv[arg+1], 0, 86400000, &duration_ms)
            || number(argv[arg+2], 100, 1000, &interval_ms) || strlen(argv[arg]) > 800) {
        fprintf(stderr, "usage: arm-live-panel-p42 [--analyse-only] NEW_DIRECTORY DURATION_MS_0_UNTIL_SIGNAL_OR_UP_TO_86400000 UI_INTERVAL_MS_100_1000\n");
        return 2;
    }
    if (mkdir(argv[arg], 0700)) { perror("new directory"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct latest s = {0}; atomic_init(&s.stop, false);
    struct iio_context *ctx = NULL;
    struct iio_device *adc = NULL, *phy = NULL;
    void *library = NULL, *map = NULL;
    size_t map_length = 0, map_start = 0;
    int status = 1, ffd = -1, mutex_ready = 0, worker_started = 0, worker_joined = 0;
    int before_ok = 0, after_ok = 0, updates = 0, buffer_created = 0;
    int progress_error = 0;
    uint64_t progress_commits = 0;
    struct metrics last = {0};
    double last_analysis_ms = 0, last_draw_ms = 0, last_compute_ms = 0;
    const char *reason = "setup_failed";
    struct rf_state before = {0}, after = {0};
    pthread_t worker;
    unsigned char shown[PREFIX_BYTES];
    int16_t iq[PREFIX_FRAMES*2];
    float window[FFT_N]; double acc[FFT_N];
    double begin = now_s(), elapsed = 0, next_update = 0;
    struct sigaction action = {0}; action.sa_handler = stop_handler; sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) goto release;
    if (pthread_mutex_init(&s.mutex, NULL)) goto release;
    mutex_ready = 1;
    if (!analyse_only) {
        struct fb_fix_screeninfo fix; struct fb_var_screeninfo var;
        ffd = open("/dev/fb0", O_RDWR);
        if (ffd < 0 || ioctl(ffd, FBIOGET_FSCREENINFO, &fix) || ioctl(ffd, FBIOGET_VSCREENINFO, &var)
                || framebuffer_geometry(&fix, &var, &map_start, &map_length)) {
            reason = "framebuffer_layout_failed"; goto release;
        }
        map = mmap(NULL, map_length, PROT_READ|PROT_WRITE, MAP_SHARED, ffd, 0);
        if (map == MAP_FAILED) { map = NULL; reason = "framebuffer_mmap_failed"; goto release; }
        fb = (uint32_t *)((unsigned char *)map+map_start); fb_stride_words = fix.line_length/4;
    }
    library = dlopen("libiio.so.0", RTLD_NOW|RTLD_LOCAL);
    if (!library) goto release;
#define LOAD_LATEST(n) { void *p = dlsym(library, #n); if (!p) goto release; memcpy(&fn_##n, &p, sizeof p); }
    API(LOAD_LATEST)
    unsigned int major, minor; char tag[8] = {0}; fn_iio_library_get_version(&major, &minor, tag);
    if (major != 0 || minor != 20) { reason = "unreviewed_libiio_version"; goto release; }
    ctx = fn_iio_create_context_from_uri("local:");
    if (!ctx || fn_iio_context_set_timeout(ctx, 3000)) goto release;
    adc = fn_iio_context_find_device(ctx, "cf-ad9361-lpc");
    phy = fn_iio_context_find_device(ctx, "ad9361-phy");
    if (!adc || !phy || read_rf(phy, &before)) { reason = "RF_before_mismatch"; goto release; }
    before_ok = 1;
    panel_sample_rate_hz = strtod(before.value[0], NULL);
    if (!isfinite(panel_sample_rate_hz) || panel_sample_rate_hz != 30720000.0) {
        reason = "display_sample_rate_not_validated"; goto release;
    }
    for (unsigned int n = 0; n < fn_iio_device_get_channels_count(adc); n++)
        fn_iio_channel_disable(fn_iio_device_get_channel(adc, n));
    for (unsigned int n = 0; n < 2; n++) {
        struct iio_channel *ch = fn_iio_device_find_channel(adc, n ? "voltage1" : "voltage0", false);
        if (!ch) goto release;
        const struct iio_data_format *f = fn_iio_channel_get_data_format(ch);
        if (!f || !fn_iio_channel_is_scan_element(ch) || fn_iio_channel_is_output(ch)
                || f->length != 16 || f->bits != 12 || f->shift || !f->is_signed
                || f->is_be || f->with_scale || f->repeat != 1) {
            reason = "scan_format_failed"; goto release;
        }
        fn_iio_channel_enable(ch); if (n) s.q = ch; else s.i = ch;
    }
    if (fn_iio_device_get_sample_size(adc) != FRAME_BYTES) { reason = "sample_size_failed"; goto release; }
    for (int n = 0; n < FFT_N; n++) window[n] = .5f-.5f*(float)cos(2*M_PI*n/FFT_N);
    s.buffer = fn_iio_device_create_buffer(adc, BLOCK_FRAMES, false);
    buffer_created = s.buffer != NULL;
    if (!s.buffer) { reason = "buffer_create_failed"; goto release; }
    if (stopping) goto release;
    begin = now_s(); next_update = begin;
    if (pthread_create(&worker, NULL, latest_worker, &s)) goto release;
    worker_started = 1;
    printf("P42_STARTED duration_ms=%d log_mode=last_frame_only\n",duration_ms);
    while (!stopping && (!duration_ms || now_s()-begin < duration_ms/1000.0)) {
        uint64_t sequence = 0, skipped = 0;
        pthread_mutex_lock(&s.mutex);
        int done = s.done;
        if (!done && now_s() >= next_update && s.published != s.consumed_sequence) {
            memcpy(shown, s.packed, PREFIX_BYTES); sequence = s.published;
            s.consumed_sequence = sequence; s.consumed++; skipped = s.overwritten;
        }
        pthread_mutex_unlock(&s.mutex);
        if (done) { reason = "refill_worker_stopped"; break; }
        if (sequence) {
            decode_latest(shown, iq);
            struct metrics m = {0}; double t0 = now_s();
            spectrum(iq, PREFIX_FRAMES, 2, 8, 0, window, acc, &m);
            double t1 = now_s();
            if (!analyse_only) {
                draw(acc, &m, 2, PREFIX_FRAMES, updates, (t1-t0)*1000, 8);
                char line[128];
                snprintf(line, sizeof line, "RX active | update %d | source block %" PRIu64 " | UI skipped %" PRIu64, updates+1, sequence, skipped);
                latest_line(28, line);
                latest_line(PANEL_H-24, "LATEST PREFIXES | ADC gaps unknown | digital bin power | no AI");
            }
            double t2 = now_s();
            last=m; last_analysis_ms=(t1-t0)*1000;
            last_draw_ms=analyse_only ? 0 : (t2-t1)*1000; last_compute_ms=(t2-t0)*1000;
            updates++; next_update = t2+interval_ms/1000.0;
            if (save_progress(argv[arg],&s,mutex_ready,"running","receiving",duration_ms,
                              updates,now_s()-begin,&last)) { progress_error=1; break; }
            progress_commits++;
        }
        struct timespec pause = {0, 10000000}; nanosleep(&pause, NULL);
    }
    atomic_store(&s.stop, true); fn_iio_buffer_cancel(s.buffer);
    struct timespec join_until;
    if (deadline(&join_until, CLOCK_REALTIME, JOIN_LIMIT_S)) join_failed(EINVAL);
    int join_rc = pthread_timedjoin_np(worker, NULL, &join_until);
    if (join_rc) join_failed(join_rc);
    worker_joined = 1;
    if (progress_error) reason = "progress_write_failed";
    else if (!s.error && !stopping && duration_ms && updates && now_s()-begin >= duration_ms/1000.0) { status = 0; reason = "duration_complete"; }
    else if (stopping) reason = "signal_requested_stop";
    else if (s.error) reason = "refill_or_layout_failed";
    else if (!updates) reason = "no_displayed_sample";
release:
    if (worker_started && !worker_joined) join_failed(EINVAL);
    elapsed = now_s()-begin;
    if (s.buffer) { fn_iio_buffer_destroy(s.buffer); s.buffer = NULL; }
    if (before_ok) after_ok = !read_rf(phy, &after) && !memcmp(&before, &after, sizeof before);
    if (before_ok && !after_ok) { status = 1; reason = "RF_after_changed"; }
    if (adc) for (unsigned int n = 0; n < fn_iio_device_get_channels_count(adc); n++) fn_iio_channel_disable(fn_iio_device_get_channel(adc, n));
    if (ctx) fn_iio_context_destroy(ctx);
    if (library) dlclose(library);
    size_t saved = 0;
    if (updates) {
        FILE *f = new_file(argv[arg], "last-display-packed.bin");
        if (f) { saved = fwrite(shown, 1, PREFIX_BYTES, f); if (fclose(f)) saved = 0; }
        if (saved != PREFIX_BYTES) { status = 1; reason = "displayed_prefix_save_failed"; }
    }
    struct rusage resources = {0};
    if (getrusage(RUSAGE_SELF, &resources)) { status = 1; reason = "resource_read_failed"; }
    int clean_stop = stopping && !strcmp(reason, "signal_requested_stop") && before_ok && after_ok && worker_joined && !s.error;
    if (save_progress(argv[arg],&s,mutex_ready,status==0 ? "finished" : clean_stop ? "stopped" : "failed",
                      reason,duration_ms,updates,elapsed,&last)) {
        status=1; clean_stop=0; reason="final_progress_write_failed";
    } else progress_commits++;
    if (map && updates) {
        char line[128];
        const char *state = status == 0 ? "RX STOPPED" : clean_stop ? "RX STOPPED BY REQUEST" : "RX FAILED";
        snprintf(line, sizeof line, "%s | update %d | source block %" PRIu64, state, updates, s.consumed_sequence);
        latest_line(28, line);
        latest_line(PANEL_H-24, status == 0 ? "RX STOPPED | last displayed prefix | ADC gaps unknown | no AI" : clean_stop ? "RX STOPPED BY REQUEST | last displayed prefix | no AI" : "RX FAILED | last displayed prefix | no AI");
    }
    if (map) munmap(map, map_length);
    if (ffd >= 0) close(ffd);
    if (mutex_ready) pthread_mutex_destroy(&s.mutex);
    if (updates) {
        print_metrics(updates-1,&last,last_analysis_ms,last_draw_ms,last_compute_ms,analyse_only);
        printf("{\"schema\":\"rfsig.latest_frame.v1\",\"update\":%d,\"source_block_sequence\":%" PRIu64 ",\"UI_overwritten_prefixes\":%" PRIu64 "}\n",
               updates-1,s.consumed_sequence,s.overwritten);
    }
    FILE *summary = new_file(argv[arg], "summary.json");
    if (!summary) return 1;
    fprintf(summary, "{\"program_version\":\"p42\",\"display_revision\":\"p48\",\"telemetry_mode\":\"latest_atomic_progress_and_last_frame_only\",\"progress_commits\":%" PRIu64 ",\"schema\":\"rfsig.latest_panel.v1\",\"status\":\"%s\",\"reason\":\"%s\",\"duration_ms_requested\":%d,\"UI_interval_ms_requested\":%d,\"elapsed_software_s\":%.9g,\"published_prefixes\":%" PRIu64 ",\"consumed_prefixes\":%" PRIu64 ",\"last_display_sequence\":%" PRIu64 ",\"UI_overwritten_prefixes\":%" PRIu64 ",\"pending_prefixes_at_stop\":%d,\"display_updates\":%d,\"retained_prefix_bytes\":%zu,\"prefix_frames\":%u,\"frames_per_refill\":%u,\"source_format\":\"le:S12/16>>0\",\"worker_started\":%s,\"worker_joined\":%s,\"refill_error\":%d,\"buffer_created\":%s,\"buffer_released\":true,\"context_released\":true,\"cleanup_unconfirmed\":false,\"RF_before_valid\":%s,\"RF_after_matches\":%s,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false,\"ADC_gaps\":\"unknown\",\"analyse_only\":%s,\"maxrss_kib\":%ld}\n",
        progress_commits,
        status == 0 ? "pass" : clean_stop ? "stopped" : "fail", reason, duration_ms, interval_ms, elapsed,
        s.published, s.consumed, s.consumed_sequence, s.overwritten, s.published != s.consumed_sequence,
        updates, saved, PREFIX_FRAMES, BLOCK_FRAMES, worker_started ? "true" : "false", worker_joined ? "true" : "false", s.error,
        buffer_created ? "true" : "false", before_ok ? "true" : "false", after_ok ? "true" : "false", analyse_only ? "true" : "false", resources.ru_maxrss);
    int bad = ferror(summary); if (fclose(summary)) bad = 1;
    printf("P42_LIVE_DONE status=%d updates=%d published=%" PRIu64 "\n", status, updates, s.published);
    return bad ? 1 : clean_stop ? 0 : status;
}
