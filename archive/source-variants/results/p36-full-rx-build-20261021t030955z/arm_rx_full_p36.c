/* Finite full returned-buffer recorder, NOT evidence of lossless ADC time.
 * Reviewed receiver ABI: libiio 0.20, RX1 I/Q le:S12/16>>0, 4 bytes/frame.
 * No RF attribute writes or TX API. Capture does no filesystem I/O or DSP.
 * SIGINT/SIGTERM only set a flag; main cancels and joins before destruction.
 */
#define _GNU_SOURCE
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <dlfcn.h>
#include <errno.h>
#include <pthread.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <sys/resource.h>
#include <sys/stat.h>
#include <time.h>
#include <unistd.h>

#define BLOCK_FRAMES 65536u
#define FRAME_BYTES 4u
#define BLOCK_BYTES (BLOCK_FRAMES * FRAME_BYTES)
#define DEFAULT_BLOCKS 16u
#define MAX_BLOCKS 64u
#define CAPTURE_LIMIT_S 15.0
#define JOIN_LIMIT_S 3.5
#define API(X) \
 X(iio_library_get_version) X(iio_create_context_from_uri) X(iio_context_destroy) \
 X(iio_context_set_timeout) X(iio_context_find_device) X(iio_device_find_channel) \
 X(iio_device_get_channels_count) X(iio_device_get_channel) X(iio_channel_disable) \
 X(iio_channel_enable) X(iio_channel_is_scan_element) X(iio_channel_is_output) \
 X(iio_channel_get_data_format) X(iio_device_get_sample_size) X(iio_device_create_buffer) \
 X(iio_buffer_refill) X(iio_buffer_cancel) X(iio_buffer_destroy) X(iio_buffer_first) \
 X(iio_buffer_end) X(iio_buffer_step) X(iio_channel_attr_read) X(iio_device_debug_attr_read)
#define DECLARE(n) static __typeof__(&n) fn_##n;
API(DECLARE)

static volatile sig_atomic_t stopping;
static void stop_handler(int number) { (void)number; stopping = 1; }
static int monotonic(double *result) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) return -1;
    *result = (double)t.tv_sec + (double)t.tv_nsec * 1e-9;
    return 0;
}
static int deadline(struct timespec *t, clockid_t clock, double seconds) {
    if (clock_gettime(clock, t)) return -1;
    t->tv_sec += (time_t)seconds;
    t->tv_nsec += (long)((seconds - (time_t)seconds) * 1e9);
    if (t->tv_nsec >= 1000000000L) { t->tv_sec++; t->tv_nsec -= 1000000000L; }
    return 0;
}
static FILE *new_file(const char *directory, const char *name) {
    char path[1024];
    int n = snprintf(path, sizeof path, "%s/%s", directory, name);
    if (n < 0 || n >= (int)sizeof path) { errno = ENAMETOOLONG; return NULL; }
    return fopen(path, "wbx");
}

struct rf_state { char value[9][128]; };
static const char *rf_keys[] = {"sample_rate_hz", "rf_bandwidth_hz", "gain_mode", "gain_db", "rx_port", "rx_lo_hz", "bist_prbs", "bist_tone", "loopback"};
static int read_rf(struct iio_device *phy, struct rf_state *state) {
    const char *names[] = {"sampling_frequency", "rf_bandwidth", "gain_control_mode", "hardwaregain", "rf_port_select", "frequency"};
    const char *expected[] = {"30720000", "18000000", "manual", "0.000000 dB", "A_BALANCED", "2450000000"};
    struct iio_channel *rx = fn_iio_device_find_channel(phy, "voltage0", false);
    struct iio_channel *lo = fn_iio_device_find_channel(phy, "altvoltage0", true);
    memset(state, 0, sizeof *state);
    if (!rx || !lo) return -1;
    for (unsigned int j = 0; j < 6; j++) {
        char *value = state->value[j];
        ssize_t n = fn_iio_channel_attr_read(j == 5 ? lo : rx, names[j], value, 127);
        if (n < 0 || n >= 128) return -1;
        value[n] = 0; value[strcspn(value, "\r\n")] = 0;
        if (strcmp(value, expected[j])) return -1;
    }
    for (unsigned int j = 6; j < 9; j++) {
        char *value = state->value[j];
        ssize_t n = fn_iio_device_debug_attr_read(phy, rf_keys[j], value, 127);
        if (n < 0 || n >= 128) return -1;
        value[n] = 0; value[strcspn(value, "\r\n")] = 0;
        if (!*value || !strchr(value, '0') || strspn(value, "0 \t") != strlen(value)) return -1;
        strcpy(value, "0");
    }
    return 0;
}
static int save_rf(const char *directory, const char *name, const struct rf_state *state) {
    FILE *file = new_file(directory, name);
    if (!file) return -1;
    for (unsigned int j = 0; j < 9; j++) fprintf(file, "%s=%s\n", rf_keys[j], state->value[j]);
    int bad = ferror(file);
    if (fclose(file)) bad = 1;
    return bad ? -1 : 0;
}

struct stamp { double start, refill, copied; ssize_t bytes; int copy_complete; };
struct capture {
    struct iio_buffer *buffer;
    struct iio_channel *channels[2];
    unsigned char *saved;
    struct stamp *stamps;
    unsigned int requested, attempts, completed;
    double begin, end;
    const char *reason;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    int done;
};
static void *capture_worker(void *argument) {
    struct capture *state = argument;
    state->reason = "complete";
    for (unsigned int b = 0; b < state->requested; b++) {
        if (stopping) { state->reason = "signal_requested_stop"; break; }
        struct stamp *stamp = &state->stamps[b];
        double t;
        if (monotonic(&t)) { state->reason = "clock_error"; break; }
        stamp->start = t - state->begin;
        if (stamp->start >= CAPTURE_LIMIT_S) { state->reason = "capture_deadline"; break; }
        state->attempts++;
        stamp->bytes = fn_iio_buffer_refill(state->buffer);
        if (monotonic(&t)) { state->reason = "clock_error"; break; }
        stamp->refill = t - state->begin;
        if (stamp->bytes < 0) { state->reason = "refill_error_or_cancel"; break; }
        unsigned char *first = fn_iio_buffer_first(state->buffer, state->channels[0]);
        unsigned char *q = fn_iio_buffer_first(state->buffer, state->channels[1]);
        unsigned char *end = fn_iio_buffer_end(state->buffer);
        if (stamp->bytes != (ssize_t)BLOCK_BYTES || fn_iio_buffer_step(state->buffer) != FRAME_BYTES ||
            !first || !q || !end || q != first + 2 || end - first != (ptrdiff_t)BLOCK_BYTES) {
            state->reason = "refill_layout_mismatch"; break;
        }
        /* Preserve every packed source byte before the next refill reuses it.
         * The high four bits are undefined; decode/mask only after capture. */
        memcpy(state->saved + (size_t)b * BLOCK_BYTES, first, BLOCK_BYTES);
        stamp->copy_complete = 1;
        state->completed++;
        if (monotonic(&t)) { state->reason = "clock_error"; break; }
        stamp->copied = t - state->begin;
    }
    if (monotonic(&state->end)) state->reason = "clock_error";
    pthread_mutex_lock(&state->mutex);
    state->done = 1;
    pthread_cond_broadcast(&state->changed);
    pthread_mutex_unlock(&state->mutex);
    return NULL;
}
static void join_failed(int rc) {
    /* Never destroy memory/context still referenced by a live refill worker. */
    printf("{\"schema\":\"rfsig.full_rx_completion.v1\",\"status\":\"join_failed\",\"join_rc\":%d,\"cleanup_unconfirmed\":true,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false}\n", rc);
    fflush(NULL);
    _exit(3);
}

int main(int argc, char **argv) {
    unsigned long blocks = DEFAULT_BLOCKS;
    if (argc < 2 || argc > 3) { fprintf(stderr, "usage: arm-rx-full-p36 NEW_DIRECTORY [BLOCKS_1_TO_64(default16)]\n"); return 2; }
    if (argc == 3) {
        char *end = NULL; errno = 0;
        blocks = strtoul(argv[2], &end, 10);
        if (errno || !end || end == argv[2] || *end || blocks < 1 || blocks > MAX_BLOCKS) return 2;
    }
    if (blocks > SIZE_MAX / BLOCK_BYTES || blocks > SIZE_MAX / sizeof(struct stamp)) return 2;
    if (strlen(argv[1]) > 900 || mkdir(argv[1], 0700)) { perror("new output directory"); return 2; }
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct capture state;
    memset(&state, 0, sizeof state); state.requested = (unsigned int)blocks; state.reason = "setup_failed";
    struct iio_context *ctx = NULL;
    struct iio_device *phy = NULL, *adc = NULL;
    void *library = NULL;
    struct rf_state before, after;
    int status = 1, before_ok = 0, after_ok = 0, buffer_created = 0, context_created = 0;
    int mutex_ready = 0, condition_ready = 0, condition_attributes_ready = 0;
    int worker_started = 0, worker_joined = 0, cancel_requested = 0, scan_cache_disabled = 0;
    unsigned int major = 0, minor = 0;
    pthread_t worker;
    pthread_condattr_t condition_attributes;
    struct sigaction action;
    memset(&action, 0, sizeof action); action.sa_handler = stop_handler; sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) goto release;
    library = dlopen("libiio.so.0", RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); goto release; }
#define LOAD(n) {void *symbol = dlsym(library, #n); if (!symbol) {fprintf(stderr, "missing %s\n", #n); goto release;} _Static_assert(sizeof fn_##n == sizeof symbol, "function pointer width"); memcpy(&fn_##n, &symbol, sizeof symbol);}
    API(LOAD)
    char tag[8] = {0}; fn_iio_library_get_version(&major, &minor, tag);
    if (major != 0 || minor != 20) { state.reason = "unreviewed_libiio_version"; goto release; }
    ctx = fn_iio_create_context_from_uri("local:");
    context_created = ctx != NULL;
    if (!ctx || fn_iio_context_set_timeout(ctx, 3000)) goto release;
    phy = fn_iio_context_find_device(ctx, "ad9361-phy");
    adc = fn_iio_context_find_device(ctx, "cf-ad9361-lpc");
    if (!phy || !adc || read_rf(phy, &before)) { state.reason = "rf_before_mismatch_or_failure"; goto release; }
    before_ok = 1;
    for (unsigned int j = 0; j < fn_iio_device_get_channels_count(adc); j++) fn_iio_channel_disable(fn_iio_device_get_channel(adc, j));
    for (unsigned int j = 0; j < 2; j++) {
        state.channels[j] = fn_iio_device_find_channel(adc, j ? "voltage1" : "voltage0", false);
        if (!state.channels[j]) goto release;
        const struct iio_data_format *f = fn_iio_channel_get_data_format(state.channels[j]);
        if (!f || !fn_iio_channel_is_scan_element(state.channels[j]) || fn_iio_channel_is_output(state.channels[j]) ||
            f->length != 16 || f->bits != 12 || f->shift || !f->is_signed || f->is_be || f->with_scale || f->repeat != 1) {
            state.reason = "unreviewed_scan_format"; goto release;
        }
        fn_iio_channel_enable(state.channels[j]);
    }
    if (fn_iio_device_get_sample_size(adc) != FRAME_BYTES) { state.reason = "wrong_frame_bytes"; goto release; }
    state.saved = malloc((size_t)blocks * BLOCK_BYTES);
    state.stamps = calloc((size_t)blocks, sizeof *state.stamps);
    if (!state.saved || !state.stamps) { state.reason = "allocation_failed"; goto release; }
    /* Volatile first-touch writes cannot be removed as a dead memset by -O2. */
    for (size_t n = 0; n < (size_t)blocks * BLOCK_BYTES; n += 4096) ((volatile unsigned char *)state.saved)[n] = 0;
    for (size_t n = 0; n < (size_t)blocks * sizeof *state.stamps; n += 4096) ((volatile unsigned char *)state.stamps)[n] = 0;
    /* malloc need not be page aligned: touch the final page as well. */
    ((volatile unsigned char *)state.saved)[(size_t)blocks * BLOCK_BYTES - 1] = 0;
    ((volatile unsigned char *)state.stamps)[(size_t)blocks * sizeof *state.stamps - 1] = 0;
    if (pthread_mutex_init(&state.mutex, NULL)) goto release;
    mutex_ready = 1;
    if (pthread_condattr_init(&condition_attributes)) goto release;
    condition_attributes_ready = 1;
    if (pthread_condattr_setclock(&condition_attributes, CLOCK_MONOTONIC) || pthread_cond_init(&state.changed, &condition_attributes)) goto release;
    condition_ready = 1;
    if (stopping) { state.reason = "signal_requested_stop"; goto release; }
    printf("{\"schema\":\"rfsig.full_rx_start.v1\",\"requested_blocks\":%lu,\"frames_per_buffer\":%u,\"frame_bytes\":%u,\"allocated_iq_bytes\":%zu,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false}\n", blocks, BLOCK_FRAMES, FRAME_BYTES, (size_t)blocks * BLOCK_BYTES);
    /* Flush before creating an RX buffer, which may arm DMA already. */
    fflush(stdout);
    state.buffer = fn_iio_device_create_buffer(adc, BLOCK_FRAMES, false);
    buffer_created = state.buffer != NULL;
    if (!state.buffer || monotonic(&state.begin)) goto release;
    if (pthread_create(&worker, NULL, capture_worker, &state)) goto release;
    worker_started = 1;
    pthread_mutex_lock(&state.mutex);
    int wait_failed = 0;
    while (!state.done && !stopping) {
        double t;
        struct timespec until;
        if (monotonic(&t) || t - state.begin >= CAPTURE_LIMIT_S || deadline(&until, CLOCK_MONOTONIC, 0.1)) { wait_failed = 1; break; }
        int rc = pthread_cond_timedwait(&state.changed, &state.mutex, &until);
        if (rc && rc != ETIMEDOUT) { wait_failed = 1; break; }
    }
    cancel_requested = !state.done || stopping || wait_failed;
    pthread_mutex_unlock(&state.mutex);
    if (cancel_requested) fn_iio_buffer_cancel(state.buffer);
    struct timespec join_until;
    if (deadline(&join_until, CLOCK_REALTIME, JOIN_LIMIT_S)) join_failed(errno ? errno : EINVAL);
    int join_rc = pthread_timedjoin_np(worker, NULL, &join_until);
    if (join_rc) join_failed(join_rc);
    worker_joined = 1;
    if (!cancel_requested && !stopping && state.completed == blocks && !strcmp(state.reason, "complete")) status = 0;
    if (wait_failed) state.reason = "main_wait_deadline_or_error";
    else if (cancel_requested) state.reason = "cancel_requested";

release:
    if (worker_started && !worker_joined) join_failed(EINVAL);
    if (state.buffer) { fn_iio_buffer_destroy(state.buffer); state.buffer = NULL; }
    if (before_ok) {
        after_ok = !read_rf(phy, &after) && !memcmp(&before, &after, sizeof before);
        if (!after_ok) { status = 1; state.reason = "rf_after_mismatch_or_failure"; }
    }
    if (adc && fn_iio_device_get_channels_count && fn_iio_device_get_channel && fn_iio_channel_disable) {
        for (unsigned int j = 0; j < fn_iio_device_get_channels_count(adc); j++) fn_iio_channel_disable(fn_iio_device_get_channel(adc, j));
        scan_cache_disabled = 1;
    }
    if (ctx) { fn_iio_context_destroy(ctx); ctx = NULL; }
    if (library) { dlclose(library); library = NULL; }
    if (condition_ready) pthread_cond_destroy(&state.changed);
    if (condition_attributes_ready) pthread_condattr_destroy(&condition_attributes);
    if (mutex_ready) pthread_mutex_destroy(&state.mutex);

    /* All file writes start after the worker and RX/context have released. */
    double save_begin = 0, save_end = 0; (void)monotonic(&save_begin);
    size_t expected_bytes = (size_t)state.completed * BLOCK_BYTES, saved_bytes = 0;
    int raw_complete = 0;
    FILE *raw = new_file(argv[1], "iq-packed.bin");
    if (raw) {
        if (expected_bytes) saved_bytes = fwrite(state.saved, 1, expected_bytes, raw);
        int close_rc = fclose(raw);
        raw_complete = saved_bytes == expected_bytes && close_rc == 0;
    }
    if (!raw_complete) { status = 1; state.reason = "raw_save_failed"; }
    if (before_ok && save_rf(argv[1], "before.txt", &before)) { status = 1; state.reason = "rf_log_save_failed"; }
    if (after_ok && save_rf(argv[1], "after.txt", &after)) { status = 1; state.reason = "rf_log_save_failed"; }
    struct rusage usage; memset(&usage, 0, sizeof usage);
    if (getrusage(RUSAGE_SELF, &usage)) { status = 1; state.reason = "resource_usage_failed"; }
    (void)monotonic(&save_end);
    FILE *meta = new_file(argv[1], "metadata.json");
    if (!meta) { status = 1; state.reason = "metadata_save_failed"; }
    else {
        fprintf(meta, "{\"schema\":\"rfsig.full_returned_buffers.v1\",\"status\":\"%s\",\"reason\":\"%s\",\"requested_blocks\":%lu,\"attempted_refills\":%u,\"completed_blocks\":%u,\"frames_per_buffer\":%u,\"frame_bytes\":%u,\"channels\":[\"voltage0:I\",\"voltage1:Q\"],\"source_format\":\"le:S12/16>>0\",\"storage\":\"original_packed_bytes_high4_undefined\",\"sample_rate_hz\":30720000,\"raw_expected_bytes\":%zu,\"raw_file_bytes_written\":%zu,\"raw_file_complete\":%s,\"complete_returned_buffers_saved\":%s,\"requested_capture_complete\":%s,\"complete_stream_saved\":false,\"lossless_proven\":false,\"known_target_proven\":false,\"hardware_gaps\":\"unknown\",\"adc_first_sample_counter\":null,\"timestamp_clock\":\"CLOCK_MONOTONIC_software_only\",\"libiio_major\":%u,\"libiio_minor\":%u,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"rf_before_valid\":%s,\"rf_after_matches\":%s,\"kernel_queue_count_modified\":false,\"kernel_queue_count\":null,\"buffer_created\":%s,\"buffer_released\":true,\"context_created\":%s,\"context_released\":true,\"scan_cache_disabled\":%s,\"hardware_scan_state_requires_host_readback\":true,\"cleanup_unconfirmed\":false,\"cancel_requested\":%s,\"signal_requested_stop\":%s,\"worker_joined\":%s,\"capture_limit_s\":%.1f,\"join_limit_s\":%.1f,\"acquisition_s\":%.9g,\"post_capture_save_s_before_metadata\":%.9g,\"maxrss_kib\":%ld,\"timestamps\":[",
                status == 0 ? "pass" : "fail", state.reason, blocks, state.attempts, state.completed,
                BLOCK_FRAMES, FRAME_BYTES, expected_bytes, saved_bytes, raw_complete ? "true" : "false",
                raw_complete && state.completed ? "true" : "false", status == 0 ? "true" : "false",
                major, minor, before_ok ? "true" : "false", after_ok ? "true" : "false",
                buffer_created ? "true" : "false", context_created ? "true" : "false", scan_cache_disabled ? "true" : "false",
                cancel_requested ? "true" : "false", stopping ? "true" : "false", worker_joined ? "true" : "false",
                CAPTURE_LIMIT_S, JOIN_LIMIT_S, state.end >= state.begin && worker_joined ? state.end - state.begin : 0,
                save_end >= save_begin ? save_end - save_begin : 0, usage.ru_maxrss);
        for (unsigned int j = 0; j < state.attempts; j++) {
            const struct stamp *s = &state.stamps[j];
            fprintf(meta, "%s{\"block_index\":%u,\"file_byte_offset\":%zu,\"refill_bytes\":%zd,\"refill_start_s\":%.9g,\"refill_end_s\":%.9g,\"copy_end_s\":%.9g,\"copy_complete\":%s}",
                    j ? "," : "", j, (size_t)j * BLOCK_BYTES, s->bytes, s->start, s->refill, s->copied, s->copy_complete ? "true" : "false");
        }
        fprintf(meta, "]}\n");
        int bad = ferror(meta);
        if (fclose(meta)) bad = 1;
        if (bad) { status = 1; state.reason = "metadata_save_failed"; }
    }
    free(state.saved); free(state.stamps);
    printf("{\"schema\":\"rfsig.full_rx_completion.v1\",\"status\":\"%s\",\"reason\":\"%s\",\"exit_status\":%d,\"completed_blocks\":%u,\"raw_file_bytes_written\":%zu,\"rf_after_matches\":%s,\"buffer_released\":true,\"context_released\":true,\"cleanup_unconfirmed\":false,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false}\n", status == 0 ? "pass" : "fail", state.reason, status, state.completed, saved_bytes, after_ok ? "true" : "false");
    return status;
}
