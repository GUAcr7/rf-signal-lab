#ifndef RFSIG_FIXED_FIR_H
#define RFSIG_FIXED_FIR_H
#include <stddef.h>
#include <stdint.h>

#define RF_FIR_MAX_TAPS 63u
#define RF_FIR_ACC_MIN (-INT64_C(34359738368))
#define RF_FIR_ACC_MAX INT64_C(34359738367)

typedef enum {
    RF_FIR_OK = 0, RF_FIR_ARGUMENT, RF_FIR_INPUT_RANGE,
    RF_FIR_COEFFICIENT_RANGE, RF_FIR_ACCUMULATOR_RANGE,
    RF_FIR_CLOSED, RF_FIR_CAPACITY
} rf_fir_status;

typedef struct {
    int16_t i, q;
    uint8_t saturated_i, saturated_q;
    int64_t accumulator_i, accumulator_q;
} rf_fir_output;

/* Initialize before all other calls; preserve this object between samples.
 * Coefficient 0 multiplies the current input. No heap or global state. */
typedef struct {
    int32_t coefficients[RF_FIR_MAX_TAPS];
    int16_t history_i[RF_FIR_MAX_TAPS], history_q[RF_FIR_MAX_TAPS];
    size_t taps, head;
    uint8_t has_input, closed;
} rf_fir_state;

rf_fir_status rf_fir_init(rf_fir_state *state, const int32_t *coefficients, size_t taps);
rf_fir_status rf_fir_reset(rf_fir_state *state);
/* Rejected samples do not advance state or overwrite output. */
rf_fir_status rf_fir_push(rf_fir_state *state, int16_t i, int16_t q, rf_fir_output *output);
/* Emit M-1 zero-input tail samples, then close. Empty streams emit no tail.
 * Insufficient capacity changes neither state nor output. Reset permits reuse. */
rf_fir_status rf_fir_finish(rf_fir_state *state, rf_fir_output *tail, size_t capacity, size_t *written);
rf_fir_status rf_fir_quantize_accumulator(int64_t value, int16_t *count, uint8_t *saturated);
#endif
