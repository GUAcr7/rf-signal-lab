"""Crop regions of the board photo so connector positions can be read exactly.

Coordinates are in pixels of the source photo (1356x748) and are chosen to
cover the areas the operator has to touch: power/jtag/usb, the FFC LCD header,
the micro-SD slot, and the red BOOT SET switch.
"""

from pathlib import Path

from PIL import Image

HERE = Path(__file__).resolve().parents[1]
SRC = HERE / "tmp" / "new-board-xilinx-review" / "figures" / "evm-spec-p05-2.jpg"
OUT = HERE / "tmp" / "new-board-xilinx-review" / "crops"

REGIONS = {
    "chip-zynq":      (600, 330, 800, 520),
    "power-dc-jack":  (1180, 30, 1356, 200),
    "jtag-usb":       (980, 30, 1200, 140),
    "lcd-ffc":        (900, 330, 1120, 440),
    "boot-dip":       (1080, 580, 1260, 700),
    "micro-sd":       (900, 580, 1080, 700),
    "fmc":            (1240, 150, 1356, 460),
}


def main():
    OUT.mkdir(parents=True, exist_ok=True)
    image = Image.open(SRC).convert("RGB")
    print(f"source {image.width}x{image.height}")
    for name, box in REGIONS.items():
        x0, y0, x1, y1 = box
        crop = image.crop(box)
        crop = crop.resize((crop.width * 4, crop.height * 4), Image.LANCZOS)
        target = OUT / f"{name}.png"
        crop.save(target)
        print(f"  {name:16s} box={box}  -> {crop.width}x{crop.height}")


if __name__ == "__main__":
    main()
