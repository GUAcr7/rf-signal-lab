#!/bin/sh
set -eu
cd "$(dirname "$0")"
sha256sum -c SHA256SUMS
./bin/arm-tx-source --inspect
