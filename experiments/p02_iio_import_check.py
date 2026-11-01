"""Check the selected native libiio DLL and read-only IIO device discovery."""

import argparse
from pathlib import Path

from rfsig.iio_runtime import use_libiio


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    args = parser.parse_args()

    with use_libiio(args.libiio_dir) as dll:
        import adi  # noqa: F401 - importing verifies the higher-level binding
        import iio

        context = iio.Context(args.uri)
        devices = [device.name for device in context.devices]
        model = context.attrs.get("hw_model", "unknown")

        print(f"Native DLL: {dll}")
        print(f"libiio version: {iio.version}")
        print(f"Board model: {model}")
        print(f"IIO devices: {devices}")

        required = {"ad9361-phy", "cf-ad9361-lpc"}
        if not required.issubset(devices):
            raise RuntimeError(f"Receiver devices missing: {required - set(devices)}")


if __name__ == "__main__":
    main()
