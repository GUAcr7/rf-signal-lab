"""Read one short, unsaved I/Q frame from the existing AD9361 RX settings."""

import argparse
from pathlib import Path

import numpy as np

from rfsig.iio_runtime import use_libiio


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--libiio-dir", required=True, type=Path)
    parser.add_argument("--uri", default="ip:192.168.2.1")
    args = parser.parse_args()

    with use_libiio(args.libiio_dir):
        import adi

        sdr = adi.ad9361(uri=args.uri)
        sdr.rx_enabled_channels = [0]
        sdr.rx_buffer_size = 1024

        sample_rate = int(sdr.sample_rate)
        rx_lo = int(sdr.rx_lo)
        bandwidth = int(sdr.rx_rf_bandwidth)
        gain_mode = sdr.gain_control_mode_chan0

        try:
            iq = np.asarray(sdr.rx()).copy()
        finally:
            sdr.rx_destroy_buffer()

        print("样本形状：", iq.shape)
        print("数据类型：", iq.dtype)
        print("是否为复数：", np.iscomplexobj(iq))
        print("采样率 Hz：", sample_rate)
        print("接收中心频率 Hz：", rx_lo)
        print("接收带宽 Hz：", bandwidth)
        print("增益模式：", gain_mode)
        print("前 5 个样本：", iq[:5])
        print("样本是否变化：", bool(np.any(iq != iq[0])))

        if iq.shape != (1024,) or not np.iscomplexobj(iq):
            raise RuntimeError("采样长度或 I/Q 格式不符合预期")


if __name__ == "__main__":
    main()
