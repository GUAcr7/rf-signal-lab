/* Bounded periodic RX snapshots on the native LCD. No RF configuration/TX.
 * Reuse the reviewed finite receiver and numerical/geometry renderer unchanged.
 * Capture releases RX before drawing: this is NOT continuous lossless RX.
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#define main full_recorder_main
#include "../arm_rx_full_p36/arm_rx_full_p36.c"
#undef main
#define main saved_panel_main
#include "../arm_panel/arm_panel.c"
#undef main

static void panel_line(int y, const char *line) {
    for (int row = y; row < y + FONT_H && row < PANEL_H; row++)
        for (int x = 16; x < PANEL_W - 16; x++) put(x, row, C_BG);
    text(16, y, line, C_DIM);
}

static int read_packed(const char *directory, int16_t *iq) {
    char path[1024];
    int n = snprintf(path, sizeof path, "%s/iq-packed.bin", directory);
    if (n < 0 || n >= (int)sizeof path) return -1;
    FILE *f = fopen(path, "rb");
    if (!f) return -1;
    unsigned char *bytes = (unsigned char *)iq;
    size_t count = fread(bytes, 1, BLOCK_BYTES, f);
    int extra = fgetc(f), bad = ferror(f);
    if (fclose(f)) bad = 1;
    if (bad || count != BLOCK_BYTES || extra != EOF) return -1;
    for (size_t i = 0; i < BLOCK_FRAMES * 2; i++) {
        unsigned int word = bytes[2*i] | ((unsigned int)bytes[2*i+1] << 8);
        int low = (int)(word & 4095u);
        iq[i] = (int16_t)(low >= 2048 ? low - 4096 : low);
    }
    return 0;
}

int main(int argc, char **argv) {
    int arg = 1, analyse_only = 0, cycles = 8, interval_ms = 500;
    if (argc > 1 && !strcmp(argv[1], "--analyse-only")) { analyse_only = 1; arg++; }
    if (argc != arg + 3 || number(argv[arg+1], 1, 64, &cycles)
            || number(argv[arg+2], 100, 5000, &interval_ms)
            || strlen(argv[arg]) > 800) {
        fprintf(stderr, "usage: arm-rx-panel-p38 [--analyse-only] NEW_DIRECTORY CYCLES_1_64 INTERVAL_MS_100_5000\n");
        return 2;
    }
    if (mkdir(argv[arg], 0700)) { perror("new monitor directory"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct sigaction action = {0};
    action.sa_handler = stop_handler; sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) return 3;
    int ffd = -1, status = 1, completed = 0;
    const char *reason = "setup_failed";
    void *map = NULL;
    size_t map_length = 0, start = 0;
    int16_t *iq = malloc(BLOCK_BYTES);
    double begin = now_s(), elapsed = 0;
    float window[FFT_N];
    double acc[FFT_N];
    if (!iq) goto done;
    if (!analyse_only) {
        struct fb_fix_screeninfo fix;
        struct fb_var_screeninfo var;
        ffd = open("/dev/fb0", O_RDWR);
        if (ffd < 0 || ioctl(ffd, FBIOGET_FSCREENINFO, &fix)
                || ioctl(ffd, FBIOGET_VSCREENINFO, &var)
                || framebuffer_geometry(&fix, &var, &start, &map_length)) {
            reason = "unsupported_framebuffer"; goto done;
        }
        map = mmap(NULL, map_length, PROT_READ | PROT_WRITE, MAP_SHARED, ffd, 0);
        if (map == MAP_FAILED) { map = NULL; reason = "framebuffer_map_failed"; goto done; }
        fb = (uint32_t *)((unsigned char *)map + start);
        fb_stride_words = fix.line_length / 4;
    }
    for (int n = 0; n < FFT_N; n++)
        window[n] = .5f - .5f * (float)cos(2 * M_PI * n / FFT_N);
    for (int cycle = 0; cycle < cycles && !stopping; cycle++) {
        /* Absolute upper bound between captures. A capture retains the reviewed
         * 15s cancel deadline and 3.5s join limit; setup/driver calls are not a
         * universal hard-real-time guarantee. Each cycle keeps all returned IQ. */
        if (now_s() - begin > 90) { reason = "monitor_deadline"; break; }
        char directory[1024];
        snprintf(directory, sizeof directory, "%s/cycle-%03d", argv[arg], cycle);
        char *capture_argv[] = {"arm-rx-full-p36", directory, "1", NULL};
        int rc = full_recorder_main(3, capture_argv);
        if (rc) { reason = "capture_failed_or_cancelled"; break; }
        if (stopping) { reason = "signal_stop"; break; }
        if (read_packed(directory, iq)) { reason = "packed_IQ_read_failed"; break; }
        struct metrics m = {0};
        double t0 = now_s();
        /* The first eight contiguous FFT frames of this full RX buffer. */
        spectrum(iq, BLOCK_FRAMES, 2, 8, 0, window, acc, &m);
        double t1 = now_s();
        if (!analyse_only) {
            draw(acc, &m, 2, BLOCK_FRAMES, cycle, (t1-t0)*1000, 8);
            char line[128];
            snprintf(line, sizeof line, "RX snapshot %d/%d | LO 2450 MHz | Fs 30.72 MS/s", cycle+1, cycles);
            panel_line(28, line);
            panel_line(PANEL_H-24, "PERIODIC RX | gaps unknown | counts/bin, not dBm | no AI");
        }
        double t2 = now_s();
        print_metrics(cycle, &m, (t1-t0)*1000, analyse_only ? 0 : (t2-t1)*1000, (t2-t0)*1000, analyse_only);
        completed++;
        if (completed < cycles) {
            struct timespec delay = {interval_ms/1000, (interval_ms%1000)*1000000L};
            while (!stopping && nanosleep(&delay, &delay) && errno == EINTR) {}
        }
    }
    if (completed == cycles && !stopping) { status = 0; reason = "complete"; }
    else if (stopping) reason = "signal_stop";
    if (map && completed)
        panel_line(PANEL_H-24, status == 0 ? "RX STOPPED | last snapshot | gaps unknown | no AI"
                                         : "RX FAILED/STOPPED | last snapshot | no AI");
done:
    elapsed = now_s() - begin;
    if (map) munmap(map, map_length);
    if (ffd >= 0) close(ffd);
    free(iq);
    FILE *summary = new_file(argv[arg], "summary.json");
    if (!summary) status = 1;
    else {
        fprintf(summary, "{\"schema\":\"rfsig.periodic_rx_panel.v1\",\"status\":\"%s\",\"reason\":\"%s\",\"requested_cycles\":%d,\"completed_cycles\":%d,\"interval_ms_requested\":%d,\"elapsed_software_s\":%.9g,\"analyse_only\":%s,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"continuous_RX\":false,\"lossless_proven\":false,\"display_refresh_measured\":false,\"hardware_gaps\":\"unknown\"}\n",
                status == 0 ? "pass" : "fail", reason, cycles, completed, interval_ms, elapsed, analyse_only ? "true" : "false");
        int bad = ferror(summary); if (fclose(summary)) bad = 1;
        if (bad) status = 1;
    }
    printf("P38_MONITOR_DONE status=%d completed=%d requested=%d\n", status, completed, cycles);
    return status;
}
