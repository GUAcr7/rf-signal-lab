"""Render the lab's own control panel into a framebuffer image.

The board ships no application of its own: in display mode it shows the vendor
XFCE desktop and nothing else, so task 1 of the competition ("show spectrum and
constellation on the screen") is still a blank page. This module draws that page.

Deliberate scope: rendering happens on the host and the result is shipped as raw
framebuffer bytes, because the board has no Python and no plotting stack. That
keeps the board side to a single `dd`/`gunzip` redirect and makes the layout
testable and reviewable offline.

The pixel layout follows Xilinx DRM with XRGB8888: one 32-bit word per pixel in
little-endian memory order B, G, R, X. That is the usual xilinx-drm format but it
must be confirmed on the actual panel with a test pattern before any layout is
declared correct - see `framebuffer_bytes()`.
"""

from dataclasses import dataclass

import numpy as np
from numpy.typing import ArrayLike
from PIL import Image, ImageDraw, ImageFont

PANEL_WIDTH = 800
PANEL_HEIGHT = 480
BYTES_PER_PIXEL = 4

BACKGROUND = (12, 14, 18)
FOREGROUND = (222, 230, 238)
DIM = (150, 165, 182)      # brighter: the first panel read dim on the real LCD
ACCENT = (80, 200, 255)
GRID = (38, 44, 54)
TRACE = (120, 230, 150)
POINT = (255, 190, 80)

# Layout rectangles: (left, top, right, bottom), right/bottom exclusive.
HEADER_RECT = (16, 10, PANEL_WIDTH - 16, 44)
SPECTRUM_RECT = (56, 62, PANEL_WIDTH - 20, 274)
CONSTELLATION_RECT = (20, 288, 236, 466)
METRICS_RECT = (252, 288, PANEL_WIDTH - 20, 466)


@dataclass(frozen=True)
class PanelContent:
    """Everything the panel needs to draw itself."""

    frequency_hz: ArrayLike
    psd_db: ArrayLike
    symbols: ArrayLike
    title: str = "RF SIGNAL LAB"
    subtitle: str = ""
    metrics: tuple[tuple[str, str], ...] = ()


def _font(size: int):
    try:
        return ImageFont.load_default(size=size)
    except TypeError:                                          # older Pillow
        return ImageFont.load_default()


def _plot_area(rect):
    left, top, right, bottom = rect
    return left, top, max(right - 1, left + 1), max(bottom - 1, top + 1)


def render_panel(content: PanelContent,
                 width: int = PANEL_WIDTH,
                 height: int = PANEL_HEIGHT,
                 db_span: float = 70.0) -> Image.Image:
    """Draw the header, spectrum, constellation and metric block.

    ``db_span`` is the dynamic range shown below the peak, in dB. Everything is
    clipped to it rather than auto-scaled per frame so that the vertical scale
    means the same thing from one frame to the next.
    """
    frequency = np.asarray(content.frequency_hz, dtype=float).ravel()
    psd = np.asarray(content.psd_db, dtype=float).ravel()
    if frequency.size != psd.size:
        raise ValueError("frequency_hz and psd_db must have the same length")
    if frequency.size < 2:
        raise ValueError("need at least two spectrum points")
    if not np.all(np.isfinite(psd)):
        raise ValueError("psd_db must be finite")
    if db_span <= 0:
        raise ValueError("db_span must be positive")

    symbols = np.asarray(content.symbols, dtype=np.complex128).ravel()
    if symbols.size == 0:
        raise ValueError("symbols must not be empty")
    if not np.all(np.isfinite(symbols)):
        raise ValueError("symbols must be finite")

    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)

    # --- header ---------------------------------------------------------
    left, top, right, bottom = HEADER_RECT
    draw.text((left, top), content.title, font=_font(20), fill=ACCENT)
    if content.subtitle:
        draw.text((left, bottom - 14), content.subtitle, font=_font(12), fill=DIM)
    draw.line((left, bottom + 2, right, bottom + 2), fill=GRID, width=1)

    # --- spectrum -------------------------------------------------------
    sx0, sy0, sx1, sy1 = _plot_area(SPECTRUM_RECT)
    for fraction in np.linspace(0.0, 1.0, 6):
        y = int(round(sy1 - fraction * (sy1 - sy0)))
        draw.line((sx0, y, sx1, y), fill=GRID, width=1)
        label = f"{fraction * db_span:3.0f}"
        draw.text((sx0 - 46, y - 7), label, font=_font(13), fill=DIM)
    draw.rectangle((sx0, sy0, sx1, sy1), outline=GRID)

    peak = float(np.max(psd))
    normalised = np.clip((psd - (peak - db_span)) / db_span, 0.0, 1.0)
    span_hz = float(frequency[-1] - frequency[0])
    if span_hz == 0:
        raise ValueError("frequency axis has no span")
    xs = sx0 + (frequency - frequency[0]) / span_hz * (sx1 - sx0)
    ys = sy1 - normalised * (sy1 - sy0)
    points = [(float(x), float(y)) for x, y in zip(xs, ys)]
    if len(points) > 1:
        draw.line(points, fill=TRACE, width=1)

    peak_index = int(np.argmax(psd))
    draw.line((xs[peak_index], sy0, xs[peak_index], sy1), fill=ACCENT, width=1)
    draw.text((sx1 - 96, sy0 + 4), f"pk {peak:6.1f} dB", font=_font(11), fill=DIM)
    draw.text((sx0 + 4, sy1 - 16),
              f"{frequency[0] / 1e6:+.3f} ... {frequency[-1] / 1e6:+.3f} MHz rel. carrier",
              font=_font(11), fill=DIM)

    # --- constellation --------------------------------------------------
    cx0, cy0, cx1, cy1 = _plot_area(CONSTELLATION_RECT)
    draw.rectangle((cx0, cy0, cx1, cy1), outline=GRID)
    mid_x = (cx0 + cx1) / 2.0
    mid_y = (cy0 + cy1) / 2.0
    draw.line((cx0, mid_y, cx1, mid_y), fill=GRID, width=1)
    draw.line((mid_x, cy0, mid_x, cy1), fill=GRID, width=1)

    rms = float(np.sqrt(np.mean(np.abs(symbols) ** 2)))
    scale = rms if rms > 0 else 1.0
    limit = 1.15 * float(np.max(np.abs(symbols) / scale)) or 1.0
    # The constellation box is much wider than it is tall (310 x 146). Using the
    # short dimension for both axes squeezed the points into the middle third of
    # the box on the real panel; each axis gets its own half-extent instead.
    half_x = (cx1 - cx0) / 2.0
    half_y = (cy1 - cy0) / 2.0
    for value in symbols:
        x = float(mid_x + (value.real / scale) / limit * half_x)
        y = float(mid_y - (value.imag / scale) / limit * half_y)
        # A 1-pixel point is invisible on a real panel at arm's length, and PSK
        # clusters overlap into a single dot. A 3x3 cross reads as a cluster.
        draw.line((x - 1, y, x + 1, y), fill=POINT)
        draw.line((x, y - 1, x, y + 1), fill=POINT)
    draw.text((cx0 + 4, cy0 + 2), "constellation", font=_font(11), fill=DIM)

    # --- metrics --------------------------------------------------------
    mx0, my0, mx1, my1 = METRICS_RECT
    draw.rectangle((mx0, my0, mx1, my1), outline=GRID)
    y = my0 + 6
    for name, value in content.metrics:
        if y > my1 - 14:
            break
        draw.text((mx0 + 8, y), f"{name}", font=_font(12), fill=DIM)
        draw.text((mx0 + 150, y), f"{value}", font=_font(12), fill=FOREGROUND)
        y += 17

    return image


def framebuffer_bytes(image: Image.Image, pixel_format: str = "bgra32") -> bytes:
    """Serialise an image into the raw byte layout of /dev/fb0.

    ``bgra32`` is what little-endian Xilinx DRM expects for XRGB8888. Confirm it
    on the panel with a test pattern before trusting a layout: a wrong channel
    order still produces a picture, just with red and blue exchanged.
    """
    if pixel_format != "bgra32":
        raise ValueError(f"unsupported pixel format {pixel_format!r}")
    rgb = np.asarray(image.convert("RGB"), dtype=np.uint8)
    height, width, _ = rgb.shape
    out = np.empty((height, width, 4), dtype=np.uint8)
    out[..., 0] = rgb[..., 2]      # B
    out[..., 1] = rgb[..., 1]      # G
    out[..., 2] = rgb[..., 0]      # R
    out[..., 3] = 0xFF             # X / padding
    return out.tobytes()


def save_png(image: Image.Image, path) -> None:
    image.save(path, format="PNG")


def test_pattern(width: int = PANEL_WIDTH, height: int = PANEL_HEIGHT) -> Image.Image:
    """Channel and geometry check: three labelled bars plus a border.

    Used to confirm the panel's channel order and stride on real hardware without
    needing any signal data.
    """
    image = Image.new("RGB", (width, height), BACKGROUND)
    draw = ImageDraw.Draw(image)
    draw.rectangle((0, 0, width - 1, height - 1), outline=(255, 255, 255))
    bars = ((0, width // 3, (255, 0, 0), "RED"),
            (width // 3, 2 * width // 3, (0, 255, 0), "GREEN"),
            (2 * width // 3, width, (0, 128, 255), "BLUE"))
    for left, right, colour, label in bars:
        draw.rectangle((left + 4, 80, right - 4, height - 140), fill=colour)
        draw.text((left + 16, 40), label, font=_font(22), fill=(255, 255, 255))
    draw.text((16, height - 40), f"{width}x{height} bgra32 test pattern",
              font=_font(14), fill=(255, 255, 255))
    return image
