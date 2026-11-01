"""Inspect extracted figures and build an annotated connector map.

Picks the board photo from the evaluation-board spec, then overlays a numbered
callout sequence on the connectors the operator must touch, in the order they
must touch them.

CJK text needs a font that actually contains the glyphs: Windows' bundled Segoe
UI does not, so Microsoft YaHei is used and its absence is a hard error rather
than a silent fallback to boxes.
"""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

HERE = Path(__file__).resolve().parents[1]
FIGS = HERE / "tmp" / "new-board-xilinx-review" / "figures"
OUT = HERE / "tmp" / "new-board-xilinx-review" / "annotated"

CJK_CANDIDATES = [
    r"C:\Windows\Fonts\msyhbd.ttc",
    r"C:\Windows\Fonts\msyh.ttc",
    r"C:\Windows\Fonts\simhei.ttf",
    r"C:\Windows\Fonts\simsun.ttc",
]


def list_sizes():
    rows = []
    for f in sorted(FIGS.iterdir()):
        if f.suffix.lower() not in {".jpg", ".jpeg", ".png", ".jp2"}:
            continue
        try:
            im = Image.open(f)
            rows.append((im.width * im.height, im.width, im.height, f.name))
        except Exception as exc:                                   # noqa: BLE001
            rows.append((0, 0, 0, f"{f.name} (unreadable: {exc})"))
    rows.sort(reverse=True)
    print(f"{'WxH':>13}  {'pixels':>11}  file")
    for area, w, h, name in rows[:14]:
        print(f"{w:5d}x{h:<7d} {area:11,d}  {name}")
    return rows


def cjk_font(size):
    for candidate in CJK_CANDIDATES:
        path = Path(candidate)
        if path.is_file():
            try:
                return ImageFont.truetype(str(path), size)
            except OSError:
                continue
    raise RuntimeError("no CJK-capable font found; refusing to render boxes")


def annotate(source: Path, marks, out_name: str, scale: int = 2, top_margin: int = 120):
    """marks: list of (x_frac, y_frac, number, text, dx_px, dy_px)."""
    photo = Image.open(source).convert("RGB")
    photo = photo.resize((photo.width * scale, photo.height * scale), Image.LANCZOS)

    # Reserve headroom so labels pointing above the board are not clipped.
    canvas = Image.new("RGB", (photo.width, photo.height + top_margin), (255, 255, 255))
    canvas.paste(photo, (0, top_margin))
    draw = ImageDraw.Draw(canvas)
    w, h = canvas.size

    num_font = cjk_font(38)
    txt_font = cjk_font(30)

    def place(x_frac, y_frac):
        return x_frac * photo.width, y_frac * photo.height + top_margin

    # Connector markers first, so leader lines draw over them.
    for x_frac, y_frac, number, _text, _dx, _dy in marks:
        x, y = place(x_frac, y_frac)
        r = 30
        draw.ellipse([x - r, y - r, x + r, y + r],
                     fill=(255, 235, 0), outline=(190, 0, 0), width=6)
        tw = draw.textlength(number, font=num_font)
        draw.text((x - tw / 2, y - 26), number, fill=(150, 0, 0), font=num_font)

    # Leader lines and labels.
    for x_frac, y_frac, number, text, dx, dy in marks:
        x, y = place(x_frac, y_frac)
        tx, ty = x + dx, y + dy
        draw.line([x, y, tx, ty], fill=(190, 0, 0), width=5)
        label = f"{number}  {text}"
        tw = draw.textlength(label, font=txt_font)
        pad = 10
        box = [tx - pad, ty - 46, tx + tw + pad, ty + 12]
        # Keep the label box inside the canvas.
        shift_x = 0
        if box[0] < 4:
            shift_x = 4 - box[0]
        if box[2] > w - 4:
            shift_x = (w - 4) - box[2]
        shift_y = 0
        if box[1] < 4:
            shift_y = 4 - box[1]
        box = [box[0] + shift_x, box[1] + shift_y, box[2] + shift_x, box[3] + shift_y]
        draw.rectangle(box, fill=(255, 255, 255), outline=(190, 0, 0), width=4)
        draw.text((box[0] + pad, box[1] + 8), label, fill=(0, 0, 0), font=txt_font)

    target = OUT / out_name
    canvas.save(target, quality=93)
    print(f"\nwrote {target}  ({canvas.width}x{canvas.height})")


if __name__ == "__main__":
    OUT.mkdir(parents=True, exist_ok=True)
    list_sizes()

    # Numbered in the order the operator must actually do them.
    STEPS = [
        (0.730, 0.862, "1", "Micro SD 卡槽", -430, 30),
        (0.852, 0.856, "2", "启动拨码 101001", 70, 70),
        (0.791, 0.094, "3", "调试串口 USB", -80, -120),
        (0.737, 0.515, "4", "RES LCD 排线", -430, -30),
        (0.951, 0.401, "5", "FMC 400pin", -330, 110),
        (0.951, 0.187, "6", "DC 12V 电源口", -380, -10),
        (0.911, 0.127, "7", "电源开关", -120, -160),
    ]
    annotate(FIGS / "evm-spec-p05-2.jpg", STEPS, "board-steps-annotated.jpg")
