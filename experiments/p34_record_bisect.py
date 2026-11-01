"""Record the bisection result: the bitstream is fine, the overlay is the problem."""

import io
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
STATUS = ROOT / "TX-SOURCE-STATUS.json"

BISECT = {
    "date": "2026-10-20",
    "record": "docs/experiments/P34-bisect-bitstream-vs-overlay.md",
    "result": "the merged bitstream is GOOD; the board hang is caused by our device tree overlay",
    "evidence": {
        "bitstream_plus_vendor_dt": (
            "boots: fpga_manager state=operating, xilinx-vdma probed, drm fb0 800x480, backlight present"
        ),
        "bitstream_plus_our_dt": 'hard hang right after "staged bitstream already current"',
    },
    "format_trap_fixed": (
        "the first board test was invalid: a .bit with its 124-byte ASCII header was fed to PCAP. "
        "Regenerated with -bin_file; derived on board with tail -c +125 and verified by sha256 "
        "34eeb736... so no 5 MB re-upload was needed"
    ),
    "ruled_out": [
        "bitstream format (fixed, still hangs)",
        "AXI address mismatch (the BD address map matches the DTS)",
        "fpga_full fragment structure (equivalent to the vendor overlay)",
        "the PL design itself (boots and runs with the vendor device tree)",
    ],
    "remaining_suspect": (
        "the RF-side nodes: ad9361-phy on spi1, dma@7c400000/7c420000, cf-ad9361-lpc@79020000. "
        "They depend on PS SPI/GPIO setup, and the RF and display projects had different PS init "
        "(UART1 MIO 48-49 vs 12-13, EMIO width 64 vs 1, FCLK2 50 vs 250 MHz)"
    ),
    "next_experiment": (
        "rf mode with our bitstream and the vendor RF overlay: back up ad9361.bin, "
        "cp p32.raw ad9361.bin, board-mode rf, reboot"
    ),
    "board_state_now": {
        "pl": "our merged bitstream",
        "device_tree": "vendor display overlay",
        "consequence": "display works, no AD9361",
        "restore": "cp display.bin.vb display.bin; cp system_wrapper.bin.vb system_wrapper.bin; reboot",
    },
}


def main() -> int:
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except Exception:                                          # noqa: BLE001
        pass

    data = json.loads(STATUS.read_text(encoding="utf-8-sig"))
    data["p34_bisect"] = BISECT
    STATUS.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print("status: p34_bisect recorded")
    print(f"  result: {BISECT['result']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
