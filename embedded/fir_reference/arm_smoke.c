#include "fixed_fir.h"
#include <stdio.h>

/* A board-run smoke test. Compilation alone does not execute these checks. */
int main(void)
{
    const int32_t coefficients[2] = {65536, 65536};
    rf_fir_state state;
    rf_fir_output first, tail[1];
    size_t written = 0u;
    if (rf_fir_init(&state, coefficients, 2u) != RF_FIR_OK ||
        rf_fir_push(&state, 2, -2, &first) != RF_FIR_OK ||
        rf_fir_finish(&state, tail, 1u, &written) != RF_FIR_OK ||
        written != 1u || first.i != 1 || first.q != -1 ||
        tail[0].i != 1 || tail[0].q != -1 ||
        first.accumulator_i != 131072 || first.accumulator_q != -131072 ||
        tail[0].accumulator_i != 131072 || tail[0].accumulator_q != -131072 ||
        first.saturated_i || first.saturated_q ||
        tail[0].saturated_i || tail[0].saturated_q)
    {
        fputs("ARM_FIR_SMOKE_FAIL\n", stderr);
        return 1;
    }
    puts("ARM_FIR_SMOKE_PASS outputs=2 I=1,1 Q=-1,-1");
    return 0;
}
