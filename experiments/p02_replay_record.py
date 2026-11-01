"""Replay a previously saved P02 I/Q record without connecting to the board."""

import argparse
from pathlib import Path

import numpy as np

from rfsig.iq_recording import load_iq_record


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("directory", type=Path)
    args = parser.parse_args()

    iq, metadata = load_iq_record(args.directory)
    before = metadata["settings_before"]
    print("记录目录：", args.directory.resolve())
    print("来源板卡：", metadata["board_model"])
    print("固件版本：", metadata["board_firmware_version"])
    print("采集开始 UTC：", metadata["capture_start_utc"])
    print("样本：", len(iq), iq.dtype)
    print("采样率 Hz：", before["sample_rate_hz"])
    print("接收中心频率 Hz：", before["rx_lo_hz"])
    print("前 5 个样本：", iq[:5])
    print("样本有变化：", bool(np.any(iq != iq[0])))
    print("离线回放：SHA256、样本数和类型校验通过")


if __name__ == "__main__":
    main()
