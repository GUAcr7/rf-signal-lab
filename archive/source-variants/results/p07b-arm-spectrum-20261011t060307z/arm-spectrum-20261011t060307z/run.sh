#!/bin/sh
set -eu
cd "$(dirname "$0")"
test ! -e outputs
sha256sum -c SHA256SUMS
mkdir outputs
uname -a > outputs/uname.txt
./bin/arm-spectrum inputs/positive_tone.iq outputs/positive_tone 30720000
./bin/arm-spectrum inputs/negative_tone.iq outputs/negative_tone 30720000
./bin/arm-spectrum inputs/off_bin.iq outputs/off_bin 30720000
./bin/arm-spectrum inputs/dc.iq outputs/dc 30720000
./bin/arm-spectrum inputs/zero.iq outputs/zero 30720000
./bin/arm-spectrum inputs/random.iq outputs/random 30720000
./bin/arm-spectrum inputs/impulse.iq outputs/impulse 30720000
./bin/arm-rx-probe outputs > outputs/run.txt
cat outputs/run.txt
grep -qx "adc_sampling_frequency=30720000" outputs/session-1.before.txt
grep -qx "adc_sampling_frequency=30720000" outputs/session-1.after.txt
./bin/arm-spectrum outputs/session-1.iq outputs/rx-spectrum-1 30720000
grep -qx "adc_sampling_frequency=30720000" outputs/session-2.before.txt
grep -qx "adc_sampling_frequency=30720000" outputs/session-2.after.txt
./bin/arm-spectrum outputs/session-2.iq outputs/rx-spectrum-2 30720000
echo ARM_BOUNDED_RX_SOFTWARE_SPECTRUM_DONE
