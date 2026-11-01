#!/bin/sh
# Offline verification of the old-board recovery bundle, on a Linux host.
#
# Purpose: separate "the bundle is bad" from "the documented command is bad".
# The START-HERE recovery command passed the sha256 of the deprecated CRLF
# bundle while naming the CR-free one, and the archived tar stores
# arm/arm-tx-source with mode 0666, so `./arm/arm-tx-source` fails after
# extraction unless it is chmod'ed. This script proves both, without a board.
#
# Run from the project root:  sh experiments/p16_verify_recovery_bundle.sh

set -u

BUNDLE="results/p13-upload-bundle-20261017T025802Z/board-session-bundle.tar"
EXPECTED_SHA="9af83ce980e9aa78214b6d50b170229564cf4e14940b1919d04a311c04afde9e"
OUT="results/p13-bundle-offline-verify-20261017"

echo "=== bundle identity ==="
actual_sha=$(sha256sum "$BUNDLE" | cut -d' ' -f1)
echo "  expected: $EXPECTED_SHA"
echo "  actual  : $actual_sha"
if [ "$actual_sha" = "$EXPECTED_SHA" ]; then
    echo "  RESULT: bundle matches the CR-free hash"
else
    echo "  RESULT: MISMATCH"
    exit 1
fi

echo
echo "=== member permissions in the archive ==="
tar -tvf "$BUNDLE" | grep -E 'arm-tx-source|SHA256SUMS'

echo
echo "=== extract and verify payload ==="
rm -rf "$OUT"
mkdir -p "$OUT"
tar -xf "$BUNDLE" -C "$OUT"
cd "$OUT/stage" || exit 1

sha256sum -c SHA256SUMS
payload_rc=$?
echo "  sha256sum -c exit: $payload_rc"

echo
echo "=== execute-bit check (this is the documented defect) ==="
ls -l arm/arm-tx-source
if [ -x arm/arm-tx-source ]; then
    echo "  RESULT: already executable"
else
    echo "  RESULT: NOT executable -> the recovery command must chmod +x first"
    echo "  applying chmod +x to demonstrate the fix"
    chmod +x arm/arm-tx-source
    ls -l arm/arm-tx-source
fi

echo
echo "=== run --inspect WITHOUT any radio, to prove the binary works ==="
./arm/arm-tx-source --inspect 2>&1 | head -20
inspect_rc=$?
echo "  inspect exit (of the pipeline): $inspect_rc"

echo
echo "NOTE: --inspect still talks to /dev/iio on the board, so a failure here"
echo "on a Linux host is expected and does NOT indicate a bad bundle."
echo "The board-side non-transmitting verification must run on the board itself."

echo
echo "=== payload summary ==="
echo "  payload_sha256_check_rc=$payload_rc"
wc -c arm/arm-tx-source SHA256SUMS
ls -1 waveforms/ | wc -l
echo "  (expect 6 waveform files)"
