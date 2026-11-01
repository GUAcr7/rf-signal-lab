#!/bin/sh
set -eu
cd "$(dirname "$0")"
test ! -e outputs
sha256sum -c SHA256SUMS
mkdir outputs
uname -a > outputs/uname.txt
./bin/arm-rx-probe outputs > outputs/run.txt
cat outputs/run.txt
