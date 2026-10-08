# qrforge
![Python Version](https://img.shields.io/badge/python-3.8+-blue.svg)
![License](https://img.shields.io/badge/license-MIT-brightgreen.svg)
![Tests](https://img.shields.io/badge/tests-passing-brightgreen.svg)
![Dependencies](https://img.shields.io/badge/dependencies-0%20(required)-blue.svg)

An open-source Python library for **generating and art-directing QR codes**: custom module shapes, gradients, shaders, logos, image textures, backgrounds and shadows — output to PNG, SVG, PDF, terminal ANSI, ASCII or Pillow.

*qrforge implements the full QR encoding pipeline (modes, Reed–Solomon error correction, masking, versions 1–40) from scratch against the standard library. There are **zero required dependencies**; [Pillow](https://pillow.readthedocs.io) is used only for non-PNG image formats, PIL images, or JPEG/GIF/WEBP logos. PNG reading/writing is built in.*

> [!NOTE]
> **qrforge** is intended to produce both *correct* and *beautiful* QR codes. Every rendered symbol is round-trip verified by a bundled decoder, and the test-suite re-rasterises the SVG geometry to prove it reproduces the matrix — so "pretty" never comes at the cost of "scannable".

## Installation

You can install qrforge using pip:

```bash
pip install qrforge
```

Or from source:

```bash
pip install .            # or copy the qrforge/ folder next to your code
pip install pillow       # optional, only for non-PNG formats / PIL images
```

## Supported Python Versions

* Python 3.8 / 3.9 / 3.10 / 3.11 / 3.12 (or later)

## Features

* **Correct encoder** – versions 1–40, EC levels L/M/Q/H, optimal numeric/alphanumeric/byte segmentation, automatic mask selection.
* **Shapes** – square, rounded, dot, diamond, hexagon, star, cross, squircle, leaf, heart etc. plus random-per-module mixes and your own SDF shapes.
* **Gradients & colours** – hex / `rgb()` / `hsl()` / CSS names; linear, radial and conic gradients for modules, eyes and background.
* **Shaders** – grain, glow, wave, twist, glitch, chromatic aberration, halftone, duotone, scanlines, vignette etc. plus custom Python or one-line expression shaders.
* **Logos & textures** – auto knockout zone, round/clip the logo, logo background, stroke, rotation, opacity; paint any image inside the modules.
* **Outputs** – PNG (pure-Python codec), SVG (tiny vector), PDF (vector), terminal ANSI, ASCII, Pillow, HTML.
* **22 ready-made presets** and a CLI.

## Usage

### Quickstart

```python
import qrforge

qrforge.save("https://example.com", "code.png", "neon", scale=12)

qr = qrforge.QR("hello", ec="h")
qr.use_style(module_shape="dot", fg=["#ff0080", "#7928ca"], logo="logo.png")
qr.save("poster.png", scale=14)
qr.save("poster.svg")
print(qr.terminal())
```

### Colours & gradients

```python
qr.use_style(fg=["#ff9a3c", "#ff4d6d", "#7b2ff7"])          # linear
qr.use_style(fg={"kind":"radial", "colors":["#fff","#1f6feb"]})
qr.use_style(fg={"kind":"conic",  "colors":["#ff71ce","#01cdfe","#05ffa1"]})
```

### Shapes & eyes

```python
qr.use_style(module_shape=["dot","star","hexagon"], seed=3, module_jitter=0.2,
             eye_shape="rounded", eye_dot_shape="circle")

@qrforge.shape("wave")          # register a custom shape (SDF in module units)
def wave(x, y, radius=0.0):
    import math
    return qrforge.shapes.sd_circle(x, y + 0.08*math.sin(x*9), 0.5)
```

### Shaders

```python
qr.use_style(shaders=["wave:amplitude=4,wavelength=36", "chromatic:offset=2"])

@qrforge.shader                 # custom per-pixel shader
def heat(x, y, color, ctx):
    return color.mix("#ff4400", ctx.uv(x, y)[1])
```

### Logos

```python
qr.use_style(logo="logo.png", logo_size=0.26, logo_shape="rounded",
             logo_radius=0.4, logo_bg="#ffffff", logo_stroke=("#000", 0.2),
             logo_rotation=0, logo_opacity=1.0)
```

### Presets & overrides

Any preset's defaults (colours, shaders,  etc.) can be overridden:

```python
qrforge.save("hi", "out.png", "neon", fg="#00ff88", scale=12)
qrforge.presets.get("sunset", bg="#000000")
```

Presets: `classic dots rounded soft confetti neon sunset blueprint brutal vapor
film halftone gold ice leaf circuit retro glitch minimal badge starry cross`.

## Correctness

```python
qr.verify()                      # decodes the symbol again
from qrforge.verify import decode
```

## CLI

```bash
python -m qrforge "https://example.com" -o out.png -p neon -s 12 -e h
python -m qrforge "hi" --terminal
python -m qrforge --list-presets --list-shapes --list-shaders
```

## Testing

```bash
python -m pytest tests -q
```

The suite cross-checks the spec tables, Reed–Solomon correction, optimal
segmentation against a brute-force reference, the PNG codec against Pillow, and
re-rasterises every preset + the SVG geometry to prove each one still scans.

## Contributing

Contributions are welcome! See [CONTRIBUTING.md](CONTRIBUTING.md). If you encounter any issues or have an edge use case, please open an issue using the templates in `.github/ISSUE_TEMPLATE`.

## License

qrforge is released under the terms of the **MIT License (Modified)**. Please see the [LICENSE.md](LICENSE.md) file for the full text.
