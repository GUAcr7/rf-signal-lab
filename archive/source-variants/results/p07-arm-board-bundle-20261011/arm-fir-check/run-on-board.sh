#!/bin/sh
set -eu
cd "$(dirname "$0")"
[ "$(uname -m)" = armv7l ] || { echo "Expected ARMv7 Linux" >&2; exit 1; }
[ -e /lib/ld-linux-armhf.so.3 ] || { echo "ARM hardfloat loader missing" >&2; exit 1; }
command -v sha256sum >/dev/null
command -v cmp >/dev/null
sha256sum -c SHA256SUMS
[ ! -e outputs ] || { echo "Existing outputs retained; use a fresh bundle directory" >&2; exit 1; }
mkdir outputs
uname -a > outputs/uname.txt
./bin/hello > outputs/hello.txt
cat outputs/hello.txt
./bin/fir-smoke > outputs/fir-smoke.txt
cat outputs/fir-smoke.txt
./bin/fir-hex-cli vectors/zero/coefficients.hex vectors/zero/input_i.hex vectors/zero/input_q.hex --reset-replay > outputs/zero.csv
cmp outputs/zero.csv expected/zero.csv
echo "ARM_CASE_PASS zero"
./bin/fir-hex-cli vectors/positive_impulse/coefficients.hex vectors/positive_impulse/input_i.hex vectors/positive_impulse/input_q.hex --reset-replay > outputs/positive_impulse.csv
cmp outputs/positive_impulse.csv expected/positive_impulse.csv
echo "ARM_CASE_PASS positive_impulse"
./bin/fir-hex-cli vectors/negative_impulse/coefficients.hex vectors/negative_impulse/input_i.hex vectors/negative_impulse/input_q.hex --reset-replay > outputs/negative_impulse.csv
cmp outputs/negative_impulse.csv expected/negative_impulse.csv
echo "ARM_CASE_PASS negative_impulse"
./bin/fir-hex-cli vectors/dc/coefficients.hex vectors/dc/input_i.hex vectors/dc/input_q.hex --reset-replay > outputs/dc.csv
cmp outputs/dc.csv expected/dc.csv
echo "ARM_CASE_PASS dc"
./bin/fir-hex-cli vectors/near_fullscale/coefficients.hex vectors/near_fullscale/input_i.hex vectors/near_fullscale/input_q.hex --reset-replay > outputs/near_fullscale.csv
cmp outputs/near_fullscale.csv expected/near_fullscale.csv
echo "ARM_CASE_PASS near_fullscale"
./bin/fir-hex-cli vectors/random_12bit/coefficients.hex vectors/random_12bit/input_i.hex vectors/random_12bit/input_q.hex --reset-replay > outputs/random_12bit.csv
cmp outputs/random_12bit.csv expected/random_12bit.csv
echo "ARM_CASE_PASS random_12bit"
./bin/fir-hex-cli vectors/two_tones/coefficients.hex vectors/two_tones/input_i.hex vectors/two_tones/input_q.hex --reset-replay > outputs/two_tones.csv
cmp outputs/two_tones.csv expected/two_tones.csv
echo "ARM_CASE_PASS two_tones"
./bin/fir-hex-cli vectors/tone_p50000/coefficients.hex vectors/tone_p50000/input_i.hex vectors/tone_p50000/input_q.hex --reset-replay > outputs/tone_p50000.csv
cmp outputs/tone_p50000.csv expected/tone_p50000.csv
echo "ARM_CASE_PASS tone_p50000"
./bin/fir-hex-cli vectors/tone_n50000/coefficients.hex vectors/tone_n50000/input_i.hex vectors/tone_n50000/input_q.hex --reset-replay > outputs/tone_n50000.csv
cmp outputs/tone_n50000.csv expected/tone_n50000.csv
echo "ARM_CASE_PASS tone_n50000"
./bin/fir-hex-cli vectors/tone_p300000/coefficients.hex vectors/tone_p300000/input_i.hex vectors/tone_p300000/input_q.hex --reset-replay > outputs/tone_p300000.csv
cmp outputs/tone_p300000.csv expected/tone_p300000.csv
echo "ARM_CASE_PASS tone_p300000"
./bin/fir-hex-cli vectors/tone_n300000/coefficients.hex vectors/tone_n300000/input_i.hex vectors/tone_n300000/input_q.hex --reset-replay > outputs/tone_n300000.csv
cmp outputs/tone_n300000.csv expected/tone_n300000.csv
echo "ARM_CASE_PASS tone_n300000"
./bin/fir-hex-cli vectors/bpsk/coefficients.hex vectors/bpsk/input_i.hex vectors/bpsk/input_q.hex --reset-replay > outputs/bpsk.csv
cmp outputs/bpsk.csv expected/bpsk.csv
echo "ARM_CASE_PASS bpsk"
./bin/fir-hex-cli vectors/qpsk/coefficients.hex vectors/qpsk/input_i.hex vectors/qpsk/input_q.hex --reset-replay > outputs/qpsk.csv
cmp outputs/qpsk.csv expected/qpsk.csv
echo "ARM_CASE_PASS qpsk"
./bin/fir-hex-cli vectors/qam16/coefficients.hex vectors/qam16/input_i.hex vectors/qam16/input_q.hex --reset-replay > outputs/qam16.csv
cmp outputs/qam16.csv expected/qam16.csv
echo "ARM_CASE_PASS qam16"
./bin/fir-hex-cli vectors/asymmetric_hand/coefficients.hex vectors/asymmetric_hand/input_i.hex vectors/asymmetric_hand/input_q.hex --reset-replay > outputs/asymmetric_hand.csv
cmp outputs/asymmetric_hand.csv expected/asymmetric_hand.csv
echo "ARM_CASE_PASS asymmetric_hand"
./bin/fir-hex-cli vectors/ties_even/coefficients.hex vectors/ties_even/input_i.hex vectors/ties_even/input_q.hex --reset-replay > outputs/ties_even.csv
cmp outputs/ties_even.csv expected/ties_even.csv
echo "ARM_CASE_PASS ties_even"
./bin/fir-hex-cli vectors/saturation_both_signs/coefficients.hex vectors/saturation_both_signs/input_i.hex vectors/saturation_both_signs/input_q.hex --reset-replay > outputs/saturation_both_signs.csv
cmp outputs/saturation_both_signs.csv expected/saturation_both_signs.csv
echo "ARM_CASE_PASS saturation_both_signs"
./bin/fir-hex-cli vectors/accumulator_extreme/coefficients.hex vectors/accumulator_extreme/input_i.hex vectors/accumulator_extreme/input_q.hex --reset-replay > outputs/accumulator_extreme.csv
cmp outputs/accumulator_extreme.csv expected/accumulator_extreme.csv
echo "ARM_CASE_PASS accumulator_extreme"
echo "ARM_FIR_ALL_PASS cases=18 outputs=144712"
echo "No RF, IIO, FPGA, boot or persistent-storage operations were performed."
