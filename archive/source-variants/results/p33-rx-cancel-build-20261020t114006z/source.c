/* Bounded receive-only libiio cancellation/recreation diagnostic.
 * No RF writes or TX API. Refills are structural checks, not lossless IQ or
 * known-target evidence. The active flag is a software observation: refill
 * can return between observation and iio_buffer_cancel().
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
#include <time.h>
#include <unistd.h>

#define CYCLES 8u
#define BLOCK_FRAMES 65536u
#define BLOCK_BYTES (BLOCK_FRAMES * 4u)
#define MAX_REFILLS 512u
#define READY_TIMEOUT_S 0.5
#define JOIN_TIMEOUT_S 3.5
#define IMMEDIATE_LIMIT_S 0.25
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
static void stop_handler(int signal_number) { (void)signal_number; stopping = 1; }

static double now(void) {
    struct timespec t;
    if (clock_gettime(CLOCK_MONOTONIC, &t)) { perror("clock_gettime"); exit(2); }
    return t.tv_sec + t.tv_nsec * 1e-9;
}
static int deadline(struct timespec *t, clockid_t clock_id, double seconds) {
    if (clock_gettime(clock_id, t)) return -1;
    t->tv_sec += (time_t)seconds;
    t->tv_nsec += (long)((seconds - (time_t)seconds) * 1e9);
    if (t->tv_nsec >= 1000000000L) { t->tv_sec++; t->tv_nsec -= 1000000000L; }
    return 0;
}

struct rf_state { char value[9][128]; };
static int read_attr(char *destination, size_t size, struct iio_channel *channel,
                     const char *attribute, const char *expected) {
    ssize_t n = fn_iio_channel_attr_read(channel, attribute, destination, size - 1);
    if (n < 0 || n >= (ssize_t)size) return -1;
    destination[n] = 0;
    destination[strcspn(destination, "\r\n")] = 0;
    if (strcmp(destination, expected)) {
        fprintf(stderr, "RF config mismatch %s=%s\n", attribute, destination);
        return -1;
    }
    return 0;
}
static int read_rf(struct iio_device *phy, struct rf_state *state) {
    struct iio_channel *rx = fn_iio_device_find_channel(phy, "voltage0", false);
    struct iio_channel *lo = fn_iio_device_find_channel(phy, "altvoltage0", true);
    memset(state, 0, sizeof *state);
    if (!rx || !lo) return -1;
    const char *names[] = {"sampling_frequency", "rf_bandwidth", "gain_control_mode", "hardwaregain", "rf_port_select", "frequency"};
    const char *expected[] = {"30720000", "18000000", "manual", "0.000000 dB", "A_BALANCED", "2450000000"};
    for (unsigned int j = 0; j < 6; j++)
        if (read_attr(state->value[j], sizeof state->value[j], j == 5 ? lo : rx,
                      names[j], expected[j])) return -1;
    const char *debug_names[] = {"bist_prbs", "bist_tone", "loopback"};
    for (unsigned int j = 0; j < 3; j++) {
        char *value = state->value[j + 6];
        ssize_t n = fn_iio_device_debug_attr_read(phy, debug_names[j], value, 127);
        if (n < 0 || n >= 128) return -1;
        value[n] = 0;
        value[strcspn(value, "\r\n")] = 0;
        if (!*value || strspn(value, "0 \t") != strlen(value)) {
            fprintf(stderr, "BIST config mismatch %s=%s\n", debug_names[j], value);
            return -1;
        }
    }
    return 0;
}
static void print_rf(const char *phase, const struct rf_state *state) {
    const char *keys[] = {"sampling_frequency", "rf_bandwidth", "gain_control_mode", "hardwaregain", "rf_port_select", "rx_lo_hz", "bist_prbs", "bist_tone", "loopback"};
    /* Values are emitted only after matching the fixed ASCII expectations. */
    printf("{\"schema\":\"rfsig.rx_cancel_rf.v1\",\"phase\":\"%s\"", phase);
    for (unsigned int j = 0; j < 9; j++) printf(",\"%s\":\"%s\"", keys[j], state->value[j]);
    printf("}\n");
}
static int valid_refill(struct iio_buffer *buffer, struct iio_channel **channels, ssize_t bytes) {
    if (bytes != (ssize_t)BLOCK_BYTES || fn_iio_buffer_step(buffer) != 4) return 0;
    unsigned char *first = fn_iio_buffer_first(buffer, channels[0]);
    unsigned char *q = fn_iio_buffer_first(buffer, channels[1]);
    unsigned char *end = fn_iio_buffer_end(buffer);
    return first && q && end && q == first + 2 && end - first == (ptrdiff_t)BLOCK_BYTES;
}

struct refill_state {
    struct iio_buffer *buffer;
    struct iio_channel **channels;
    pthread_mutex_t mutex;
    pthread_cond_t changed;
    unsigned int completed, attempts;
    int active, done, cancel_requested, negative_after_cancel, layout_error;
    ssize_t terminal;
};
static void *refill_worker(void *argument) {
    struct refill_state *state = argument;
    for (unsigned int k = 0; k < MAX_REFILLS; k++) {
        pthread_mutex_lock(&state->mutex);
        state->active = 1;
        state->attempts++;
        pthread_cond_broadcast(&state->changed);
        pthread_mutex_unlock(&state->mutex);
        ssize_t bytes = fn_iio_buffer_refill(state->buffer);
        int layout_ok = bytes < 0 || valid_refill(state->buffer, state->channels, bytes);
        pthread_mutex_lock(&state->mutex);
        state->active = 0;
        if (bytes < 0) {
            state->terminal = bytes;
            state->negative_after_cancel = state->cancel_requested;
            state->done = 1;
        } else if (!layout_ok) {
            state->layout_error = 1;
            state->done = 1;
        } else {
            state->completed++;
        }
        pthread_cond_broadcast(&state->changed);
        int done = state->done;
        pthread_mutex_unlock(&state->mutex);
        if (done) return NULL;
    }
    pthread_mutex_lock(&state->mutex);
    state->done = 1;
    pthread_cond_broadcast(&state->changed);
    pthread_mutex_unlock(&state->mutex);
    return NULL;
}

/* On a failed timed join, no thread-unsafe buffer/context destruction is
 * attempted. Process exit closes descriptors; the host must inspect kernel,
 * buffer and scan state independently before any further experiment. */
static void join_failure(int rc, unsigned int cycle) {
    fprintf(stderr, "worker join failed rc=%d\n", rc);
    printf("{\"schema\":\"rfsig.rx_cancel_completion.v1\",\"status\":\"join_failed\",\"cycle\":%u,\"join_rc\":%d,\"cleanup_unconfirmed\":true,\"RF_attributes_written\":false,\"TX_API_loaded\":false}\n", cycle, rc);
    fflush(NULL);
    _exit(3);
}

int main(int argc, char **argv) {
    (void)argv;
    if (argc != 1) { fprintf(stderr, "usage: arm-rx-cancel\n"); return 2; }
    struct iio_context *ctx = NULL;
    struct iio_device *adc = NULL, *phy = NULL;
    struct iio_buffer *buffer = NULL;
    struct iio_channel *channels[2] = {NULL, NULL};
    void *library = NULL;
    struct rf_state before, after;
    int status = 1, rf_read_before = 0, rf_after_ok = 0;
    unsigned int completed_cycles = 0;
    setvbuf(stdout, NULL, _IOLBF, 0);
    struct sigaction action;
    memset(&action, 0, sizeof action);
    action.sa_handler = stop_handler;
    sigemptyset(&action.sa_mask);
    if (sigaction(SIGINT, &action, NULL) || sigaction(SIGTERM, &action, NULL)) {
        perror("sigaction"); goto done;
    }
    library = dlopen("libiio.so.0", RTLD_NOW | RTLD_LOCAL);
    if (!library) { fprintf(stderr, "%s\n", dlerror()); goto done; }
#define LOAD(n) {void *symbol = dlsym(library, #n); if (!symbol) {fprintf(stderr, "missing %s\n", #n); goto done;} _Static_assert(sizeof fn_##n == sizeof symbol, "function pointer width"); memcpy(&fn_##n, &symbol, sizeof symbol);}
    API(LOAD)
    unsigned int major = 0, minor = 0;
    char tag[8] = {0};
    fn_iio_library_get_version(&major, &minor, tag);
    printf("{\"schema\":\"rfsig.rx_cancel_start.v1\",\"libiio_major\":%u,\"libiio_minor\":%u,\"cycles\":%u,\"frames_per_buffer\":%u,\"max_worker_refills\":%u,\"context_timeout_ms\":3000,\"join_timeout_s\":%.1f,\"readiness_timeout_s\":%.1f,\"immediate_refill_limit_s\":%.2f,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false,\"known_target_proven\":false,\"active_is_software_observation\":true}\n", major, minor, CYCLES, BLOCK_FRAMES, MAX_REFILLS, JOIN_TIMEOUT_S, READY_TIMEOUT_S, IMMEDIATE_LIMIT_S);
    if (major != 0 || minor != 20) { fprintf(stderr, "requires reviewed receiver libiio 0.20\n"); goto done; }
    ctx = fn_iio_create_context_from_uri("local:");
    if (!ctx || fn_iio_context_set_timeout(ctx, 3000)) goto done;
    phy = fn_iio_context_find_device(ctx, "ad9361-phy");
    adc = fn_iio_context_find_device(ctx, "cf-ad9361-lpc");
    if (!phy || !adc || read_rf(phy, &before)) goto done;
    rf_read_before = 1;
    print_rf("before", &before);
    for (unsigned int j = 0; j < fn_iio_device_get_channels_count(adc); j++)
        fn_iio_channel_disable(fn_iio_device_get_channel(adc, j));
    for (unsigned int j = 0; j < 2; j++) {
        channels[j] = fn_iio_device_find_channel(adc, j ? "voltage1" : "voltage0", false);
        if (!channels[j]) goto done;
        const struct iio_data_format *format = fn_iio_channel_get_data_format(channels[j]);
        if (!format || !fn_iio_channel_is_scan_element(channels[j]) ||
            fn_iio_channel_is_output(channels[j]) || format->length != 16 ||
            format->bits != 12 || format->shift || !format->is_signed ||
            format->is_be || format->with_scale || format->repeat != 1) {
            fprintf(stderr, "unreviewed RX1 I/Q scan format\n"); goto done;
        }
        fn_iio_channel_enable(channels[j]);
    }
    if (fn_iio_device_get_sample_size(adc) != 4) { fprintf(stderr, "wrong sample size\n"); goto done; }

    for (unsigned int cycle = 1; cycle <= CYCLES; cycle++) {
        struct refill_state state;
        pthread_t worker;
        pthread_condattr_t condition_attributes;
        int mutex_ready = 0, condition_ready = 0, attributes_ready = 0;
        int ready = 0, cycle_ok = 0, active_observed = 0, wait_rc = 0;
        ssize_t canceled_result = 0;
        double join_elapsed = 0, canceled_elapsed = 0;
        unsigned int recovered = 0;
        memset(&state, 0, sizeof state);
        if (stopping) break;
        buffer = fn_iio_device_create_buffer(adc, BLOCK_FRAMES, false);
        if (!buffer) { perror("create buffer"); goto done; }
        state.buffer = buffer;
        state.channels = channels;
        if (pthread_mutex_init(&state.mutex, NULL)) goto cycle_cleanup;
        mutex_ready = 1;
        if (pthread_condattr_init(&condition_attributes)) goto cycle_cleanup;
        attributes_ready = 1;
        if (pthread_condattr_setclock(&condition_attributes, CLOCK_MONOTONIC) ||
            pthread_cond_init(&state.changed, &condition_attributes)) goto cycle_cleanup;
        condition_ready = 1;
        struct timespec ready_until;
        if (deadline(&ready_until, CLOCK_MONOTONIC, READY_TIMEOUT_S)) goto cycle_cleanup;
        if (pthread_create(&worker, NULL, refill_worker, &state)) goto cycle_cleanup;
        pthread_mutex_lock(&state.mutex);
        while (!stopping && !state.done && !(state.completed >= 2 && state.active)) {
            wait_rc = pthread_cond_timedwait(&state.changed, &state.mutex, &ready_until);
            if (wait_rc) break;
        }
        ready = !stopping && !state.done && state.completed >= 2 && state.active;
        active_observed = state.active;
        state.cancel_requested = 1;
        pthread_mutex_unlock(&state.mutex);
        /* Thread-safe API is deliberately called from the main thread,
         * never from a signal handler and never pthread_cancel(). */
        double join_started = now();
        fn_iio_buffer_cancel(buffer);
        struct timespec join_until;
        if (deadline(&join_until, CLOCK_REALTIME, JOIN_TIMEOUT_S)) join_failure(errno ? errno : EINVAL, cycle);
        int join_rc = pthread_timedjoin_np(worker, NULL, &join_until);
        if (join_rc) join_failure(join_rc, cycle);
        join_elapsed = now() - join_started;
        double canceled_started = now();
        canceled_result = fn_iio_buffer_refill(buffer);
        canceled_elapsed = now() - canceled_started;
        cycle_ok = ready && !state.layout_error && state.terminal < 0 &&
                   state.negative_after_cancel && canceled_result < 0 &&
                   canceled_elapsed <= IMMEDIATE_LIMIT_S && !stopping;
        fn_iio_buffer_destroy(buffer);
        buffer = NULL;
        if (cycle_ok) {
            buffer = fn_iio_device_create_buffer(adc, BLOCK_FRAMES, false);
            if (!buffer) { perror("recreate buffer"); cycle_ok = 0; }
            for (unsigned int j = 0; cycle_ok && j < 2; j++) {
                ssize_t bytes = fn_iio_buffer_refill(buffer);
                if (stopping || !valid_refill(buffer, channels, bytes)) cycle_ok = 0;
                else recovered++;
            }
            if (buffer) { fn_iio_buffer_destroy(buffer); buffer = NULL; }
        }
        struct rf_state current;
        int rf_unchanged = !read_rf(phy, &current) && !memcmp(&before, &current, sizeof before);
        if (!rf_unchanged) cycle_ok = 0;
        printf("{\"schema\":\"rfsig.rx_cancel_cycle.v1\",\"cycle\":%u,\"status\":\"%s\",\"ready\":%s,\"readiness_wait_rc\":%d,\"active_observed_at_request\":%s,\"active_observation_races_return\":true,\"worker_attempts\":%u,\"worker_completed\":%u,\"worker_terminal_result\":%zd,\"negative_observed_after_request\":%s,\"layout_error\":%s,\"cancel_join_elapsed_s\":%.9g,\"canceled_buffer_refill_result\":%zd,\"canceled_buffer_refill_elapsed_s\":%.9g,\"recovery_refills\":%u,\"rf_unchanged\":%s,\"RF_attributes_written\":false,\"complete_stream_saved\":false}\n", cycle, cycle_ok ? "pass" : "fail", ready ? "true" : "false", wait_rc, active_observed ? "true" : "false", state.attempts, state.completed, state.terminal, state.negative_after_cancel ? "true" : "false", state.layout_error ? "true" : "false", join_elapsed, canceled_result, canceled_elapsed, recovered, rf_unchanged ? "true" : "false");
cycle_cleanup:
        if (condition_ready) pthread_cond_destroy(&state.changed);
        if (attributes_ready) pthread_condattr_destroy(&condition_attributes);
        if (mutex_ready) pthread_mutex_destroy(&state.mutex);
        if (buffer) { fn_iio_buffer_destroy(buffer); buffer = NULL; }
        if (!cycle_ok) goto done;
        completed_cycles++;
    }
    if (completed_cycles == CYCLES && !stopping) status = 0;
done:
    if (buffer) fn_iio_buffer_destroy(buffer);
    if (rf_read_before) {
        rf_after_ok = !read_rf(phy, &after) && !memcmp(&before, &after, sizeof before);
        if (rf_after_ok) print_rf("after", &after);
        else { fprintf(stderr, "RF after readback mismatch or failure\n"); status = 1; }
    }
    if (adc && fn_iio_device_get_channels_count && fn_iio_device_get_channel && fn_iio_channel_disable)
        for (unsigned int j = 0; j < fn_iio_device_get_channels_count(adc); j++)
            fn_iio_channel_disable(fn_iio_device_get_channel(adc, j));
    if (ctx) fn_iio_context_destroy(ctx);
    if (library) dlclose(library);
    printf("{\"schema\":\"rfsig.rx_cancel_completion.v1\",\"status\":\"%s\",\"exit_status\":%d,\"completed_cycles\":%u,\"expected_cycles\":%u,\"rf_after_matches\":%s,\"cleanup_unconfirmed\":false,\"buffer_released\":true,\"scan_cache_disabled\":true,\"context_released\":true,\"hardware_scan_state_requires_host_readback\":true,\"signal_requested_stop\":%s,\"RF_attributes_written\":false,\"TX_API_loaded\":false,\"lossless_proven\":false,\"known_target_proven\":false}\n", status == 0 ? "pass" : "fail", status, completed_cycles, CYCLES, rf_after_ok ? "true" : "false", stopping ? "true" : "false");
    return status;
}
