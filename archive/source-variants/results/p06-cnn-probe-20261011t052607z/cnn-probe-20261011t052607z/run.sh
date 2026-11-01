#!/bin/sh
set -eu
cd "$(dirname "$0")"
test ! -e outputs
sha256sum -c SHA256SUMS
mkdir outputs
uname -a > outputs/uname.txt
./bin/tiny-cnn-probe inputs/accumulator_extreme.iq > outputs/accumulator_extreme.txt
./bin/tiny-cnn-probe inputs/asymmetric_hand.iq > outputs/asymmetric_hand.txt
./bin/tiny-cnn-probe inputs/bpsk.iq > outputs/bpsk.txt
./bin/tiny-cnn-probe inputs/dc.iq > outputs/dc.txt
./bin/tiny-cnn-probe inputs/near_fullscale.iq > outputs/near_fullscale.txt
./bin/tiny-cnn-probe inputs/negative_impulse.iq > outputs/negative_impulse.txt
./bin/tiny-cnn-probe inputs/positive_impulse.iq > outputs/positive_impulse.txt
./bin/tiny-cnn-probe inputs/qam16.iq > outputs/qam16.txt
./bin/tiny-cnn-probe inputs/qpsk.iq > outputs/qpsk.txt
./bin/tiny-cnn-probe inputs/random_12bit.iq > outputs/random_12bit.txt
./bin/tiny-cnn-probe inputs/saturation_both_signs.iq > outputs/saturation_both_signs.txt
./bin/tiny-cnn-probe inputs/ties_even.iq > outputs/ties_even.txt
./bin/tiny-cnn-probe inputs/tone_n300000.iq > outputs/tone_n300000.txt
./bin/tiny-cnn-probe inputs/tone_n50000.iq > outputs/tone_n50000.txt
./bin/tiny-cnn-probe inputs/tone_p300000.iq > outputs/tone_p300000.txt
./bin/tiny-cnn-probe inputs/tone_p50000.iq > outputs/tone_p50000.txt
./bin/tiny-cnn-probe inputs/two_tones.iq > outputs/two_tones.txt
./bin/tiny-cnn-probe inputs/zero.iq > outputs/zero.txt
./bin/tiny-cnn-probe inputs/qpsk_shaped.iq --bench > outputs/benchmark.txt
echo CNN_OPERATOR_RUN_DONE_UNTRAINED
