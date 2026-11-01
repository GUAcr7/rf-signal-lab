#include "fixed_fir.h"
#include <errno.h>
#include <inttypes.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

/* One bounded hexadecimal word per line. Reject signs, prefixes, comments,
 * embedded NUL, excess digits, extra tokens and unused high bits. */
static int read_hex(FILE *file, unsigned bits, uint32_t *word)
{
    int c, trailing = 0;
    unsigned digits = 0u, bytes = 0u, digit;
    uint32_t value = 0u;
    while ((c = fgetc(file)) != EOF && c != '\n') {
        if (++bytes > 128u) return -1;
        if (c == ' ' || c == '\t' || c == '\r') { if (digits != 0u) trailing = 1; continue; }
        if (trailing) return -1;
        if (c >= '0' && c <= '9') digit = (unsigned)(c - '0');
        else if (c >= 'a' && c <= 'f') digit = (unsigned)(c - 'a') + 10u;
        else if (c >= 'A' && c <= 'F') digit = (unsigned)(c - 'A') + 10u;
        else return -1;
        if (++digits > (bits + 3u) / 4u) return -1;
        value = value * 16u + digit;
    }
    if (ferror(file)) return -1;
    if (digits == 0u) return c == EOF && bytes == 0u ? 0 : -1;
    if (value >= (UINT32_C(1) << bits)) return -1;
    *word = value;
    return 1;
}

static int32_t decode(uint32_t word, unsigned bits)
{
    /* Both casts are in-range; avoid implementation-defined unsigned-to-signed conversion. */
    int32_t value = (int32_t)word;
    if (word >= (UINT32_C(1) << (bits - 1u))) value -= (int32_t)(UINT32_C(1) << bits);
    return value;
}

static int emit(const rf_fir_output *output)
{
    return printf("%d,%d,%u,%u,%" PRId64 ",%" PRId64 "\n", (int)output->i, (int)output->q,
                  (unsigned)output->saturated_i, (unsigned)output->saturated_q,
                  output->accumulator_i, output->accumulator_q) < 0 ? -1 : 0;
}

static int run_stream(rf_fir_state *state, const char *i_path, const char *q_path)
{
    FILE *input_i = fopen(i_path, "rb"), *input_q = fopen(q_path, "rb");
    rf_fir_output output, tail[RF_FIR_MAX_TAPS - 1u];
    uint32_t i_word, q_word;
    size_t inputs = 0u, tail_count, k;
    int i_status, q_status, ok = 0;
    if (input_i == NULL || input_q == NULL) { fprintf(stderr, "Cannot open I/Q inputs\n"); goto done; }
    for (;;) {
        i_status = read_hex(input_i, 12u, &i_word);
        q_status = read_hex(input_q, 12u, &q_word);
        if (i_status < 0 || q_status < 0 || i_status != q_status) {
            fprintf(stderr, "Invalid I/Q word or unequal lengths at sample %zu\n", inputs); goto done;
        }
        if (i_status == 0) break;
        if (rf_fir_push(state, (int16_t)decode(i_word, 12u), (int16_t)decode(q_word, 12u), &output) != RF_FIR_OK || emit(&output) != 0)
            goto done;
        ++inputs;
    }
    if (inputs == 0u) { fprintf(stderr, "Input stream must be nonempty\n"); goto done; }
    if (rf_fir_finish(state, tail, RF_FIR_MAX_TAPS - 1u, &tail_count) != RF_FIR_OK) goto done;
    for (k = 0u; k < tail_count; ++k) if (emit(&tail[k]) != 0) goto done;
    ok = 1;
done:
    if (input_i != NULL && fclose(input_i) != 0) ok = 0;
    if (input_q != NULL && fclose(input_q) != 0) ok = 0;
    return ok ? 0 : 1;
}

int main(int argc, char **argv)
{
    rf_fir_state state;
    int32_t coefficients[RF_FIR_MAX_TAPS];
    uint32_t word;
    size_t taps = 0u;
    FILE *coefficient_file;
    int status, replay = 0;
    if (argc == 3 && strcmp(argv[1], "--quantize") == 0) {
        char *end;
        intmax_t value;
        int16_t count;
        uint8_t saturated;
        errno = 0;
        value = strtoimax(argv[2], &end, 10);
        if (errno != 0 || end == argv[2] || *end != '\0' || value < INT64_MIN || value > INT64_MAX ||
            rf_fir_quantize_accumulator((int64_t)value, &count, &saturated) != RF_FIR_OK) return 2;
        return printf("%d,%u\n", (int)count, (unsigned)saturated) < 0 ? 1 : 0;
    }
    if (argc == 5 && strcmp(argv[4], "--reset-replay") == 0) replay = 1;
    else if (argc != 4) {
        fprintf(stderr, "Usage: fir_hex_cli coefficients.hex input_i.hex input_q.hex [--reset-replay]\n"); return 2;
    }
    coefficient_file = fopen(argv[1], "rb");
    if (coefficient_file == NULL) { fprintf(stderr, "Cannot open coefficients\n"); return 2; }
    while ((status = read_hex(coefficient_file, 18u, &word)) == 1) {
        if (taps == RF_FIR_MAX_TAPS) { status = -1; break; }
        coefficients[taps++] = decode(word, 18u);
    }
    if (fclose(coefficient_file) != 0 || status < 0 || rf_fir_init(&state, coefficients, taps) != RF_FIR_OK) {
        fprintf(stderr, "Invalid coefficients: require 1 through 63 signed 18-bit words\n"); return 2;
    }
    if (run_stream(&state, argv[2], argv[3]) != 0) return 1;
    if (replay && (rf_fir_reset(&state) != RF_FIR_OK || run_stream(&state, argv[2], argv[3]) != 0)) return 1;
    return fflush(stdout) == 0 ? 0 : 1;
}
