# P36 finite full-IQ recorder

This is a new program; the P27 sparse recorder remains unchanged. Offline build:

```powershell
.venv\Scripts\python.exe experiments\p36_build_rx_full.py
```

The build runs the actual C program against a host-only mock IIO library, then creates an ARMv7 Cortex-A9 hard-float ELF with the existing GCC 8.3 toolchain. It uses the pinned libiio v0.24 header only for the already reviewed shared 0.x ABI and refuses runtime libraries other than 0.20. Build success does not prove execution on the board.

After the main task has independently confirmed the receiver boot, running PL/overlay identity, compatible libiio and idle DMA state, upload and verify the binary hash. The program requires the already approved RX configuration: 30.72 MS/s, 18 MHz BW, manual/0 dB, A_BALANCED, LO 2450 MHz, BIST/loopback off. It performs no RF attribute writes and contains no TX API. It changes the receive scan selection to RX1 I/Q and restores the library scan cache to disabled on normal exit; actual kernel state must still be read independently.

```text
arm-rx-full-p36 NEW_DIRECTORY [BLOCKS]
```

The program itself creates `NEW_DIRECTORY` and rejects an existing path. Do not create that directory in the host wrapper. Default is 16 blocks; allowed range is 1–64 for bounded smoke/expansion. Each block contains 65536 frames × 4 bytes. Default capture stores 4 MiB; the maximum stores 16 MiB. All memory is allocated and touched before receive. Saving to tmpfs temporarily requires another data-sized allocation in addition to DMA/kernel/video memory.

The full packed source bytes are copied before the next refill. `iq-packed.bin` is little-endian interleaved I,Q, each a signed 12-bit value in a 16-bit storage word, shift 0. The high four bits are undefined and intentionally preserved for raw integrity. Offline signal decoding must mask to `word & 0x0fff`, then subtract 4096 if the value is at least 2048. Do not interpret the raw words as already sign-extended int16.

The hot loop performs no filesystem writes, FFT or screen drawing. A worker refills/copies; the main thread observes SIGINT/SIGTERM and a 15-second acquisition deadline at approximately 100 ms intervals. Only the normal main thread calls `iio_buffer_cancel`. It joins with a 3.5-second limit before destroying the buffer/context and before writing any capture files. Join failure exits 3 with `cleanup_unconfirmed=true`; the host must stop the workflow and independently inspect the receiver. Do not reconfigure PL/overlay to clean up a live or uncertain worker.

Normal/failure artifacts, written only after release:

- `iq-packed.bin`: exactly the completed blocks, never zero-filled to the requested length.
- `metadata.json`: requested/completed blocks, every attempted refill's length, software timestamps and copy flag, layout/storage contract, RF readback status, cancellation and cleanup status.
- `before.txt` / `after.txt`: actual RF observations and per-field read status whenever that readback was attempted, including values that fail the fixed contract. Layout/RF declarations in metadata are expectations until `scan_layout_validated` / `rf_before_valid` establish their validation.

Exit 0 means finite capture, byte save and readback contract passed. Exit 1 means a failed or interrupted capture; partial bytes may still be complete for `completed_blocks`, but `requested_capture_complete=false`. Exit 2 rejects arguments/output directory before acquisition. Exit 3 means cleanup is unconfirmed and there are no reliable saved capture artifacts. Any host-side forced termination also requires independent cleanup inspection.

After success, verify the raw byte count equals `completed_blocks*262144`, compute board and host SHA256 and archive all files. Bind the report to boot_id, PL/DTBO and binary/source hashes in the host experiment record. Per-block index and CLOCK_MONOTONIC times are software observations, not ADC timestamps. `complete_returned_buffers_saved=true` does not imply every ADC sample was returned. `complete_stream_saved=false`, `lossless_proven=false` and `hardware_gaps=unknown` remain explicit. Known-source and independent continuity verification follow [the P36 contract](../../docs/experiments/p36-full-iq-contract.md).
