#include "fixed_fir.h"
#include <string.h>

static int valid_state(const rf_fir_state *state)
{
    return state != NULL && state->taps >= 1u && state->taps <= RF_FIR_MAX_TAPS && state->head < state->taps;
}

rf_fir_status rf_fir_init(rf_fir_state *state, const int32_t *coefficients, size_t taps)
{
    rf_fir_state fresh;
    size_t k;
    if (state == NULL || coefficients == NULL || taps < 1u || taps > RF_FIR_MAX_TAPS)
        return RF_FIR_ARGUMENT;
    for (k = 0u; k < taps; ++k)
        if (coefficients[k] < -131072 || coefficients[k] > 131071)
            return RF_FIR_COEFFICIENT_RANGE;
    memset(&fresh, 0, sizeof fresh);
    fresh.taps = taps;
    for (k = 0u; k < taps; ++k) fresh.coefficients[k] = coefficients[k];
    *state = fresh;
    return RF_FIR_OK;
}

rf_fir_status rf_fir_reset(rf_fir_state *state)
{
    if (!valid_state(state)) return RF_FIR_ARGUMENT;
    memset(state->history_i, 0, sizeof state->history_i);
    memset(state->history_q, 0, sizeof state->history_q);
    state->head = 0u;
    state->has_input = 0u;
    state->closed = 0u;
    return RF_FIR_OK;
}

rf_fir_status rf_fir_quantize_accumulator(int64_t value, int16_t *count, uint8_t *saturated)
{
    uint64_t magnitude, quotient, remainder;
    int64_t rounded;
    if (count == NULL || saturated == NULL) return RF_FIR_ARGUMENT;
    if (value < RF_FIR_ACC_MIN || value > RF_FIR_ACC_MAX) return RF_FIR_ACCUMULATOR_RANGE;
    /* The checked 36-bit value can safely be negated in int64_t.
     * Divide an unsigned magnitude: no signed shifts or INT64_MIN negation. */
    magnitude = (uint64_t)(value < 0 ? -value : value);
    quotient = magnitude / UINT64_C(131072);
    remainder = magnitude % UINT64_C(131072);
    if (remainder > UINT64_C(65536) || (remainder == UINT64_C(65536) && quotient % 2u != 0u))
        ++quotient;
    rounded = (int64_t)quotient;
    if (value < 0) rounded = -rounded;
    *saturated = 0u;
    if (rounded > 32767) { rounded = 32767; *saturated = 1u; }
    else if (rounded < -32768) { rounded = -32768; *saturated = 1u; }
    *count = (int16_t)rounded;
    return RF_FIR_OK;
}

rf_fir_status rf_fir_push(rf_fir_state *state, int16_t i, int16_t q, rf_fir_output *output)
{
    rf_fir_output result;
    size_t k, index, next_head;
    rf_fir_status status;
    if (!valid_state(state) || output == NULL) return RF_FIR_ARGUMENT;
    if (state->closed != 0u) return RF_FIR_CLOSED;
    if (i < -2048 || i > 2047 || q < -2048 || q > 2047) return RF_FIR_INPUT_RANGE;
    result.accumulator_i = (int64_t)i * (int64_t)state->coefficients[0];
    result.accumulator_q = (int64_t)q * (int64_t)state->coefficients[0];
    index = state->head;
    for (k = 1u; k < state->taps; ++k) {
        result.accumulator_i += (int64_t)state->history_i[index] * (int64_t)state->coefficients[k];
        result.accumulator_q += (int64_t)state->history_q[index] * (int64_t)state->coefficients[k];
        index = (index + 1u) % state->taps;
    }
    /* All legal sums satisfy |acc| <= 63*2048*131072 = 16911433728.
     * The int64_t calculation is exact; 36-bit overflow never wraps. */
    status = rf_fir_quantize_accumulator(result.accumulator_i, &result.i, &result.saturated_i);
    if (status != RF_FIR_OK) return status;
    status = rf_fir_quantize_accumulator(result.accumulator_q, &result.q, &result.saturated_q);
    if (status != RF_FIR_OK) return status;
    next_head = (state->head + state->taps - 1u) % state->taps;
    state->history_i[next_head] = i;
    state->history_q[next_head] = q;
    state->head = next_head;
    state->has_input = 1u;
    *output = result;
    return RF_FIR_OK;
}

rf_fir_status rf_fir_finish(rf_fir_state *state, rf_fir_output *tail, size_t capacity, size_t *written)
{
    size_t k, needed;
    rf_fir_status status;
    if (!valid_state(state) || written == NULL) return RF_FIR_ARGUMENT;
    if (state->closed != 0u) return RF_FIR_CLOSED;
    needed = state->has_input != 0u ? state->taps - 1u : 0u;
    if (capacity < needed) return RF_FIR_CAPACITY;
    if (needed != 0u && tail == NULL) return RF_FIR_ARGUMENT;
    for (k = 0u; k < needed; ++k) {
        status = rf_fir_push(state, 0, 0, &tail[k]);
        if (status != RF_FIR_OK) return status;
    }
    state->closed = 1u;
    *written = needed;
    return RF_FIR_OK;
}
