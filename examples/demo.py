"""Generate the example gallery.

Run from the repo root:  python examples/demo.py
Outputs land in ./gallery.
"""

import math
import os
import random
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import qrforge
from qrforge.image import Pixmap

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
ASSETS = os.path.join(ROOT, "assets")
GALLERY = os.path.join(ROOT, "gallery")
os.makedirs(GALLERY, exist_ok=True)


def make_logo():
    path = os.path.join(ASSETS, "logo.png")
    if os.path.exists(path):
        return path
    os.makedirs(ASSETS, exist_ok=True)
    logo = Pixmap(160, 160, (0, 0, 0, 0))
    for y in range(160):
        for x in range(160):
            d = math.hypot(x - 80, y - 80)
            if d <= 78:
                t = d / 78
                logo.set(x, y, (int(255 * (1 - t) + 30 * t),
                                int(120 * (1 - t) + 20 * t),
                                int(220 * (1 - t) + 60 * t), 255))
    logo.save(path)
    return path


def make_texture():
    path = os.path.join(ASSETS, "texture.png")
    if os.path.exists(path):
        return path
    os.makedirs(ASSETS, exist_ok=True)
    tex = Pixmap(200, 200, (255, 255, 255, 255))
    rng = random.Random(5)
    for y in range(200):
        for x in range(200):
            u, v = x / 199, y / 199
            r = int(255 * abs(math.sin(u * 3.1 + v)))
            g = int(255 * abs(math.sin(u * 3.1 + v + 2.09)))
            b = int(255 * abs(math.sin(u * 3.1 + v + 4.18)))
            n = rng.randint(-18, 18)
            tex.set(x, y, (max(0, min(255, r + n)), max(0, min(255, g + n)),
                           max(0, min(255, b + n)), 255))
    tex.save(path)
    return path


def main() -> None:
    logo = make_logo()
    texture = make_texture()
    url = "https://example.com/qrforge"
    qr = qrforge.QR(url, ec="h")

    # every preset
    for name in qrforge.presets.names():
        qr.styled(name).render(scale=8).save(os.path.join(GALLERY, f"{name}.png"))

    # a few bespoke compositions
    qr.styled("dots", fg=["#ff0080", "#7928ca"], logo=logo, logo_size=0.26) \
        .render(scale=10).save(os.path.join(GALLERY, "logo_dots.png"))
    qr.styled(module_shape="square", module_scale=1.0, texture=texture,
              texture_mode="cover", bg="#101018", fg="#ffffff") \
        .render(scale=10).save(os.path.join(GALLERY, "texture.png"))
    qr.styled(module_shape="dot", fg=["#00c6ff", "#0072ff"], bg=None) \
        .render(scale=10).save(os.path.join(GALLERY, "transparent.png"))

    # vector + terminal + pdf artifacts
    with open(os.path.join(GALLERY, "neon.svg"), "w") as fh:
        fh.write(qr.svg("neon"))
    with open(os.path.join(GALLERY, "neon.pdf"), "wb") as fh:
        fh.write(qr.pdf("neon"))

    print(f"wrote {len(os.listdir(GALLERY))} files to {GALLERY}")


if __name__ == "__main__":
    main()
