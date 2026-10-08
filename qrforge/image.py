"""A tiny RGBA pixel buffer with a built-in PNG codec.

PNG reading and writing are implemented on top of :mod:`zlib` from the standard
library, so QRForge can load logos/textures and export images with **no
dependencies at all**.  When Pillow happens to be installed it is used for the
formats PNG cannot cover (JPEG, GIF, WEBP, BMP, ...) and for ``to_pil()``.
"""

from __future__ import annotations

import io
import struct
import zlib
from typing import Callable, Optional, Sequence, Tuple, Union

from .color import Color, ColorLike

Color4 = Tuple[int, int, int, int]
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"


def _pil():
    try:
        import PIL.Image as pil  # type: ignore
    except ImportError:  # pragma: no cover - depends on the environment
        return None
    return pil


class Pixmap:
    """An RGBA image stored as a flat :class:`bytearray`."""

    __slots__ = ("width", "height", "data")

    def __init__(self, width: int, height: int,
                 color: Union[Color4, ColorLike, None] = None,
                 data: Optional[bytearray] = None) -> None:
        self.width = int(width)
        self.height = int(height)
        if data is not None:
            if len(data) != self.width * self.height * 4:
                raise ValueError("buffer size does not match the dimensions")
            self.data = data
        else:
            rgba = Color.parse(color).rgba if color is not None else (0, 0, 0, 0)
            self.data = bytearray(bytes(rgba)) * (self.width * self.height)

    # ------------------------------------------------------------- constructors
    @classmethod
    def new(cls, width: int, height: int, color: ColorLike = None) -> "Pixmap":
        return cls(width, height, color)

    @classmethod
    def open(cls, source) -> "Pixmap":
        """Load an image from a path, file-like object, bytes or a PIL image."""
        if isinstance(source, Pixmap):
            return source.copy()
        pil = _pil()
        if pil is not None and isinstance(source, pil.Image):
            return cls.from_pil(source)
        if isinstance(source, (bytes, bytearray)):
            raw = bytes(source)
        elif isinstance(source, (str,)):
            with open(source, "rb") as handle:
                raw = handle.read()
        elif hasattr(source, "read"):
            raw = source.read()
        else:
            raise TypeError(f"cannot open image from {type(source)!r}")
        if raw.startswith(PNG_SIGNATURE):
            try:
                return decode_png(raw)
            except NotImplementedError:
                pass  # interlaced / unusual bit depth -> let Pillow try
        if pil is None:
            raise ValueError("only PNG can be read without Pillow "
                             "(install Pillow for JPEG/GIF/WEBP/BMP support)")
        return cls.from_pil(pil.open(io.BytesIO(raw)))

    @classmethod
    def from_pil(cls, image) -> "Pixmap":
        image = image.convert("RGBA")
        return cls(image.width, image.height, data=bytearray(image.tobytes()))

    # ------------------------------------------------------------------ pixels
    def get(self, x: int, y: int) -> Color4:
        i = (y * self.width + x) * 4
        return (self.data[i], self.data[i + 1], self.data[i + 2], self.data[i + 3])

    def set(self, x: int, y: int, color: Color4) -> None:
        i = (y * self.width + x) * 4
        self.data[i:i + 4] = bytes(color)

    def fill(self, color: ColorLike) -> None:
        self.data = bytearray(bytes(Color.parse(color).rgba)) * (self.width * self.height)

    def copy(self) -> "Pixmap":
        return Pixmap(self.width, self.height, data=bytearray(self.data))

    def in_bounds(self, x: int, y: int) -> bool:
        return 0 <= x < self.width and 0 <= y < self.height

    def sample(self, x: float, y: float) -> Color4:
        """Bilinear sample at fractional coordinates (edge clamped)."""
        w, h = self.width, self.height
        fx = min(max(x - 0.5, 0.0), w - 1.0)
        fy = min(max(y - 0.5, 0.0), h - 1.0)
        x0, y0 = int(fx), int(fy)
        x1, y1 = min(x0 + 1, w - 1), min(y0 + 1, h - 1)
        tx, ty = fx - x0, fy - y0
        data = self.data
        stride = w * 4
        i00 = (y0 * w + x0) * 4
        i01 = (y0 * w + x1) * 4
        i10 = (y1 * w + x0) * 4
        i11 = (y1 * w + x1) * 4
        out = []
        for c in range(4):
            top = data[i00 + c] + (data[i01 + c] - data[i00 + c]) * tx
            bottom = data[i10 + c] + (data[i11 + c] - data[i10 + c]) * tx
            out.append(int(round(top + (bottom - top) * ty)))
        return (out[0], out[1], out[2], out[3])

    def blit(self, other: "Pixmap", x: int, y: int, opacity: float = 1.0,
             mask: Optional[Callable[[int, int], float]] = None) -> None:
        """Composite ``other`` over this image at (x, y)."""
        for row in range(other.height):
            ty = y + row
            if not 0 <= ty < self.height:
                continue
            for col in range(other.width):
                tx = x + col
                if not 0 <= tx < self.width:
                    continue
                src = other.get(col, row)
                alpha = (src[3] / 255.0) * opacity
                if mask is not None:
                    alpha *= mask(col, row)
                if alpha <= 0:
                    continue
                dst = self.get(tx, ty)
                self.set(tx, ty, _compose(dst, src, alpha))

    def paste_cover(self, other: "Pixmap", opacity: float = 1.0) -> None:
        """Scale ``other`` to cover this image completely and composite it."""
        resized = other.resized(self.width, self.height, "cover")
        offset_x = (resized.width - self.width) // 2
        offset_y = (resized.height - self.height) // 2
        self.blit(resized, -offset_x, -offset_y, opacity)

    def resized(self, width: int, height: int, mode: str = "stretch") -> "Pixmap":
        """Bilinear resize; ``mode`` is ``stretch``, ``cover`` or ``contain``."""
        if mode in ("cover", "contain") and self.width and self.height:
            scale = max(width / self.width, height / self.height) if mode == "cover" \
                else min(width / self.width, height / self.height)
            width = max(1, int(round(self.width * scale)))
            height = max(1, int(round(self.height * scale)))
        out = Pixmap(width, height)
        if width == self.width and height == self.height:
            out.data = bytearray(self.data)
            return out
        sx = self.width / width
        sy = self.height / height
        data = self.data
        sw = self.width
        for ty in range(height):
            fy = min(max((ty + 0.5) * sy - 0.5, 0.0), self.height - 1.0)
            y0 = int(fy)
            y1 = min(y0 + 1, self.height - 1)
            wy = fy - y0
            row_top = y0 * sw * 4
            row_bot = y1 * sw * 4
            target = ty * width * 4
            for tx in range(width):
                fx = min(max((tx + 0.5) * sx - 0.5, 0.0), sw - 1.0)
                x0 = int(fx)
                x1 = min(x0 + 1, sw - 1)
                wx = fx - x0
                i00 = row_top + x0 * 4
                i01 = row_top + x1 * 4
                i10 = row_bot + x0 * 4
                i11 = row_bot + x1 * 4
                pos = target + tx * 4
                for c in range(4):
                    top = data[i00 + c] + (data[i01 + c] - data[i00 + c]) * wx
                    bottom = data[i10 + c] + (data[i11 + c] - data[i10 + c]) * wx
                    out.data[pos + c] = int(round(top + (bottom - top) * wy))
        return out

    def rotated(self, degrees: float) -> "Pixmap":
        """Return a copy rotated about its centre (transparent corners)."""
        if degrees % 360 == 0:
            return self.copy()
        import math
        rad = math.radians(degrees)
        cos_a, sin_a = math.cos(rad), math.sin(rad)
        w, h = self.width, self.height
        size = int(math.ceil(math.hypot(w, h)))
        out = Pixmap(size, size, (0, 0, 0, 0))
        cx = cy = size / 2.0
        scx, scy = w / 2.0, h / 2.0
        for y in range(size):
            for x in range(size):
                dx, dy = x - cx, y - cy
                sx = dx * cos_a + dy * sin_a + scx
                sy = -dx * sin_a + dy * cos_a + scy
                if 0 <= sx < w and 0 <= sy < h:
                    out.set(x, y, self.sample(sx, sy))
        return out

    def map_pixels(self, fn: Callable[[int, int, Color4], Color4]) -> None:
        for y in range(self.height):
            row = y * self.width * 4
            for x in range(self.width):
                i = row + x * 4
                self.data[i:i + 4] = bytes(fn(x, y, (self.data[i], self.data[i + 1],
                                                     self.data[i + 2], self.data[i + 3])))

    # ------------------------------------------------------------------ output
    def to_png(self, compress: int = 6) -> bytes:
        return encode_png(self.width, self.height, self.data, compress)

    def save(self, path: str, compress: int = 6) -> str:
        if path.lower().endswith(".png"):
            with open(path, "wb") as handle:
                handle.write(self.to_png(compress))
            return path
        pil = _pil()
        if pil is None:
            raise ValueError("only PNG can be written without Pillow")
        self.to_pil().save(path)
        return path

    def to_pil(self):
        pil = _pil()
        if pil is None:
            raise ValueError("Pillow is required for to_pil()")
        return pil.frombytes("RGBA", (self.width, self.height), bytes(self.data))

    def __repr__(self) -> str:
        return f"<Pixmap {self.width}x{self.height}>"


def _compose(dst: Color4, src: Color4, alpha: float) -> Color4:
    if alpha >= 1.0:
        return (src[0], src[1], src[2], 255)
    da = dst[3] / 255.0
    out_a = alpha + da * (1 - alpha)
    if out_a <= 0:
        return (0, 0, 0, 0)
    return tuple(  # type: ignore[return-value]
        int(round((src[i] * alpha + dst[i] * da * (1 - alpha)) / out_a)) for i in range(3)
    ) + (int(round(out_a * 255)),)


# ---------------------------------------------------------------------- PNG I/O
def encode_png(width: int, height: int, data: Sequence[int], compress: int = 6) -> bytes:
    """Encode raw RGBA8 pixels into a PNG file (no dependencies)."""
    stride = width * 4
    raw = bytearray()
    prev = bytes(stride)
    for y in range(height):
        start = y * stride
        line = bytes(data[start:start + stride])
        # choose the cheapest of None / Sub / Up using the sum-of-abs heuristic
        candidates = (line, _filter_sub(line), _filter_up(line, prev))
        best = min(range(3), key=lambda i: sum(candidates[i]))
        raw.append(best)
        raw += candidates[best]
        prev = line
    body = b"".join((
        _chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)),
        _chunk(b"IDAT", zlib.compress(bytes(raw), compress)),
        _chunk(b"IEND", b""),
    ))
    return PNG_SIGNATURE + body


def _filter_sub(line: bytes) -> bytes:
    out = bytearray(len(line))
    for i in range(len(line)):
        left = line[i - 4] if i >= 4 else 0
        out[i] = (line[i] - left) & 0xFF
    return bytes(out)


def _filter_up(line: bytes, prev: bytes) -> bytes:
    return bytes((line[i] - prev[i]) & 0xFF for i in range(len(line)))


def _chunk(tag: bytes, payload: bytes) -> bytes:
    return (struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF))


def decode_png(raw: bytes) -> Pixmap:
    """Decode a PNG (8/16-bit, grey/RGB/palette/alpha, non-interlaced)."""
    if not raw.startswith(PNG_SIGNATURE):
        raise ValueError("not a PNG file")
    pos = 8
    width = height = depth = ctype = interlace = 0
    palette: list = []
    trans: Optional[bytes] = None
    idat = bytearray()
    while pos + 8 <= len(raw):
        length = struct.unpack(">I", raw[pos:pos + 4])[0]
        tag = raw[pos + 4:pos + 8]
        payload = raw[pos + 8:pos + 8 + length]
        pos += 12 + length
        if tag == b"IHDR":
            width, height, depth, ctype, comp, filt, interlace = struct.unpack(">IIBBBBB", payload)
        elif tag == b"PLTE":
            palette = [tuple(payload[i:i + 3]) for i in range(0, len(payload), 3)]
        elif tag == b"tRNS":
            trans = payload
        elif tag == b"IDAT":
            idat += payload
        elif tag == b"IEND":
            break
    if interlace:
        raise NotImplementedError("interlaced PNGs need Pillow")
    stream = zlib.decompress(bytes(idat))
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[ctype]
    if depth == 16:
        bpp = channels * 2
    elif depth in (1, 2, 4) and ctype == 3:
        bpp = 1
    elif depth == 8:
        bpp = channels
    else:
        raise NotImplementedError(f"unsupported PNG bit depth {depth}")
    stride = (width * bpp * depth + 7) // 8
    pixels = bytearray(height * stride)
    prev = bytes(stride)
    idx = 0
    for y in range(height):
        filt = stream[idx]
        idx += 1
        line = bytearray(stream[idx:idx + stride])
        idx += stride
        _unfilter(filt, line, prev, bpp)
        pixels[y * stride:(y + 1) * stride] = line
        prev = bytes(line)
    out = Pixmap(width, height)
    data = out.data
    step = channels * (2 if depth == 16 else 1)
    for y in range(height):
        base = y * stride
        for x in range(width):
            if ctype == 3:  # palette
                if depth == 8:
                    entry = pixels[base + x]
                else:
                    per = 8 // depth
                    byte = pixels[base + x // per]
                    entry = (byte >> (8 - depth * (x % per + 1))) & ((1 << depth) - 1)
                r, g, b = palette[entry] if entry < len(palette) else (0, 0, 0)
                a = trans[entry] if (trans and entry < len(trans)) else 255
            else:
                off = base + x * step
                if ctype in (0, 4):  # grey, grey + alpha
                    r = g = b = pixels[off]
                    a = pixels[off + (2 if depth == 16 else 1)] if ctype == 4 else 255
                else:  # RGB, RGBA
                    r = pixels[off]
                    g = pixels[off + (2 if depth == 16 else 1)]
                    b = pixels[off + (4 if depth == 16 else 2)]
                    a = pixels[off + (6 if depth == 16 else 3)] if ctype == 6 else 255
            i = (y * width + x) * 4
            data[i] = r
            data[i + 1] = g
            data[i + 2] = b
            data[i + 3] = a
    return out


def _unfilter(filt: int, line: bytearray, prev: bytes, bpp: int) -> None:
    if filt == 0:
        return
    if filt == 1:  # Sub
        for i in range(bpp, len(line)):
            line[i] = (line[i] + line[i - bpp]) & 0xFF
    elif filt == 2:  # Up
        for i in range(len(line)):
            line[i] = (line[i] + prev[i]) & 0xFF
    elif filt == 3:  # Average
        for i in range(len(line)):
            left = line[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + ((left + prev[i]) >> 1)) & 0xFF
    elif filt == 4:  # Paeth
        for i in range(len(line)):
            a = line[i - bpp] if i >= bpp else 0
            b = prev[i]
            c = prev[i - bpp] if i >= bpp else 0
            line[i] = (line[i] + _paeth(a, b, c)) & 0xFF
    else:
        raise ValueError(f"unknown PNG filter {filt}")


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    return b if pb <= pc else c
