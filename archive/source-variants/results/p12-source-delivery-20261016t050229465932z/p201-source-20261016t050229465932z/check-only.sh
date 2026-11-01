#!/bin/sh
set -eu
cd "$(dirname "$0")"
sha256sum -c SHA256SUMS
./bin/arm-tx-source --sha256-selftest
./bin/arm-tx-source --check waveforms/existing30m72/tone-positive.iq16le 131072 36cd4ed7007721dd023b7b2c8b581a5ddb6f0365d9c0c0a40fef7c87522a0727
./bin/arm-tx-source --check waveforms/existing30m72/tone-negative.iq16le 131072 9bf8bb37bb59d05955cef616a19e9d5595e29e1b9b39cb9a47ee3d256a92e57d
./bin/arm-tx-source --check waveforms/existing30m72/bpsk.iq16le 131072 ceebe58f146a1cde27bc91b429e3ca26c6ecec5b1917d528d01ce75a2d652789
./bin/arm-tx-source --check waveforms/existing30m72/qpsk.iq16le 131072 fd56491f068881c5c315fc4fba41bfd165b0e3e25419d66755e66c372081cee9
./bin/arm-tx-source --check waveforms/existing30m72/qam16.iq16le 131072 85f8df7f3f5e986678df225da3f3421ecc453891284b12ca9ad67895be26efc2
./bin/arm-tx-source --check waveforms/planned4m250k/tone-positive.iq16le 32768 ee259fdc4a153a1889ee8ea141d27c7b017fc345f300520fc5e6875d9f3ee135
./bin/arm-tx-source --check waveforms/planned4m250k/tone-negative.iq16le 32768 fb4b7c243511571f95c782961a095cc05afa46b1012ca0c7d0e9028a487f1555
./bin/arm-tx-source --check waveforms/planned4m250k/bpsk.iq16le 32768 613302ee2664ab58bc75ad0e96a1214b4e97c783f73a3dbe29735ac49a729f10
./bin/arm-tx-source --check waveforms/planned4m250k/qpsk.iq16le 32768 281fe2260e759235000ce015673bd18c43c3edc4ec619bd95fa9693b9e3dcfd5
./bin/arm-tx-source --check waveforms/planned4m250k/qam16.iq16le 32768 cb99d5f7075a1ed7c51832e419e606bab7f09d2d740ecff392b84e2024a7d731
./bin/arm-tx-source --check waveforms/planned4m125k/tone-positive.iq16le 32768 ee259fdc4a153a1889ee8ea141d27c7b017fc345f300520fc5e6875d9f3ee135
./bin/arm-tx-source --check waveforms/planned4m125k/tone-negative.iq16le 32768 fb4b7c243511571f95c782961a095cc05afa46b1012ca0c7d0e9028a487f1555
./bin/arm-tx-source --check waveforms/planned4m125k/bpsk.iq16le 32768 29faed368a7f6553db6748a92d5cc259e724a28a2845aff762f623b70320a7f9
./bin/arm-tx-source --check waveforms/planned4m125k/qpsk.iq16le 32768 526b7c04b23b370c512faedbe4ca6146368cba2befdda5f52ea431b89406250a
./bin/arm-tx-source --check waveforms/planned4m125k/qam16.iq16le 32768 8a8491cf5db63e845d65c89c933acf1332dd354c7ea85babd5ca3c09456e2112
echo CHECK_ONLY_FINISHED_NO_IIO_NO_RF
