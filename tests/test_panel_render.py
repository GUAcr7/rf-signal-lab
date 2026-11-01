import numpy as np
import pytest
from PIL import Image

from rfsig.panel_render import (
    BYTES_PER_PIXEL,
    PANEL_HEIGHT,
    PANEL_WIDTH,
    PanelContent,
    framebuffer_bytes,
    render_panel,
    test_pattern as make_test_pattern,
)


def _content(points=256, symbols=256, seed=0):
    rng = np.random.default_rng(seed)
    frequency = np.linspace(-15.36e6, 15.36e6, points)
    psd = -60 + 40 * np.exp(-((frequency - 0.993e6) ** 2) / (2 * (0.2e6) ** 2))
    constellation = rng.choice([1, -1], symbols) + 0j
    return PanelContent(
        frequency_hz=frequency, psd_db=psd, symbols=constellation,
        subtitle="unit test", metrics=(("EVM", "-37.2 dB"), ("carrier", "993.2 kHz")),
    )


def test_panel_has_the_expected_size():
    image = render_panel(_content())
    assert image.size == (PANEL_WIDTH, PANEL_HEIGHT)
    assert image.mode == "RGB"


def test_framebuffer_bytes_length_matches_a_32bpp_panel():
    image = render_panel(_content())
    raw = framebuffer_bytes(image)
    assert len(raw) == PANEL_WIDTH * PANEL_HEIGHT * BYTES_PER_PIXEL


def test_framebuffer_alpha_byte_is_opaque_everywhere():
    image = render_panel(_content())
    raw = np.frombuffer(framebuffer_bytes(image), dtype=np.uint8).reshape(-1, 4)
    assert np.all(raw[:, 3] == 0xFF)


def test_bgra_order_matches_the_rgb_source():
    image = Image.new("RGB", (4, 1))
    image.putpixel((0, 0), (255, 0, 0))
    image.putpixel((1, 0), (0, 255, 0))
    image.putpixel((2, 0), (0, 0, 255))
    image.putpixel((3, 0), (1, 2, 3))
    raw = np.frombuffer(framebuffer_bytes(image), dtype=np.uint8).reshape(4, 4)
    # Memory order per pixel is B, G, R, X.
    assert raw[0].tolist() == [0, 0, 255, 0xFF]
    assert raw[1].tolist() == [0, 255, 0, 0xFF]
    assert raw[2].tolist() == [255, 0, 0, 0xFF]
    assert raw[3].tolist() == [3, 2, 1, 0xFF]


def test_rendering_is_deterministic():
    image = render_panel(_content(seed=7))
    again = render_panel(_content(seed=7))
    assert framebuffer_bytes(image) == framebuffer_bytes(again)


def test_a_flat_spectrum_still_draws_a_frame():
    # A constant PSD must not divide by zero or produce an all-background panel.
    content = PanelContent(
        frequency_hz=np.linspace(-1e6, 1e6, 64),
        psd_db=np.full(64, -50.0),
        symbols=np.ones(16, dtype=complex),
    )
    image = render_panel(content)
    colours = {colour for _, colour in image.getcolors(maxcolors=1 << 20)}
    assert len(colours) > 3


def test_spectrum_trace_changes_the_plot_region():
    flat = render_panel(PanelContent(
        frequency_hz=np.linspace(-1e6, 1e6, 128),
        psd_db=np.full(128, -80.0),
        symbols=np.ones(8, dtype=complex),
    ))
    shaped = render_panel(PanelContent(
        frequency_hz=np.linspace(-1e6, 1e6, 128),
        psd_db=-80.0 + 60.0 * np.exp(-np.linspace(-6, 6, 128) ** 2),
        symbols=np.ones(8, dtype=complex),
    ))
    box = (60, 66, 760, 296)
    assert flat.crop(box).tobytes() != shaped.crop(box).tobytes()


def test_constellation_marks_symbols():
    content = PanelContent(
        frequency_hz=np.linspace(-1e6, 1e6, 32),
        psd_db=np.full(32, -50.0),
        symbols=np.array([1 + 1j, -1 + 1j, -1 - 1j, 1 - 1j]) * 1000.0,
    )
    image = render_panel(content)
    region = image.crop((20, 320, 330, 466))
    colours = {colour for _, colour in region.getcolors(maxcolors=1 << 20)}
    assert len(colours) > 2


def test_render_rejects_inconsistent_input():
    with pytest.raises(ValueError):
        render_panel(PanelContent(frequency_hz=[0.0, 1.0], psd_db=[0.0], symbols=[1.0]))
    with pytest.raises(ValueError):
        render_panel(PanelContent(frequency_hz=[0.0], psd_db=[0.0], symbols=[1.0]))
    with pytest.raises(ValueError):
        render_panel(PanelContent(frequency_hz=[0.0, 1.0], psd_db=[0.0, np.nan],
                                  symbols=[1.0]))
    with pytest.raises(ValueError):
        render_panel(PanelContent(frequency_hz=[0.0, 1.0], psd_db=[0.0, 1.0], symbols=[]))
    with pytest.raises(ValueError):
        render_panel(PanelContent(frequency_hz=[0.0, 1.0], psd_db=[0.0, 1.0],
                                  symbols=[np.inf]))
    with pytest.raises(ValueError):
        render_panel(_content(), db_span=0.0)


def test_unsupported_pixel_format_is_rejected():
    with pytest.raises(ValueError):
        framebuffer_bytes(render_panel(_content()), pixel_format="rgb565")


def test_test_pattern_is_three_distinct_bars():
    # Imported under an alias: a module-level name starting with "test_" would
    # be collected by pytest as a test function, which silently "passes".
    image = make_test_pattern()
    assert image.size == (PANEL_WIDTH, PANEL_HEIGHT)
    middle = PANEL_HEIGHT // 2
    colours = [image.getpixel((x, middle)) for x in (100, 400, 700)]
    assert len(set(colours)) == 3
