# Portable C99 integer FIR reference

`arm_smoke.c` is a small standalone deployment check: a two-tap half/half filter must return I=1,1 and Q=-1,-1 for the impulse I=2,Q=-2, including the final tail, exact accumulators, and no saturation. The Windows host check passed on 2026-10-11; its ARM build/run status is tracked separately in [ARM preparation](../../docs/experiments/exp-p06-arm-cross-20261011.md). The literal `ARM_FIR_SMOKE_PASS` output is not evidence of ARM execution when printed by a Windows build. No IIO or RF interface is used.

This module matches `src/rfsig/fixed_fir.py` and the standalone FIR RTL arithmetic: signed 12-bit I/Q input, 1–63 signed 18-bit Q17 taps, exact signed 36-bit accumulator, nearest ties-to-even division by 131072, then signed 16-bit saturation with independent I/Q flags. Coefficient 0 multiplies the current sample. There is no decimation or amplitude normalization.

`rf_fir_init` validates and copies taps into caller-owned fixed storage. Call `rf_fir_push` once per accepted I/Q pair. `rf_fir_finish` emits the M−1 zero-input tail and closes the stream; an empty stream emits no tail. `rf_fir_reset` preserves taps and clears history/closure before a new record. Provide a tail buffer of up to 62 `rf_fir_output` objects. Initialize every state before using it; do not modify its internal members or overlap output buffers with state storage.

The per-sample filter uses no heap or global state. Each product explicitly widens to `int64_t`. Every legal 63-tap sum has magnitude at most 16,911,433,728, within signed 36 bits. Conversion checks the accumulator range before negating, uses unsigned magnitude division/remainder, and performs no signed shifts or out-of-range casts. Invalid inputs do not advance sample state.

`fir_hex_cli.c` is a host fixture runner, separate from the reusable module. It requires nonempty, equally sized I/Q files and 1–63 coefficients; each hexadecimal line must fit its bit width. It rejects malformed words, signs, `0x` prefixes, comments, extra tokens, embedded NUL and excessively long lines. It prints decimal `I,Q,sat_I,sat_Q,acc_I,acc_Q` rows including the full tail. `--reset-replay` repeats the entire record after an explicit reset; `--quantize DECIMAL` exercises direct accumulator boundaries.

Run the experiment with the existing project Python environment:

```text
python experiments/p07_fir_c_check.py results/p07-fixed-fir-20261010T080230137429Z
```

It verifies all 126 saved vector files before compiling with the explicit host `C:\msys64\ucrt64\bin\gcc.exe` path and an isolated subprocess environment. Each of the 18 cases checks both components, saturation flags, exact accumulators and reset replay against the saved hex vectors/current Python reference. The new result directory records source/executable/tool/vector hashes, compiler version/target, compilation diagnostics and all C output rows.

This is host Windows execution. It does not demonstrate ARM compilation, ARM speed, board execution, IIO integration or FPGA synthesis/timing. The portable module may be reused later with a matching ARM C99 compiler; board deployment remains a separate step.

Update 2026-10-11: Hello, smoke, and all 18 CLI cases were actually executed on the P201 ARMv7 Linux board through COM5. The 144,712 outputs (including reset replay) were retrieved and independently matched byte-for-byte against the validated golden bundle; see the ARM experiment record and results/p06-arm-board-readback-20261011-131559/output-verification.json. This verifies offline ARM arithmetic and runtime compatibility, not live IIO integration, throughput, FPGA deployment, or AI inference.
