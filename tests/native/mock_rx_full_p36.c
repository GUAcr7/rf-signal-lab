/* Test-only IIO 0.x ABI surface; never used on a receiver. */
#define _POSIX_C_SOURCE 200809L
#include "iio.h"
#include <errno.h>
#include <signal.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>
#include <stdatomic.h>
#include <unistd.h>

struct iio_context { int unused; };
struct iio_device { int kind; };
struct iio_channel { int index; };
struct iio_buffer { unsigned char *data; size_t size; unsigned int block; atomic_int canceled; };
static struct iio_context ctx;
static struct iio_device phy = {1}, adc = {2};
static struct iio_channel channels[4] = {{0},{1},{2},{3}}, lo = {9};
static unsigned int enabled, destroyed, refills, created;
static int fault(const char *name) { const char *f = getenv("P36_MOCK_FAULT"); return f && !strcmp(f, name); }
static void delay_ms(unsigned int ms) {
    struct timespec t = {(time_t)(ms / 1000), (long)(ms % 1000) * 1000000L};
    while (nanosleep(&t, &t) && errno == EINTR) {}
}
void iio_library_get_version(unsigned int *major, unsigned int *minor, char tag[8]) {
    *major = 0; *minor = fault("version") ? 24 : 20; memcpy(tag, "mock\0\0\0", 8);
}
struct iio_context *iio_create_context_from_uri(const char *uri) { return !strcmp(uri, "local:") ? &ctx : NULL; }
void iio_context_destroy(struct iio_context *c) {
    (void)c;
    const char *p = getenv("P36_MOCK_LOG");
    if (p) {
        FILE *f = fopen(p, "w");
        if (f) { fprintf(f, "destroyed=%u enabled=%u created=%u refills=%u\n", destroyed, enabled, created, refills); fclose(f); }
    }
}
int iio_context_set_timeout(struct iio_context *c, unsigned int t) { (void)c; return t == 3000 ? 0 : -1; }
struct iio_device *iio_context_find_device(const struct iio_context *c, const char *name) {
    (void)c; return !strcmp(name, "ad9361-phy") ? &phy : !strcmp(name, "cf-ad9361-lpc") ? &adc : NULL;
}
struct iio_channel *iio_device_find_channel(const struct iio_device *d, const char *name, bool output) {
    (void)d;
    if (output) return !strcmp(name, "altvoltage0") ? &lo : NULL;
    return !strcmp(name, "voltage0") ? &channels[0] : !strcmp(name, "voltage1") ? &channels[1] : NULL;
}
unsigned int iio_device_get_channels_count(const struct iio_device *d) { (void)d; return 4; }
struct iio_channel *iio_device_get_channel(const struct iio_device *d, unsigned int n) { (void)d; return n < 4 ? &channels[n] : NULL; }
void iio_channel_disable(struct iio_channel *c) { enabled &= ~(1u << c->index); }
void iio_channel_enable(struct iio_channel *c) { enabled |= 1u << c->index; }
bool iio_channel_is_scan_element(const struct iio_channel *c) { return c->index < 4; }
bool iio_channel_is_output(const struct iio_channel *c) { return c->index == 9; }
const struct iio_data_format *iio_channel_get_data_format(const struct iio_channel *c) {
    (void)c;
    static struct iio_data_format format = {.length=16, .bits=12, .shift=0, .is_signed=true, .repeat=1};
    format.bits = fault("format") ? 16 : 12;
    return &format;
}
ssize_t iio_device_get_sample_size(const struct iio_device *d) { (void)d; return enabled == 3 && !fault("sample_size") ? 4 : 8; }
struct iio_buffer *iio_device_create_buffer(const struct iio_device *d, size_t frames, bool cyclic) {
    (void)d;
    if (frames != 65536 || cyclic || fault("create")) return NULL;
    struct iio_buffer *b = calloc(1, sizeof *b);
    if (!b) return NULL;
    b->size = frames * 4; b->data = malloc(b->size);
    if (!b->data) { free(b); return NULL; }
    created++; return b;
}
ssize_t iio_buffer_refill(struct iio_buffer *b) {
    if (fault("join_hang")) {
        /* Main receives a normal process signal; this worker ignores cancel.
         * It must be terminated by process exit without destroying its buffer. */
        raise(SIGTERM);
        delay_ms(10000);
    }
    if ((fault("cancel") || fault("signal_stop")) && b->block == 3) {
        raise(SIGTERM);
        while (!atomic_load(&b->canceled)) delay_ms(1);
    }
    if (atomic_load(&b->canceled)) return -ECANCELED;
    if (fault("refill") && b->block == 3) return -EIO;
    for (size_t n = 0; n < b->size / 4; n++) {
        unsigned int value = (unsigned int)((b->block * 97 + n) & 4095u);
        /* Deliberately set undefined high bits. Raw recorder must preserve
         * them; decoders must ignore them when interpreting signal values. */
        uint16_t i = (uint16_t)(value | ((b->block & 15u) << 12));
        uint16_t q = (uint16_t)((4095u - value) | (((b->block + 5u) & 15u) << 12));
        b->data[4*n] = (unsigned char)i; b->data[4*n+1] = (unsigned char)(i >> 8);
        b->data[4*n+2] = (unsigned char)q; b->data[4*n+3] = (unsigned char)(q >> 8);
    }
    b->block++; refills++;
    return fault("short") && b->block == 4 ? (ssize_t)b->size - 4 : (ssize_t)b->size;
}
void iio_buffer_cancel(struct iio_buffer *b) { atomic_store(&b->canceled, 1); }
void iio_buffer_destroy(struct iio_buffer *b) { destroyed++; free(b->data); free(b); }
void *iio_buffer_first(const struct iio_buffer *b, const struct iio_channel *c) {
    if (fault("null_i") && c->index == 0) return NULL;
    return b->data + (fault("iq_offset") && c->index == 1 ? 4 : c->index * 2);
}
void *iio_buffer_end(const struct iio_buffer *b) { return b->data + b->size - (fault("end") ? 4 : 0); }
ptrdiff_t iio_buffer_step(const struct iio_buffer *b) { (void)b; return fault("step") ? 8 : 4; }
ssize_t iio_channel_attr_read(const struct iio_channel *c, const char *name, char *value, size_t size) {
    (void)c;
    const char *s = !strcmp(name,"sampling_frequency") ? "30720000" : !strcmp(name,"rf_bandwidth") ? "18000000" :
        !strcmp(name,"gain_control_mode") ? "manual" : !strcmp(name,"hardwaregain") ? "0.000000 dB" :
        !strcmp(name,"rf_port_select") ? "A_BALANCED" : !strcmp(name,"frequency") ? "2450000000" : "bad";
    if ((fault("config") || (fault("after_config") && destroyed)) && !strcmp(name,"gain_control_mode")) s = "slow_attack";
    return snprintf(value, size, "%s", s);
}
ssize_t iio_device_debug_attr_read(const struct iio_device *d, const char *name, char *value, size_t size) {
    (void)d; (void)name;
    return snprintf(value, size, "%s", fault("bist") ? "1" : fault("empty_bist") ? "" : "0");
}
