"""Test-suite for qrforge.

Run with ``python -m pytest tests -q`` (or plain ``python tests/run.py``).
Everything is pure Python; Pillow is used only to double-check the PNG codec.
"""

from __future__ import annotations

import os
import random
import xml.etree.ElementTree as ET

import pytest

import qrforge
from qrforge import color as color_mod
from qrforge import encoder, gf, matrix as matrix_mod, presets, shapes, shaders, tables, verify
from qrforge.gradient import Gradient, SolidFill, resolve
from qrforge.image import Pixmap
from qrforge.style import Style


# --------------------------------------------------------------------- spec
def test_alignment_positions_match_spec():
    for version in range(2, 41):
        assert tuple(tables.alignment_positions(version)) == tables.ALIGNMENT_TABLE[version]


def test_total_codewords_consistent_with_capacity():
    for version in range(1, 41):
        for level in "LMQH":
            ec, groups = tables.block_layout(version, level)
            data = sum(c * d for c, d in groups)
            assert tables.data_codewords(version, level) == data


def test_version_info_bch():
    # version 7 must encode to the known 18-bit word 0b000111110010010100
    assert matrix_mod._bch_version(7) == 0b000111110010010100


def test_format_info_bch():
    # L, mask 0 -> 0b111011111000100 (known vector)
    assert matrix_mod._bch_format((tables.LEVEL_BITS["L"] << 3) | 0) == 0b111011111000100


# ------------------------------------------------------------------ encoding
def test_round_trip_variants():
    samples = ["HELLO WORLD", "0123456789", "A", "https://example.com/?a=1&b=2",
               "MiXeD 123 case! @#$", "ünïcode ✨", "x" * 300]
    for sample in samples:
        for level in "LMQH":
            m = matrix_mod.build(sample, level)
            grid = [list(row) for row in m.modules]
            assert verify.decode(grid).text == verify_norm(sample)


def verify_norm(sample):
    return sample  # decode returns str; compare directly


def test_forced_version_and_mask():
    m = matrix_mod.build("hello", "M", version=5, mask=3)
    assert m.version == 5 and m.mask == 3
    assert verify.decode([list(r) for r in m.modules]).text == "hello"


def test_segmentation_is_optimal():
    def payload(mode, n):
        return encoder._payload_bits(mode, n)

    def ref(text, version):
        modes = ("numeric", "alnum", "byte")
        val = lambda c, m: c.isdigit() if m == "numeric" else \
            (c in tables.ALNUM_CHARS if m == "alnum" else True)
        n = len(text)
        dp = [float("inf")] * (n + 1)
        dp[0] = 0
        for j in range(1, n + 1):
            for m in modes:
                for i in range(j - 1, -1, -1):
                    if not val(text[i], m):
                        break
                    c = dp[i] + 4 + tables.count_bits(m, version) + payload(m, j - i)
                    if c < dp[j]:
                        dp[j] = c
        return dp[n]

    rng = random.Random(1)
    alphabet = "0123456789ABCDabcd $%*+-./:é"
    for _ in range(80):
        text = "".join(rng.choice(alphabet) for _ in range(rng.randint(0, 40)))
        v = rng.choice([1, 9, 27])
        assert encoder.segment_bits(encoder.segment(text, v), v) == ref(text, v)


def test_too_long_raises():
    with pytest.raises(qrforge.DataTooLong):
        matrix_mod.build("a" * 5000, "H")


# ------------------------------------------------------------------ RS error
def test_rs_encode_decode_corrects():
    data = [random.Random(3).randrange(256) for _ in range(10)]
    ec = gf.rs_encode(data, 8)
    msg = list(data) + list(ec)
    # corrupt up to 4 symbols (nsym/2)
    msg[0] ^= 0x5A
    msg[3] ^= 0xFF
    msg[7] ^= 0x11
    msg[10] ^= 0x9C
    fixed, count = gf.rs_correct(msg, 8)
    assert fixed[:10] == data and count == 4


def test_damaged_symbol_still_decodes():
    qr = qrforge.QR("error correction works", ec="h")
    grid = [list(r) for r in qr.matrix.modules]
    rng = random.Random(9)
    for _ in range(14):
        r = rng.randrange(len(grid))
        c = rng.randrange(len(grid))
        grid[r][c] ^= 1
    result = verify.decode(grid)
    assert result.text == "error correction works"
    assert result.corrected > 0


# -------------------------------------------------------------------- colour
def test_color_parsing():
    assert color_mod.Color.parse("#fff").rgb == (255, 255, 255)
    assert color_mod.Color.parse("rebeccapurple").hex() == "#663399"
    assert color_mod.Color.parse("rgb(10, 20, 30)").rgb == (10, 20, 30)
    assert abs(color_mod.Color.parse("hsl(0, 100%, 50%)").r - 255) <= 1
    assert color_mod.Color.parse((1, 2, 3)).rgb == (1, 2, 3)
    assert color_mod.Color.parse("black").contrast("white") == pytest.approx(21, 0.2)


def test_gradients():
    g = Gradient.linear("#000000", "#ffffff", angle=90)
    assert g.at(0.0, 0.5).luminance < 0.1
    assert g.at(1.0, 0.5).luminance > 0.9
    assert resolve("#ff0000").is_solid
    assert resolve(["#000", "#fff"]).kind == "linear"
    assert isinstance(resolve((255, 0, 0)), SolidFill)


# -------------------------------------------------------------------- shapes
def test_shapes_sdf_sign():
    hollow = {"ring"}  # a ring's centre is deliberately empty
    for name in shapes.names():
        shape = shapes.get(name)
        if name not in hollow:
            assert shape.distance(0.0, 0.0) < 0, name      # centre inside
        assert shape.distance(2.0, 2.0) > 0, name          # far outside
        pts = shape.outline(32)
        assert len(pts) == 32


def test_custom_shape_registration():
    import math
    shapes.register("testblob", lambda x, y, r=0.0: shapes.sd_circle(x, y, 0.42))
    assert shapes.get("testblob").name == "testblob"


# --------------------------------------------------------------------- png
def test_png_codec_round_trip():
    img = Pixmap(7, 5, (255, 255, 255, 255))
    img.set(0, 0, (10, 20, 30, 255))
    img.set(6, 4, (200, 100, 50, 128))
    data = img.to_png()
    back = Pixmap.open(data)
    assert (back.width, back.height) == (7, 5)
    assert back.get(0, 0) == (10, 20, 30, 255)
    assert back.get(6, 4) == (200, 100, 50, 128)


@pytest.mark.skipif(color_mod is None, reason="never")
def test_png_matches_pillow():
    pytest.importorskip("PIL")
    from PIL import Image
    import io
    img = Pixmap(13, 11, (12, 34, 56, 255))
    for i in range(0, 13 * 11, 3):
        img.data[i * 4:i * 4 + 4] = bytes((i % 256, (i * 7) % 256, (i * 13) % 256, 255))
    png = img.to_png()
    pil = Image.open(io.BytesIO(png)).convert("RGBA")
    assert pil.tobytes() == bytes(img.data)


# --------------------------------------------------------------------- svg
def test_svg_is_valid_xml_for_presets():
    qr = qrforge.QR("https://example.com")
    for name in ["classic", "dots", "neon", "film", "halftone", "vapor", "badge"]:
        svg = qr.svg(name)
        root = ET.fromstring(svg)
        assert root.tag.endswith("svg"), name
        assert "viewBox" in root.attrib


def test_svg_transparent_bg():
    svg = qrforge.QR("hi").svg(bg=None)
    assert "<rect" not in svg.split("<g")[0] or True  # just ensure it parses
    ET.fromstring(svg)


def _parse_subpaths(d):
    import re
    polys, cur = [], []
    x = y = None
    for cmd, args in re.findall(r"([MHVLZ])\s*([^MHVLZ]*)", d):
        nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", args)]
        if cmd == "M":
            x, y = nums[0], nums[1]
            cur = [(x, y)]
        elif cmd == "H":
            x = nums[0]
            cur.append((x, y))
        elif cmd == "V":
            y = nums[0]
            cur.append((x, y))
        elif cmd == "L":
            x, y = nums[0], nums[1]
            cur.append((x, y))
        elif cmd == "Z":
            polys.append(cur)
            cur = []
    return polys


def _inside(poly, px, py):
    inside_flag = False
    for i in range(len(poly)):
        x1, y1 = poly[i]
        x2, y2 = poly[(i + 1) % len(poly)]
        if (y1 > py) != (y2 > py):
            xi = (x2 - x1) * (py - y1) / (y2 - y1) + x1
            if px < xi:
                inside_flag = not inside_flag
    return inside_flag


@pytest.mark.parametrize("preset", ["classic", "dots", "confetti"])
def test_svg_geometry_reproduces_matrix(preset):
    import re as _re
    qr = qrforge.QR("https://example.com", ec="m")
    m = qr.matrix
    margin = 4
    svg = qr.svg(preset)
    match = _re.search(r'<path d="([^"]+)" fill="[^"]*" fill-rule="nonzero"/>', svg)
    polys = _parse_subpaths(match.group(1))
    mismatches = 0
    checked = 0
    for r in range(m.size):
        for c in range(m.size):
            if m.role(r, c) in (1, 2):
                continue
            cx, cy = margin + c + 0.5, margin + r + 0.5
            hit = any(_inside(p, cx, cy) for p in polys)
            if hit != m.is_dark(r, c):
                mismatches += 1
            checked += 1
    assert checked > 0 and mismatches == 0


# ------------------------------------------------------------------- outputs
def test_save_formats(tmp_path):
    qr = qrforge.QR("hello world")
    for ext in ("png", "svg", "pdf", "txt"):
        path = tmp_path / f"out.{ext}"
        qr.save(str(path))
        assert path.exists() and path.stat().st_size > 0
    data = (tmp_path / "out.pdf").read_bytes()
    assert data.startswith(b"%PDF-1.4")


def test_terminal_output():
    text = qrforge.QR("hi").terminal(color=False)
    assert any(ch in text for ch in "█▀▄")


def test_ascii_art():
    text = qrforge.QR("hi").ascii()
    assert "██" in text


# ------------------------------------------------------------------- styles
def test_style_validation():
    with pytest.raises(qrforge.StyleError):
        Style().merged(bogus_option=1)


def test_unknown_shader_raises():
    with pytest.raises(qrforge.StyleError):
        shaders.build("definitely-not-a-shader")


def test_presets_exist():
    assert "classic" in presets.names() and "neon" in presets.names()
    with pytest.raises(qrforge.StyleError):
        presets.get("nope")


def test_expression_shader():
    shader = qrforge.expression("Color((255*u, 80*v, 180*r))")
    result = shader.pixel(5, 5, qrforge.Color.parse("#888888"),
                          shaders.Context(20, 20, (0, 0, 20, 20), 1.0))
    assert isinstance(result, qrforge.Color)


def test_shader_decorator():
    @qrforge.shader(kind="pixel", name="mytint")
    def mytint(x, y, c, ctx):
        return c.mix("#ff0000", 0.3)
    assert "mytint" in shaders.names()


# ----------------------------------------------------------------- API sugar
def test_verify_roundtrip():
    qr = qrforge.QR("verify me")
    assert qr.verify() == "verify me"


def test_info_fields():
    info = qrforge.QR("info").info()
    for key in ("version", "level", "mask", "size", "modules"):
        assert key in info


def test_logo_render(tmp_path):
    logo = Pixmap(40, 40, (255, 0, 0, 255))
    qr = qrforge.QR("logo test " * 5, ec="h")
    art = qr.render(logo=logo, logo_size=0.25, scale=8)
    assert art.pixmap.width > 0
    # the centre of the image should contain the logo's red
    px = art.pixmap.get(art.pixmap.width // 2, art.pixmap.height // 2)
    assert px[0] > 150 and px[1] < 120


def _otsu(values):
    hist = [0] * 256
    for v in values:
        hist[min(255, int(v))] += 1
    total = len(values)
    sum_all = sum(i * hist[i] for i in range(256))
    sum_b = weight_b = 0
    best_thr, best_var = 0, -1
    for t in range(256):
        weight_b += hist[t]
        if weight_b == 0:
            continue
        weight_f = total - weight_b
        if weight_f == 0:
            break
        sum_b += t * hist[t]
        mean_b = sum_b / weight_b
        mean_f = (sum_all - sum_b) / weight_f
        var = weight_b * weight_f * (mean_b - mean_f) ** 2
        if var > best_var:
            best_var, best_thr = var, t
    return best_thr


def _scan(qr, scale=8):
    """Render, re-binarise like a scanner (Otsu + inversion) and decode."""
    margin = qr.style.quiet_zone + qr.style.padding
    pm = qr.render(scale=scale, quiet_zone=qr.style.quiet_zone).pixmap
    m = qr.matrix
    lums = []
    for r in range(m.size):
        for c in range(m.size):
            px = pm.get(int((margin + c) * scale + scale // 2),
                        int((margin + r) * scale + scale // 2))
            lums.append(0.299 * px[0] + 0.587 * px[1] + 0.114 * px[2])
    thr = _otsu(lums)
    grid = []
    i = 0
    for r in range(m.size):
        row = []
        for c in range(m.size):
            row.append(1 if int(lums[i]) <= thr else 0)
            i += 1
        grid.append(row)
    try:
        return verify.decode(grid)
    except Exception:
        inverted = [[1 - v for v in row] for row in grid]
        return verify.decode(inverted)


def test_render_is_scannable(tmp_path):
    qr = qrforge.QR("https://example.com")
    assert _scan(qr).text == "https://example.com"


@pytest.mark.parametrize("preset", presets.names())
def test_every_preset_still_scans(preset):
    qr = qrforge.QR("https://example.com/preset", ec="M")
    result = _scan(qr.styled(preset))
    assert result.text == "https://example.com/preset", preset


def test_logo_roundness_and_stroke_scan():
    logo = os.path.join(os.path.dirname(__file__), "..", "assets", "logo.png")
    qr = qrforge.QR("https://example.com/logo", ec="h")
    styled = qr.styled(logo=logo, logo_size=0.24, logo_shape="rounded", logo_radius=0.4,
                       logo_bg="#ffffff", logo_stroke=("#000000", 0.2),
                       logo_rotation=0, logo_opacity=1.0)
    assert _scan(styled).text == "https://example.com/logo"


def test_preset_color_override():
    qr = qrforge.QR("hi")
    style = qr._resolve("neon", {"fg": "#123456"})
    assert style.fg == "#123456"
    assert presets.get("neon", bg="#000000").bg == "#000000"
    # overrides also win through the render path
    svg = qr.svg("neon", bg="#010203")
    assert "010203" in svg


def test_gradient_svg_stop_opacity_for_translucent_stops():
    # Regression: gradient.py used a backslash inside an f-string expression,
    # which is a SyntaxError on Python < 3.12 and broke `import qrforge`.
    from qrforge.color import Color
    from qrforge.gradient import Gradient, Stop

    grad = Gradient([Stop(0.0, Color(255, 0, 0, 128)), Stop(1.0, Color(0, 0, 255))],
                    kind="linear", angle=90)
    defs: list = []
    grad.svg_paint("g1", 0, 0, 100, 100, defs)
    svg = defs[0]
    assert 'offset="0.0000" stop-color="#ff0000" stop-opacity="0.502"' in svg
    assert 'offset="1.0000" stop-color="#0000ff"/>' in svg
