"""Colors: parsing, mixing and conversion.

Accepts hex (``#fff``, ``#ffffff``, ``#ffffff80``), ``rgb()``/``rgba()``,
``hsl()``/``hsla()``, CSS colour names, ``(r, g, b[, a])`` tuples and
:class:`Color` instances.
"""

from __future__ import annotations

import colorsys
import re
from typing import Optional, Sequence, Tuple, Union

from .exceptions import StyleError

ColorLike = Union["Color", str, Sequence[float], None]

NAMED_COLORS = {
    "aliceblue": "#f0f8ff", "antiquewhite": "#faebd7", "aqua": "#00ffff", "aquamarine": "#7fffd4",
    "azure": "#f0ffff", "beige": "#f5f5dc", "bisque": "#ffe4c4", "black": "#000000",
    "blanchedalmond": "#ffebcd", "blue": "#0000ff", "blueviolet": "#8a2be2", "brown": "#a52a2a",
    "burlywood": "#deb887", "cadetblue": "#5f9ea0", "chartreuse": "#7fff00", "chocolate": "#d2691e",
    "coral": "#ff7f50", "cornflowerblue": "#6495ed", "cornsilk": "#fff8dc", "crimson": "#dc143c",
    "cyan": "#00ffff", "darkblue": "#00008b", "darkcyan": "#008b8b", "darkgoldenrod": "#b8860b",
    "darkgray": "#a9a9a9", "darkgreen": "#006400", "darkkhaki": "#bdb76b", "darkmagenta": "#8b008b",
    "darkolivegreen": "#556b2f", "darkorange": "#ff8c00", "darkorchid": "#9932cc",
    "darkred": "#8b0000", "darksalmon": "#e9967a", "darkseagreen": "#8fbc8f",
    "darkslateblue": "#483d8b", "darkslategray": "#2f4f4f", "darkturquoise": "#00ced1",
    "darkviolet": "#9400d3", "deeppink": "#ff1493", "deepskyblue": "#00bfff", "dimgray": "#696969",
    "dodgerblue": "#1e90ff", "firebrick": "#b22222", "floralwhite": "#fffaf0",
    "forestgreen": "#228b22", "fuchsia": "#ff00ff", "gainsboro": "#dcdcdc", "ghostwhite": "#f8f8ff",
    "gold": "#ffd700", "goldenrod": "#daa520", "gray": "#808080", "green": "#008000",
    "greenyellow": "#adff2f", "honeydew": "#f0fff0", "hotpink": "#ff69b4", "indianred": "#cd5c5c",
    "indigo": "#4b0082", "ivory": "#fffff0", "khaki": "#f0e68c", "lavender": "#e6e6fa",
    "lavenderblush": "#fff0f5", "lawngreen": "#7cfc00", "lemonchiffon": "#fffacd",
    "lightblue": "#add8e6", "lightcoral": "#f08080", "lightcyan": "#e0ffff",
    "lightgoldenrodyellow": "#fafad2", "lightgray": "#d3d3d3", "lightgreen": "#90ee90",
    "lightpink": "#ffb6c1", "lightsalmon": "#ffa07a", "lightseagreen": "#20b2aa",
    "lightskyblue": "#87cefa", "lightslategray": "#778899", "lightsteelblue": "#b0c4de",
    "lightyellow": "#ffffe0", "lime": "#00ff00", "limegreen": "#32cd32", "linen": "#faf0e6",
    "magenta": "#ff00ff", "maroon": "#800000", "mediumaquamarine": "#66cdaa", "mediumblue": "#0000cd",
    "mediumorchid": "#ba55d3", "mediumpurple": "#9370db", "mediumseagreen": "#3cb371",
    "mediumslateblue": "#7b68ee", "mediumspringgreen": "#00fa9a", "mediumturquoise": "#48d1cc",
    "mediumvioletred": "#c71585", "midnightblue": "#191970", "mintcream": "#f5fffa",
    "mistyrose": "#ffe4e1", "moccasin": "#ffe4b5", "navajowhite": "#ffdead", "navy": "#000080",
    "oldlace": "#fdf5e6", "olive": "#808000", "olivedrab": "#6b8e23", "orange": "#ffa500",
    "orangered": "#ff4500", "orchid": "#da70d6", "palegoldenrod": "#eee8aa", "palegreen": "#98fb98",
    "paleturquoise": "#afeeee", "palevioletred": "#db7093", "papayawhip": "#ffefd5",
    "peachpuff": "#ffdab9", "peru": "#cd853f", "pink": "#ffc0cb", "plum": "#dda0dd",
    "powderblue": "#b0e0e6", "purple": "#800080", "rebeccapurple": "#663399", "red": "#ff0000",
    "rosybrown": "#bc8f8f", "royalblue": "#4169e1", "saddlebrown": "#8b4513", "salmon": "#fa8072",
    "sandybrown": "#f4a460", "seagreen": "#2e8b57", "seashell": "#fff5ee", "sienna": "#a0522d",
    "silver": "#c0c0c0", "skyblue": "#87ceeb", "slateblue": "#6a5acd", "slategray": "#708090",
    "snow": "#fffafa", "springgreen": "#00ff7f", "steelblue": "#4682b4", "tan": "#d2b48c",
    "teal": "#008080", "thistle": "#d8bfd8", "tomato": "#ff6347", "transparent": "#00000000",
    "turquoise": "#40e0d0", "violet": "#ee82ee", "wheat": "#f5deb3", "white": "#ffffff",
    "whitesmoke": "#f5f5f5", "yellow": "#ffff00", "yellowgreen": "#9acd32",
}

_HEX_RE = re.compile(r"^#?([0-9a-fA-F]{3,8})$")
_RGB_RE = re.compile(r"^rgba?\(\s*([-\d.]+%?)\s*[,\s]\s*([-\d.]+%?)\s*[,\s]\s*([-\d.]+%?)\s*(?:[,/]\s*([-\d.]+%?)\s*)?\)$")
_HSL_RE = re.compile(r"^hsla?\(\s*([-\d.]+)(?:deg)?\s*[,\s]\s*([\d.]+)%?\s*[,\s]\s*([\d.]+)%?\s*(?:[,/]\s*([-\d.]+%?)\s*)?\)$")


def _clamp_byte(value: float) -> int:
    return max(0, min(255, int(round(value))))


class Color:
    """An RGBA colour with 8 bits per channel."""

    __slots__ = ("r", "g", "b", "a")

    def __init__(self, r: int = 0, g: int = 0, b: int = 0, a: int = 255) -> None:
        self.r = _clamp_byte(r)
        self.g = _clamp_byte(g)
        self.b = _clamp_byte(b)
        self.a = _clamp_byte(a)

    # ------------------------------------------------------------------ parsing
    @classmethod
    def parse(cls, value: ColorLike) -> "Color":
        if value is None:
            return cls(0, 0, 0, 0)
        if isinstance(value, Color):
            return value
        if isinstance(value, (tuple, list)):
            parts = list(value)
            if len(parts) == 3:
                return cls(*parts)
            if len(parts) == 4:
                r, g, b, a = parts
                return cls(r, g, b, a * 255 if isinstance(a, float) and a <= 1 else a)
            raise StyleError(f"cannot read colour {value!r}")
        if isinstance(value, int):
            return cls((value >> 16) & 255, (value >> 8) & 255, value & 255)
        if not isinstance(value, str):
            raise StyleError(f"cannot read colour {value!r}")
        text = value.strip()
        lowered = text.lower()
        if lowered in NAMED_COLORS:
            text = NAMED_COLORS[lowered]
        match = _HEX_RE.match(text)
        if match:
            digits = match.group(1)
            if len(digits) in (3, 4):
                digits = "".join(ch * 2 for ch in digits)
            if len(digits) == 6:
                digits += "ff"
            if len(digits) != 8:
                raise StyleError(f"cannot read colour {value!r}")
            return cls(int(digits[0:2], 16), int(digits[2:4], 16),
                       int(digits[4:6], 16), int(digits[6:8], 16))
        match = _RGB_RE.match(lowered)
        if match:
            channels = []
            for i in range(3):
                raw = match.group(i + 1)
                channels.append(float(raw[:-1]) * 2.55 if raw.endswith("%") else float(raw))
            alpha = match.group(4)
            a = 255.0
            if alpha is not None:
                a = float(alpha[:-1]) * 2.55 if alpha.endswith("%") else float(alpha) * 255
            return cls(channels[0], channels[1], channels[2], a)
        match = _HSL_RE.match(lowered)
        if match:
            h = float(match.group(1)) / 360.0
            s = float(match.group(2)) / 100.0
            light = float(match.group(3)) / 100.0
            r, g, b = colorsys.hls_to_rgb(h % 1.0, light, s)
            alpha = match.group(4)
            a = 255.0 if alpha is None else (
                float(alpha[:-1]) * 2.55 if alpha.endswith("%") else float(alpha) * 255)
            return cls(r * 255, g * 255, b * 255, a)
        raise StyleError(f"cannot read colour {value!r}")

    # ---------------------------------------------------------------- conversion
    @property
    def rgba(self) -> Tuple[int, int, int, int]:
        return (self.r, self.g, self.b, self.a)

    @property
    def rgb(self) -> Tuple[int, int, int]:
        return (self.r, self.g, self.b)

    @property
    def alpha(self) -> float:
        return self.a / 255.0

    @property
    def is_opaque(self) -> bool:
        return self.a == 255

    def hex(self, with_alpha: bool = False) -> str:
        base = f"#{self.r:02x}{self.g:02x}{self.b:02x}"
        return base + (f"{self.a:02x}" if with_alpha and self.a != 255 else "")

    @property
    def css(self) -> str:
        if self.a == 255:
            return self.hex()
        return f"rgba({self.r}, {self.g}, {self.b}, {round(self.a / 255.0, 3)})"

    def hsl(self) -> Tuple[float, float, float]:
        h, l, s = colorsys.rgb_to_hls(self.r / 255, self.g / 255, self.b / 255)
        return (h * 360, s, l)

    # ---------------------------------------------------------------- operations
    def with_alpha(self, alpha: float) -> "Color":
        return Color(self.r, self.g, self.b, alpha * 255)

    def mix(self, other: ColorLike, t: float) -> "Color":
        """Linear interpolation towards ``other`` (``t`` 0..1), alpha aware."""
        o = Color.parse(other)
        t = max(0.0, min(1.0, t))
        return Color(self.r + (o.r - self.r) * t,
                     self.g + (o.g - self.g) * t,
                     self.b + (o.b - self.b) * t,
                     self.a + (o.a - self.a) * t)

    def lighten(self, amount: float) -> "Color":
        return self.mix(Color(255, 255, 255, self.a), amount)

    def darken(self, amount: float) -> "Color":
        return self.mix(Color(0, 0, 0, self.a), amount)

    def rotate(self, degrees: float) -> "Color":
        h, s, l = self.hsl()
        r, g, b = colorsys.hls_to_rgb(((h + degrees) / 360.0) % 1.0, l, s)
        return Color(r * 255, g * 255, b * 255, self.a)

    @property
    def luminance(self) -> float:
        """Relative luminance (0..1) as used for contrast calculations."""
        def channel(v: int) -> float:
            c = v / 255.0
            return c / 12.92 if c <= 0.03928 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * channel(self.r) + 0.7152 * channel(self.g) + 0.0722 * channel(self.b)

    def contrast(self, other: ColorLike) -> float:
        """WCAG contrast ratio (1..21) against ``other``."""
        l1, l2 = sorted((self.luminance, Color.parse(other).luminance), reverse=True)
        return (l1 + 0.05) / (l2 + 0.05)

    def is_dark(self) -> bool:
        return self.luminance < 0.5

    # ------------------------------------------------------------------ dunder
    def __eq__(self, other: object) -> bool:
        return isinstance(other, Color) and self.rgba == other.rgba

    def __hash__(self) -> int:
        return hash(self.rgba)

    def __repr__(self) -> str:
        return f"Color({self.css})"


def parse(value: ColorLike) -> Color:
    return Color.parse(value)


def blend(base: Sequence[int], top: Sequence[int], opacity: float = 1.0) -> Tuple[int, int, int, int]:
    """Source-over compositing of two RGBA colours, returns RGBA."""
    a = (top[3] / 255.0) * opacity
    if a <= 0:
        return tuple(base)  # type: ignore[return-value]
    if a >= 1 and base[3] == 255:
        return (top[0], top[1], top[2], 255)
    out_a = a + (base[3] / 255.0) * (1 - a)
    if out_a <= 0:
        return (0, 0, 0, 0)
    out = tuple(int(round((top[i] * a + base[i] * (base[3] / 255.0) * (1 - a)) / out_a))
                for i in range(3))
    return (out[0], out[1], out[2], int(round(out_a * 255)))
