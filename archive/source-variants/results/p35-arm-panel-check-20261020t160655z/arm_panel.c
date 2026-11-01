/*
 * arm_panel - on-board spectrum panel for the TLZ7xH-EVM.
 *
 * WHY THIS PROGRAM EXISTS
 * -----------------------
 * Everything earlier renders on the host: a capture is analysed in Python and the
 * finished picture is shipped to /dev/fb0 as bytes. That proves the layout and
 * the display path, but the board itself does nothing. Task 1 of the project is a
 * panel that shows signal characteristics, so the analysis has to run on the
 * board.
 *
 * This program does that. It reads interleaved int16 I/Q, applies a Hann window,
 * runs an in-place radix-2 FFT, averages a few frames into a dB spectrum and draws
 * the result straight into the framebuffer. It also measures its own frame time,
 * because "can this be real time?" is a question only a measurement answers.
 *
 * The spectrum it computes was cross-checked against a numpy implementation of the
 * same algorithm (experiments/p34_arm_panel_reference.py): peak level, peak bin
 * offset and RMS agreed to the printed precision.
 *
 * WHY THERE IS NO LIVE CAPTURE HERE YET
 * -------------------------------------
 * The board cannot receive and display at the same time with the shipped
 * bitstreams: in display mode there is no AD9361, in RF mode there is no
 * /dev/fb0. A merged RF+display bitstream now exists, so live capture becomes
 * possible once it is deployed; the capture block drops in where load_iq() is,
 * using the dynamic libiio loading proven by arm_rx_diagnostic.c.
 *
 * Usage:  arm_panel <iq-file> [channels] [frames] [iterations]
 *           channels   : interleaved channels in the file, default 4 (RX1 uses ch0/ch1)
 *           frames     : FFT frames averaged per panel, default 8
 *           iterations : panels to draw, sliding the window, default 1
 *        arm_panel --analyse-only <iq-file> [channels] [frames] [iterations]
 *          prints JSON analysis without opening the framebuffer.
 *
 * Bin power is mean(|FFT(I+jQ times Hann)|^2)/(N*sum(Hann^2)), in
 * count^2 per FFT bin. This is not dBm, calibrated RF power, or power/Hz.
 * Timings separate FFT analysis from framebuffer drawing; they do not measure
 * capture throughput, display refresh, file loading, or end-to-end latency.
 */

/* clock_gettime and CLOCK_MONOTONIC need POSIX 2008 visibility; -std=c99 alone
 * hides them, which is a compile error rather than a warning. */
#define _POSIX_C_SOURCE 200809L

#include <errno.h>
#include <fcntl.h>
#include <limits.h>
#include <linux/fb.h>
#include <math.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/mman.h>
#include <sys/ioctl.h>
#include <time.h>
#include <unistd.h>

#include "font8x12.h"

#ifndef M_PI
/* -std=c99 hides M_PI unless _GNU_SOURCE is set; define it rather than depend on
 * a feature-test macro a different toolchain may not honour. */
#define M_PI 3.14159265358979323846
#endif

#define PANEL_W 800
#define PANEL_H 480

#define FFT_N 1024
#define DB_SPAN 70.0

#define HEADER_H 46
#define SPEC_L 60
#define SPEC_T 62
#define SPEC_R (PANEL_W - 20)
#define SPEC_B 300
#define METRIC_T 312

#define MAX_ITER 4096
#define MAX_FRAMES 4096

static uint32_t *fb = NULL;
static size_t fb_stride_words;

static uint32_t rgb(unsigned r, unsigned g, unsigned b)
{
    /* Little-endian DRM wants B,G,R,X in memory, which is 0xAARRGGBB stored LE. */
    return 0xFF000000u | ((r & 0xFF) << 16) | ((g & 0xFF) << 8) | (b & 0xFF);
}

#define C_BG     rgb(12, 14, 18)
#define C_FG     rgb(222, 230, 238)
#define C_DIM    rgb(150, 165, 182)
#define C_ACCENT rgb(80, 200, 255)
#define C_GRID   rgb(38, 44, 54)
#define C_TRACE  rgb(120, 230, 150)

static void put(int x, int y, uint32_t colour)
{
    if (x < 0 || y < 0 || x >= PANEL_W || y >= PANEL_H)
        return;
    fb[(size_t)y * fb_stride_words + (size_t)x] = colour;
}

static void fill(uint32_t colour)
{
    for (size_t y = 0; y < PANEL_H; y++)
        for (size_t x = 0; x < PANEL_W; x++)
            fb[y * fb_stride_words + x] = colour;
}

static void hline(int x0, int x1, int y, uint32_t colour)
{
    if (x0 > x1) { int t = x0; x0 = x1; x1 = t; }
    for (int x = x0; x <= x1; x++)
        put(x, y, colour);
}

static void vline(int x, int y0, int y1, uint32_t colour)
{
    if (y0 > y1) { int t = y0; y0 = y1; y1 = t; }
    for (int y = y0; y <= y1; y++)
        put(x, y, colour);
}

static void rect(int x0, int y0, int x1, int y1, uint32_t colour)
{
    hline(x0, x1, y0, colour);
    hline(x0, x1, y1, colour);
    vline(x0, y0, y1, colour);
    vline(x1, y0, y1, colour);
}

static void bresenham(int x0, int y0, int x1, int y1, uint32_t colour)
{
    int dx = abs(x1 - x0), sx = x0 < x1 ? 1 : -1;
    int dy = -abs(y1 - y0), sy = y0 < y1 ? 1 : -1;
    int err = dx + dy;
    for (;;) {
        put(x0, y0, colour);
        if (x0 == x1 && y0 == y1)
            break;
        int e2 = 2 * err;
        if (e2 >= dy) { err += dy; x0 += sx; }
        if (e2 <= dx) { err += dx; y0 += sy; }
    }
}

static void glyph(int x, int y, char ch, uint32_t colour)
{
    unsigned code = (unsigned char)ch;
    if (code < FONT_FIRST || code > FONT_LAST)
        code = '?';
    const unsigned char *rows = FONT_DATA[code - FONT_FIRST];
    for (int row = 0; row < FONT_H; row++) {
        unsigned char bits = rows[row];
        for (int col = 0; col < FONT_W; col++) {
            if (bits & (1u << (7 - col)))
                put(x + col, y + row, colour);
        }
    }
}

static void text(int x, int y, const char *s, uint32_t colour)
{
    for (; *s; s++) {
        glyph(x, y, *s, colour);
        x += FONT_W;
    }
}

static double now_s(void)
{
    struct timespec ts;
    if (clock_gettime(CLOCK_MONOTONIC, &ts) != 0) {
        perror("clock_gettime");
        exit(4);
    }
    return (double)ts.tv_sec + (double)ts.tv_nsec * 1e-9;
}

/* ---------------------------------------------------------------- FFT */

static void fft(float *re, float *im, int n)
{
    for (int i = 1, j = 0; i < n; i++) {
        int bit = n >> 1;
        for (; j & bit; bit >>= 1)
            j ^= bit;
        j ^= bit;
        if (i < j) {
            float t = re[i]; re[i] = re[j]; re[j] = t;
            t = im[i]; im[i] = im[j]; im[j] = t;
        }
    }
    for (int len = 2; len <= n; len <<= 1) {
        double ang = -2.0 * M_PI / len;
        float wr = (float)cos(ang), wi = (float)sin(ang);
        for (int i = 0; i < n; i += len) {
            float cr = 1.0f, ci = 0.0f;
            for (int k = 0; k < len / 2; k++) {
                int a = i + k, b = i + k + len / 2;
                float tr = re[b] * cr - im[b] * ci;
                float ti = re[b] * ci + im[b] * cr;
                re[b] = re[a] - tr;
                im[b] = im[a] - ti;
                re[a] += tr;
                im[a] += ti;
                float ncr = cr * wr - ci * wi;
                ci = cr * wi + ci * wr;
                cr = ncr;
            }
        }
    }
}

/* ---------------------------------------------------------------- input */

static int16_t *load_iq(const char *path, size_t *pairs, int *channels)
{
    FILE *handle = fopen(path, "rb");
    if (!handle) {
        fprintf(stderr, "cannot open %s: %s\n", path, strerror(errno));
        return NULL;
    }
    if (fseek(handle, 0, SEEK_END) != 0) {
        fclose(handle);
        return NULL;
    }
    long bytes = ftell(handle);
    rewind(handle);
    if (bytes <= 0 || (bytes % 2) != 0) {
        fprintf(stderr, "%s: not a whole number of int16 samples\n", path);
        fclose(handle);
        return NULL;
    }
    size_t words = (size_t)bytes / 2;
    int ch = *channels > 0 ? *channels : 4;
    if (words % (size_t)ch != 0) {
        fprintf(stderr, "%s: %zu words is not a multiple of %d channels\n", path, words, ch);
        fclose(handle);
        return NULL;
    }
    int16_t *raw = malloc(words * sizeof(int16_t));
    if (!raw) {
        fclose(handle);
        return NULL;
    }
    if (fread(raw, sizeof(int16_t), words, handle) != words) {
        fprintf(stderr, "short read from %s\n", path);
        free(raw);
        fclose(handle);
        return NULL;
    }
    fclose(handle);
    *channels = ch;
    *pairs = words / (size_t)ch;
    return raw;
}

/* ------------------------------------------------------------ analysis */

struct metrics {
    double peak_db;
    int peak_bin;
    double peak_offset_bins;
    double rms;
    int frames_used;
    double spectrum_power_sum;
    int peak_valid;
};

static void spectrum(const int16_t *raw, size_t pairs, int channels, int frames,
                     size_t start_pair, const float *window,
                     double *acc, struct metrics *out)
{
    static float re[FFT_N], im[FFT_N];
    memset(acc, 0, sizeof(double) * FFT_N);

    size_t avail = pairs > start_pair ? pairs - start_pair : 0;
    int used = (int)(avail / FFT_N);
    if (used > frames)
        used = frames;
    if (used < 1)
        used = 1;

    double total_power = 0.0;
    for (int f = 0; f < used; f++) {
        const int16_t *base = raw + (start_pair + (size_t)f * FFT_N) * channels;
        for (int n = 0; n < FFT_N; n++) {
            float i = (float)base[(size_t)n * channels + 0];
            float q = (float)base[(size_t)n * channels + 1];
            total_power += (double)i * i + (double)q * q;
            re[n] = i * window[n];
            im[n] = q * window[n];
        }
        fft(re, im, FFT_N);
        for (int k = 0; k < FFT_N; k++)
            acc[k] += (double)re[k] * re[k] + (double)im[k] * im[k];
    }

    out->frames_used = used;
    out->rms = sqrt(total_power / (double)((size_t)used * FFT_N * 2));

    double window_energy = 0.0;
    for (int n = 0; n < FFT_N; n++)
        window_energy += (double)window[n] * window[n];
    double denominator = (double)used * FFT_N * window_energy;
    out->spectrum_power_sum = 0.0;
    for (int k = 0; k < FFT_N; k++) {
        acc[k] /= denominator;
        out->spectrum_power_sum += acc[k];
    }
    double peak = -1e30;
    int peak_bin = 0;
    for (int k = 0; k < FFT_N; k++) {
        int src = (k + FFT_N / 2) % FFT_N;
        double v = acc[src] > 0 ? 10.0 * log10(acc[src] + 1e-30) : -300.0;
        if (v > peak) { peak = v; peak_bin = k; }
    }
    out->peak_db = peak;
    out->peak_bin = peak_bin;
    out->peak_offset_bins = (double)(peak_bin - FFT_N / 2);
    out->peak_valid = out->spectrum_power_sum > 0.0;
}

static void draw(const double *acc, const struct metrics *m, int channels,
                 size_t pairs, int iteration, double frame_ms, int frames_requested)
{
    char line[128];
    fill(C_BG);
    text(16, 10, "RF SIGNAL LAB", C_ACCENT);
    snprintf(line, sizeof line, "on-board arm_panel  %dx%d  n=%d", PANEL_W, PANEL_H, FFT_N);
    text(16, 28, line, C_DIM);
    hline(16, PANEL_W - 16, HEADER_H, C_GRID);

    rect(SPEC_L, SPEC_T, SPEC_R, SPEC_B, C_GRID);
    text(SPEC_L, SPEC_T - FONT_H - 1, "Spectrum: dB relative to this panel peak", C_DIM);
    for (int g = 0; g <= 5; g++) {
        int y = SPEC_B - (SPEC_B - SPEC_T) * g / 5;
        if (g) hline(SPEC_L + 1, SPEC_R - 1, y, C_GRID);
        snprintf(line, sizeof line, "%d", -(5 - g) * (int)(DB_SPAN / 5));
        text(SPEC_L - 30, y - FONT_H / 2, line, C_DIM);
    }
    vline((SPEC_L + SPEC_R) / 2, SPEC_T + 1, SPEC_B - 1, C_GRID);

    static double db[FFT_N];
    for (int k = 0; k < FFT_N; k++) {
        int src = (k + FFT_N / 2) % FFT_N;
        db[k] = acc[src] > 0 ? 10.0 * log10(acc[src] + 1e-30) : -300.0;
    }
    int prev_x = -1, prev_y = -1;
    for (int k = 0; k < FFT_N; k++) {
        double norm = (db[k] - (m->peak_db - DB_SPAN)) / DB_SPAN;
        if (norm < 0) norm = 0;
        if (norm > 1) norm = 1;
        int x = SPEC_L + 1 + (int)((double)(SPEC_R - SPEC_L - 2) * k / (FFT_N - 1));
        int y = SPEC_B - 1 - (int)(norm * (double)(SPEC_B - SPEC_T - 2));
        if (prev_x >= 0)
            bresenham(prev_x, prev_y, x, y, C_TRACE);
        prev_x = x;
        prev_y = y;
    }
    if (m->peak_valid) {
        int peak_x = SPEC_L + 1 + (int)((double)(SPEC_R - SPEC_L - 2) * m->peak_bin / (FFT_N - 1));
        vline(peak_x, SPEC_T + 1, SPEC_B - 1, C_ACCENT);
    }

    rect(SPEC_L, METRIC_T, PANEL_W - 20, PANEL_H - 14, C_GRID);
    int ty = METRIC_T + 8;
    const int lx = SPEC_L + 10, vx = SPEC_L + 190;
#define ROW(label, fmt, value)                       \
    do {                                             \
        text(lx, ty, label, C_DIM);                  \
        snprintf(line, sizeof line, fmt, value);     \
        text(vx, ty, line, C_FG);                    \
        ty += FONT_H + 6;                            \
    } while (0)

    text(lx, ty, "peak bin power", C_DIM);
    if (m->peak_valid) snprintf(line, sizeof line, "%.1f dB re 1 count^2", m->peak_db);
    else snprintf(line, sizeof line, "none (zero input)");
    text(vx, ty, line, C_FG); ty += FONT_H + 6;
    text(lx, ty, "peak offset", C_DIM);
    if (m->peak_valid) snprintf(line, sizeof line, "%.1f bins", m->peak_offset_bins);
    else snprintf(line, sizeof line, "none");
    text(vx, ty, line, C_FG); ty += FONT_H + 6;
    ROW("rms/component", "%.1f counts", m->rms);
    ROW("analysis only", "%.1f ms", frame_ms);
    ROW("iteration", "%d", iteration);
    text(lx, ty, "frames/panel", C_DIM);
    snprintf(line, sizeof line, "%d of %d", m->frames_used, frames_requested);
    text(vx, ty, line, C_FG);
    ty += FONT_H + 6;
    ROW("channels", "%d", channels);
    (void)pairs;
#undef ROW

    text(16, PANEL_H - 26, "Saved IQ | Hann energy normalized bin power | not live RF / dBm", C_DIM);
}

/* Geometry validation is pure so the same boundary checks can be exercised
 * without an actual framebuffer. Only known little-endian X/ARGB8888 is accepted. */
static int framebuffer_geometry(const struct fb_fix_screeninfo *fix,
        const struct fb_var_screeninfo *var, size_t *start, size_t *length)
{
    uint16_t endian = 1;
    if (*(const unsigned char *)&endian != 1 || fix->type != FB_TYPE_PACKED_PIXELS ||
        fix->visual != FB_VISUAL_TRUECOLOR || var->xres != PANEL_W ||
        var->yres != PANEL_H || var->bits_per_pixel != 32 || var->grayscale ||
        var->nonstd || var->rotate || var->vmode ||
        var->red.offset != 16 || var->red.length != 8 || var->red.msb_right ||
        var->green.offset != 8 || var->green.length != 8 || var->green.msb_right ||
        var->blue.offset || var->blue.length != 8 || var->blue.msb_right ||
        (var->transp.length && (var->transp.length != 8 || var->transp.offset != 24 || var->transp.msb_right)) ||
        !fix->line_length || (fix->line_length % 4) ||
        (uint64_t)var->xoffset + PANEL_W > var->xres_virtual ||
        (uint64_t)var->yoffset + PANEL_H > var->yres_virtual ||
        ((uint64_t)var->xoffset + PANEL_W) * 4 > fix->line_length)
        return -1;
    uint64_t first = (uint64_t)var->yoffset * fix->line_length + (uint64_t)var->xoffset * 4;
    uint64_t end = first + (PANEL_H - 1u) * (uint64_t)fix->line_length + PANEL_W * 4u;
    if (end > fix->smem_len || end > SIZE_MAX || first > SIZE_MAX)
        return -1;
    *start = (size_t)first;
    *length = (size_t)end;
    return 0;
}

static int number(const char *value, int minimum, int maximum, int *out)
{
    if (!value || !*value) return -1;
    for (const char *p = value; *p; p++)
        if (*p < '0' || *p > '9') return -1;
    errno = 0;
    char *end = NULL;
    long n = strtol(value, &end, 10);
    if (errno || !end || *end || n < minimum || n > maximum) return -1;
    *out = (int)n;
    return 0;
}

static void print_metrics(int iteration, const struct metrics *m,
        double analysis_ms, double draw_ms, double compute_ms, int analyse_only)
{
    printf("{\"schema\":\"rfsig.arm_panel_metrics.v2\",\"iteration\":%d,\"frames\":%d,"
           "\"power_reference\":\"1 count^2 per FFT bin\",\"normalization\":\"mean_fft_power/(N*sum_hann_squared)\","
           "\"peak_db\":%.9g,\"peak_valid\":%s,\"peak_offset_bins\":",
           iteration, m->frames_used, m->peak_db, m->peak_valid ? "true" : "false");
    if (m->peak_valid) printf("%.9g", m->peak_offset_bins); else printf("null");
    printf(",\"rms_per_component_counts\":%.12g,\"spectrum_power_sum_counts_squared\":%.12g,"
           "\"analysis_ms\":%.9g,\"draw_ms\":%.9g,\"iteration_compute_ms\":%.9g,"
           "\"analyse_only\":%s,\"display_refresh_measured\":false,\"capture_throughput_measured\":false}\n",
           m->rms, m->spectrum_power_sum, analysis_ms, draw_ms, compute_ms,
           analyse_only ? "true" : "false");
}

/* ---------------------------------------------------------------- main */

int main(int argc, char **argv)
{
    int arg = 1, analyse_only = 0;
    if (argc > 1 && strcmp(argv[1], "--analyse-only") == 0) { analyse_only = 1; arg++; }
    if (argc < arg + 1 || argc > arg + 4) {
        fprintf(stderr, "usage: %s [--analyse-only] <iq-file> [channels] [frames] [iterations]\n", argv[0]);
        return 2;
    }
    int channels = 4, frames = 8, iterations = 1;
    if ((argc > arg + 1 && number(argv[arg + 1], 2, 8, &channels)) ||
        (argc > arg + 2 && number(argv[arg + 2], 1, MAX_FRAMES, &frames)) ||
        (argc > arg + 3 && number(argv[arg + 3], 1, MAX_ITER, &iterations))) {
        fprintf(stderr, "invalid numeric argument (channels 2..8; frames/iterations 1..4096)\n");
        return 2;
    }

    size_t pairs = 0;
    int16_t *raw = load_iq(argv[arg], &pairs, &channels);
    if (!raw)
        return 2;
    if (pairs < (size_t)FFT_N) {
        fprintf(stderr, "need at least %d I/Q pairs, file has %zu\n", FFT_N, pairs);
        free(raw);
        return 2;
    }

    int ffd = -1;
    void *map = NULL;
    size_t map_length = 0;
    if (!analyse_only) {
        struct fb_fix_screeninfo fix;
        struct fb_var_screeninfo var;
        size_t start = 0;
        ffd = open("/dev/fb0", O_RDWR);
        if (ffd < 0 || ioctl(ffd, FBIOGET_FSCREENINFO, &fix) ||
            ioctl(ffd, FBIOGET_VSCREENINFO, &var) ||
            framebuffer_geometry(&fix, &var, &start, &map_length)) {
            fprintf(stderr, "framebuffer unavailable or unsupported geometry/format/extent\n");
            if (ffd >= 0) close(ffd);
            free(raw);
            return 3;
        }
        map = mmap(NULL, map_length, PROT_READ | PROT_WRITE, MAP_SHARED, ffd, 0);
        if (map == MAP_FAILED) {
            perror("mmap /dev/fb0");
            close(ffd); free(raw); return 3;
        }
        fb = (uint32_t *)((unsigned char *)map + start);
        fb_stride_words = fix.line_length / 4;
    }

    static float window[FFT_N];
    for (int n = 0; n < FFT_N; n++)
        window[n] = 0.5f - 0.5f * (float)cos(2.0 * M_PI * n / FFT_N);

    static double acc[FFT_N];
    static double frame_ms[MAX_ITER];

    struct metrics last = {0};
    size_t span = (size_t)frames * FFT_N;
    for (int it = 0; it < iterations; it++) {
        /* Slide the analysis window so successive panels show different data;
         * clamp at the end so the last panels repeat rather than read past it. */
        size_t start = (size_t)it * FFT_N;
        if (start + span > pairs)
            start = pairs > span ? pairs - span : 0;

        double t0 = now_s();
        spectrum(raw, pairs, channels, frames, start, window, acc, &last);
        double t1 = now_s();
        if (!analyse_only) draw(acc, &last, channels, pairs, it, (t1 - t0) * 1e3, frames);
        double t2 = now_s();
        frame_ms[it] = (t2 - t0) * 1e3;
        print_metrics(it, &last, (t1-t0)*1e3, analyse_only ? 0.0 : (t2-t1)*1e3,
                      frame_ms[it], analyse_only);
    }
    /* Framebuffer stores have completed at the CPU; this does not wait for
     * scanout/vsync. No refresh-rate/FPS claim is inferred from compute time. */

    double sum = 0.0, worst = 0.0;
    for (int i = 0; i < iterations; i++) {
        sum += frame_ms[i];
        if (frame_ms[i] > worst) worst = frame_ms[i];
    }
    double mean = sum / (double)iterations;
    printf("iterations=%d mean_iteration_compute_ms=%.3f worst_iteration_compute_ms=%.3f\n",
           iterations, mean, worst);
    printf("last: frames=%d peak=%.1f dB_re_1_count_squared_per_bin offset=%.1f bins rms_per_component=%.1f\n",
           last.frames_used, last.peak_db, last.peak_offset_bins, last.rms);

    if (map) munmap(map, map_length);
    if (ffd >= 0) close(ffd);
    free(raw);
    return 0;
}
