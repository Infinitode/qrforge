"""Shaders.

Three kinds of effect can be applied to a rendered symbol:

``PixelShader``  recolours every pixel (``grain``, ``duotone``, ``sepia``, ...)
``WarpShader``   displaces sampling coordinates (``wave``, ``twist``, ``glitch``)
``PostShader``   needs the whole image (``glow``, ``chromatic``, ``halftone``)

Every built-in also knows how to express itself as an SVG filter where SVG has
an equivalent primitive, so ``style="grain"`` looks the same in ``.svg()`` and
``.png()``.  Write your own with :func:`shader` or :func:`expression`.
"""

from __future__ import annotations

import math
from typing import Any, Callable, Dict, List, Optional, Tuple

from .color import Color, ColorLike
from .exceptions import StyleError

Color4 = Tuple[int, int, int, int]


# --------------------------------------------------------------------- helpers
def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    return lo if value < lo else (hi if value > hi else value)


def smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = clamp((x - edge0) / (edge1 - edge0) if edge1 != edge0 else 0.0)
    return t * t * (3 - 2 * t)


def mix(a, b, t: float):
    if isinstance(a, Color):
        return a.mix(b, t)
    return a + (b - a) * t


def hash2(x: int, y: int, seed: int = 0) -> float:
    """Deterministic 2D hash in [0, 1)."""
    n = (x * 374761393 + y * 668265263 + seed * 1013904223) & 0xFFFFFFFF
    n = ((n ^ (n >> 13)) * 1274126177) & 0xFFFFFFFF
    n = (n ^ (n >> 16)) & 0xFFFFFFFF
    return n / 4294967296.0


def noise2(x: float, y: float, seed: int = 0, octaves: int = 1) -> float:
    """Value noise in [0, 1]."""
    total, amplitude, frequency, norm = 0.0, 1.0, 1.0, 0.0
    for _ in range(max(1, octaves)):
        fx, fy = x * frequency, y * frequency
        x0, y0 = int(math.floor(fx)), int(math.floor(fy))
        tx, ty = fx - x0, fy - y0
        tx, ty = tx * tx * (3 - 2 * tx), ty * ty * (3 - 2 * ty)
        a = hash2(x0, y0, seed)
        b = hash2(x0 + 1, y0, seed)
        c = hash2(x0, y0 + 1, seed)
        d = hash2(x0 + 1, y0 + 1, seed)
        top = a + (b - a) * tx
        bottom = c + (d - c) * tx
        total += (top + (bottom - top) * ty) * amplitude
        norm += amplitude
        amplitude *= 0.5
        frequency *= 2.0
    return total / norm if norm else 0.0


class Context:
    """Everything a shader is allowed to know about the image it is shading."""

    def __init__(self, width: int, height: int, symbol: Tuple[float, float, float, float],
                 module_size: float, seed: int = 0, texture=None, matrix=None) -> None:
        self.width = width
        self.height = height
        #: (x, y, w, h) of the symbol area inside the canvas
        self.symbol = symbol
        self.module_size = module_size
        self.seed = seed
        self.texture = texture
        self.matrix = matrix

    # normalised coordinates over the whole canvas
    def uv(self, x: int, y: int) -> Tuple[float, float]:
        return (x / max(self.width - 1, 1), y / max(self.height - 1, 1))

    def radius(self, x: int, y: int) -> float:
        cx, cy = self.width / 2.0, self.height / 2.0
        scale = min(self.width, self.height) / 2.0
        return math.hypot(x - cx, y - cy) / scale

    def noise(self, x: float, y: float, octaves: int = 1) -> float:
        return noise2(x, y, self.seed, octaves)

    def rand(self, x: int, y: int) -> float:
        return hash2(x, y, self.seed)

    def sample_texture(self, u: float, v: float) -> Color4:
        if self.texture is None:
            return (0, 0, 0, 0)
        return self.texture.sample(clamp(u) * (self.texture.width - 1),
                                   clamp(v) * (self.texture.height - 1))


# ------------------------------------------------------------------- base class
class Shader:
    """Base class for shaders."""

    name = "shader"
    kind = "pixel"

    def __init__(self, name: Optional[str] = None, **params: Any) -> None:
        if name:
            self.name = name
        self.params = params

    # -- raster ----------------------------------------------------------
    def apply(self, image, ctx: Context):
        """Apply to a :class:`~qrforge.image.Pixmap`, in place or returning one."""
        if self.kind == "pixel":
            return self._apply_pixel(image, ctx)
        if self.kind == "warp":
            return self._apply_warp(image, ctx)
        return self._apply_post(image, ctx)

    def pixel(self, x: int, y: int, color: Color, ctx: Context) -> Color:
        return color

    def warp(self, x: int, y: int, ctx: Context) -> Tuple[float, float]:
        return (float(x), float(y))

    def post(self, image, ctx: Context):
        return image

    def _apply_pixel(self, image, ctx: Context):
        data = image.data
        width = image.width
        fn = self.pixel
        for y in range(image.height):
            row = y * width * 4
            for x in range(width):
                i = row + x * 4
                out = fn(x, y, Color(data[i], data[i + 1], data[i + 2], data[i + 3]), ctx)
                data[i:i + 4] = bytes(out.rgba)
        return image

    def _apply_warp(self, image, ctx: Context):
        from .image import Pixmap
        src = image
        out = Pixmap(src.width, src.height, (0, 0, 0, 0))
        warp = self.warp
        for y in range(src.height):
            for x in range(src.width):
                sx, sy = warp(x, y, ctx)
                if 0 <= sx < src.width and 0 <= sy < src.height:
                    out.set(x, y, src.sample(sx, sy))
        return out

    def _apply_post(self, image, ctx: Context):
        return self.post(image, ctx)

    # -- vector ----------------------------------------------------------
    def svg_filter(self, uid: str, ctx: Context) -> Optional[str]:
        """Return SVG filter markup, or ``None`` if SVG cannot express it."""
        return None

    def svg_overlay(self, uid: str, ctx: Context) -> Optional[str]:
        """Return markup drawn on top of the symbol (scanlines, vignette...)."""
        return None

    def __repr__(self) -> str:
        args = ", ".join(f"{k}={v!r}" for k, v in self.params.items())
        return f"Shader({self.name}{', ' + args if args else ''})"


class FunctionShader(Shader):
    """Wraps a plain Python function into a shader."""

    def __init__(self, fn: Callable, kind: str = "pixel", name: Optional[str] = None,
                 **params: Any) -> None:
        super().__init__(name or getattr(fn, "__name__", "custom"), **params)
        self.fn = fn
        self.kind = kind

    def pixel(self, x, y, color, ctx):
        return self.fn(x, y, color, ctx)

    def warp(self, x, y, ctx):
        return self.fn(x, y, ctx)

    def post(self, image, ctx):
        return self.fn(image, ctx)


# ------------------------------------------------------------------ expression
_ALLOWED_CALLS = {
    "sin": math.sin, "cos": math.cos, "tan": math.tan, "sqrt": math.sqrt,
    "abs": abs, "min": min, "max": max, "pow": math.pow, "exp": math.exp,
    "log": math.log, "floor": math.floor, "ceil": math.ceil, "atan2": math.atan2,
    "hypot": math.hypot, "clamp": clamp, "mix": mix, "smoothstep": smoothstep,
    "noise": noise2, "rand": hash2, "pi": math.pi, "Color": Color.parse,
}


def expression(formula: str, name: str = "expression") -> Shader:
    """Build a shader from a formula string.

    The formula is evaluated per pixel with ``x``, ``y`` (pixel coordinates),
    ``u``, ``v`` (0..1 over the canvas), ``r`` (radius from the centre),
    ``theta`` (angle), ``c`` (the incoming :class:`~qrforge.color.Color`) and
    the usual maths helpers in scope.  Return a :class:`Color`.

    ::

        qr = qrforge.QR("hi").style(shaders=[
            qrforge.expression("Color((255*u, 128*v, 200*r))")])

    The string is compiled once with a restricted namespace (no builtins), but
    you should still only use formulas you trust.
    """
    code = compile(formula, "<qrforge expression>", "eval")
    for const in code.co_names:
        if not (const in _ALLOWED_CALLS or const in
                {"x", "y", "u", "v", "r", "theta", "c", "ctx", "self"}):
            raise StyleError(f"{const!r} is not available inside a shader expression")

    class ExpressionShader(Shader):
        kind = "pixel"

        def pixel(self, x, y, color, ctx):
            u, v = ctx.uv(x, y)
            r = ctx.radius(x, y)
            theta = math.atan2(y - ctx.height / 2, x - ctx.width / 2)
            env = dict(_ALLOWED_CALLS)
            env.update(x=x, y=y, u=u, v=v, r=r, theta=theta, c=color, ctx=ctx)
            value = eval(code, {"__builtins__": {}}, env)  # noqa: S307 - restricted
            return Color.parse(value)

    shader = ExpressionShader(name=name)
    shader.params = {"formula": formula}
    return shader


# ------------------------------------------------------------------ built-ins
class Grain(Shader):
    def __init__(self, amount: float = 0.12, mono: bool = True, scale: float = 1.0) -> None:
        super().__init__(amount=amount, mono=mono, scale=scale)
        self.amount, self.mono, self.scale = amount, mono, scale

    def pixel(self, x, y, color, ctx):
        if color.a == 0:
            return color
        if self.mono:
            n = (hash2(int(x / self.scale), int(y / self.scale), ctx.seed) - 0.5) * 255 * self.amount
            return Color(color.r + n, color.g + n, color.b + n, color.a)
        return Color(color.r + (hash2(x, y, ctx.seed) - 0.5) * 255 * self.amount,
                     color.g + (hash2(x, y, ctx.seed + 1) - 0.5) * 255 * self.amount,
                     color.b + (hash2(x, y, ctx.seed + 2) - 0.5) * 255 * self.amount,
                     color.a)

    def svg_filter(self, uid, ctx):
        frequency = 0.9 / max(self.scale, 0.01)
        kind = "saturate" if self.mono else "matrix"
        color_matrix = ('0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0.33 0.33 0.33 0 0 0 0 0 1 0'
                        if self.mono else '1 0 0 0 0 0 1 0 0 0 0 0 1 0 0 0 0 0 1 0')
        amount = min(self.amount * 2.0, 1.0)
        return (f'<filter id="{uid}" x="0%" y="0%" width="100%" height="100%">'
                f'<feTurbulence type="fractalNoise" baseFrequency="{frequency:.4f}" '
                f'numOctaves="2" seed="{ctx.seed % 100}" result="noise"/>'
                f'<feColorMatrix in="noise" type="{kind}" values="{color_matrix}" result="mono"/>'
                f'<feComponentTransfer in="mono" result="contrast">'
                f'<feFuncR type="linear" slope="2" intercept="-0.5"/>'
                f'<feFuncG type="linear" slope="2" intercept="-0.5"/>'
                f'<feFuncB type="linear" slope="2" intercept="-0.5"/></feComponentTransfer>'
                f'<feBlend in="SourceGraphic" in2="contrast" mode="overlay" result="blended"/>'
                f'<feComponentTransfer><feFuncA type="table" '
                f'tableValues="0 {1 - amount:.3f} 1"/></feComponentTransfer>'
                f'<feComposite in="blended" in2="SourceGraphic" operator="in"/>'
                f'</filter>')


class Vignette(Shader):
    def __init__(self, amount: float = 0.55, color: ColorLike = "#000000",
                 softness: float = 0.45) -> None:
        super().__init__(kind="overlay", amount=amount, color=color, softness=softness)
        self.amount = amount
        self.color = Color.parse(color)
        self.softness = softness

    def pixel(self, x, y, color, ctx):
        t = smoothstep(1.0 - self.softness, 1.0, ctx.radius(x, y) * 1.15) * self.amount
        base = color.mix(self.color, t)
        return Color(base.r, base.g, base.b, color.a)

    def svg_overlay(self, uid, ctx):
        cx, cy = ctx.width / 2, ctx.height / 2
        radius = min(ctx.width, ctx.height) / 2 * (1.0 + self.softness)
        return (f'<defs><radialGradient id="{uid}" gradientUnits="userSpaceOnUse" '
                f'cx="{cx}" cy="{cy}" r="{radius:.2f}">'
                f'<stop offset="{clamp(1 - self.softness):.3f}" stop-color="{self.color.hex()}" '
                f'stop-opacity="0"/>'
                f'<stop offset="1" stop-color="{self.color.hex()}" '
                f'stop-opacity="{self.amount:.3f}"/></radialGradient></defs>'
                f'<rect width="{ctx.width}" height="{ctx.height}" fill="url(#{uid})"/>')


class Duotone(Shader):
    """Map luminance onto two colours."""

    def __init__(self, shadow: ColorLike = "#12002e", highlight: ColorLike = "#ffe6a7",
                 amount: float = 1.0) -> None:
        super().__init__(shadow=shadow, highlight=highlight, amount=amount)
        self.shadow = Color.parse(shadow)
        self.highlight = Color.parse(highlight)
        self.amount = amount

    def pixel(self, x, y, color, ctx):
        if color.a == 0:
            return color
        target = self.shadow.mix(self.highlight, color.luminance)
        out = color.mix(target, self.amount)
        return Color(out.r, out.g, out.b, color.a)

    def svg_filter(self, uid, ctx):
        steps = 9
        tables = []
        for channel, index in (("R", 0), ("G", 1), ("B", 2)):
            values = " ".join(
                f"{(self.shadow.mix(self.highlight, t).rgba[index] / 255):.4f}"
                for t in (i / (steps - 1) for i in range(steps)))
            tables.append(f'<feFunc{channel} type="table" tableValues="{values}"/>')
        return (f'<filter id="{uid}" color-interpolation-filters="sRGB">'
                f'<feColorMatrix type="matrix" values="0.2126 0.7152 0.0722 0 0 '
                f'0.2126 0.7152 0.0722 0 0 0.2126 0.7152 0.0722 0 0 0 0 0 1 0" result="lum"/>'
                f'<feComponentTransfer in="lum">{"".join(tables)}</feComponentTransfer>'
                f'</filter>')


class ComponentTransfer(Shader):
    """Posterise / sepia / greyscale via a colour matrix or transfer table."""

    def __init__(self, name: str, matrix: Optional[List[float]] = None,
                 levels: Optional[int] = None, amount: float = 1.0) -> None:
        super().__init__(name=name, levels=levels, amount=amount)
        self.matrix = matrix
        self.levels = levels
        self.amount = amount

    def pixel(self, x, y, color, ctx):
        if color.a == 0:
            return color
        if self.matrix:
            r, g, b = color.r / 255, color.g / 255, color.b / 255
            m = self.matrix
            out = Color(min(1, max(0, m[0] * r + m[1] * g + m[2] * b + m[4])) * 255,
                        min(1, max(0, m[5] * r + m[6] * g + m[7] * b + m[9])) * 255,
                        min(1, max(0, m[10] * r + m[11] * g + m[12] * b + m[14])) * 255,
                        color.a)
        else:
            levels = max(2, self.levels or 4)
            def quant(v):  # noqa: E306
                return int(round(round(v / 255 * (levels - 1)) / (levels - 1) * 255))
            out = Color(quant(color.r), quant(color.g), quant(color.b), color.a)
        if self.amount < 1.0:
            out = color.mix(out, self.amount)
        return Color(out.r, out.g, out.b, color.a)

    def svg_filter(self, uid, ctx):
        if self.matrix:
            values = " ".join(f"{v:g}" for v in self.matrix)
            return (f'<filter id="{uid}" color-interpolation-filters="sRGB">'
                    f'<feColorMatrix type="matrix" values="{values}"/></filter>')
        levels = max(2, self.levels or 4)
        step = 1.0 / (levels - 1)
        table = " ".join(f"{min(1.0, round(i * step * (levels - 1)) / (levels - 1)):.4f}"
                         for i in range(levels + 1))
        return (f'<filter id="{uid}" color-interpolation-filters="sRGB">'
                f'<feComponentTransfer>'
                f'<feFuncR type="discrete" tableValues="{table}"/>'
                f'<feFuncG type="discrete" tableValues="{table}"/>'
                f'<feFuncB type="discrete" tableValues="{table}"/>'
                f'</feComponentTransfer></filter>')


class Wave(Shader):
    kind = "warp"

    def __init__(self, amplitude: float = 6.0, wavelength: float = 48.0,
                 angle: float = 0.0) -> None:
        super().__init__(amplitude=amplitude, wavelength=wavelength, angle=angle)
        self.amplitude, self.wavelength, self.angle = amplitude, wavelength, angle

    def warp(self, x, y, ctx):
        rad = math.radians(self.angle)
        along = x * math.cos(rad) + y * math.sin(rad)
        offset = math.sin(2 * math.pi * along / max(self.wavelength, 1e-6)) * self.amplitude
        return (x - offset * math.sin(rad), y + offset * math.cos(rad))

    def svg_filter(self, uid, ctx):
        scale = max(self.amplitude * 2, 1)
        return (f'<filter id="{uid}" x="-10%" y="-10%" width="120%" height="120%">'
                f'<feTurbulence type="turbulence" baseFrequency="{8.0 / max(self.wavelength, 1):.4f}" '
                f'numOctaves="1" seed="{ctx.seed % 100}" result="warp"/>'
                f'<feDisplacementMap in="SourceGraphic" in2="warp" scale="{scale:.2f}" '
                f'xChannelSelector="R" yChannelSelector="G"/></filter>')


class Twist(Shader):
    kind = "warp"

    def __init__(self, strength: float = 1.2, radius: float = 1.0) -> None:
        super().__init__(strength=strength, radius=radius)
        self.strength, self.radius = strength, radius

    def warp(self, x, y, ctx):
        cx, cy = ctx.width / 2, ctx.height / 2
        dx, dy = x - cx, y - cy
        scale = min(ctx.width, ctx.height) / 2 * self.radius
        d = math.hypot(dx, dy) / max(scale, 1e-6)
        angle = self.strength * (1 - min(d, 1.0)) ** 2
        cos_a, sin_a = math.cos(angle), math.sin(angle)
        return (cx + dx * cos_a - dy * sin_a, cy + dx * sin_a + dy * cos_a)


class Bulge(Shader):
    kind = "warp"

    def __init__(self, amount: float = 0.35) -> None:
        super().__init__(amount=amount)
        self.amount = amount

    def warp(self, x, y, ctx):
        cx, cy = ctx.width / 2, ctx.height / 2
        scale = min(ctx.width, ctx.height) / 2
        dx, dy = (x - cx) / scale, (y - cy) / scale
        d = math.hypot(dx, dy)
        if d == 0 or d > 1.4:
            return (float(x), float(y))
        factor = 1.0 + self.amount * (1 - d) ** 2
        return (cx + dx / factor * scale, cy + dy / factor * scale)


class Glitch(Shader):
    kind = "warp"

    def __init__(self, offset: float = 0.3, band: int = 1, seed: int = 1,
                 probability: float = 0.45) -> None:
        super().__init__(offset=offset, band=band, seed=seed, probability=probability)
        #: ``offset`` is a *fraction of one module* so the grid never tears enough
        #: to become unscannable; ``band`` is the band height in modules.
        self.offset, self.band = offset, max(1, int(band))
        self.gseed, self.probability = seed, probability

    def warp(self, x, y, ctx):
        ms = max(ctx.module_size, 1.0)
        origin = ctx.symbol[1]
        index = int((y - origin) // (self.band * ms))
        if hash2(index, self.gseed, 11) < self.probability:
            shift = (hash2(index, self.gseed, 7) - 0.5) * 2.0 * self.offset * ms
            return (x + shift, float(y))
        return (float(x), float(y))


class Chromatic(Shader):
    kind = "post"

    def __init__(self, offset: float = 2.5, angle: float = 0.0) -> None:
        super().__init__(offset=offset, angle=angle)
        self.offset, self.angle = offset, angle

    def post(self, image, ctx):
        from .image import Pixmap
        out = Pixmap(image.width, image.height, (0, 0, 0, 0))
        dx = math.cos(math.radians(self.angle)) * self.offset
        dy = math.sin(math.radians(self.angle)) * self.offset
        for y in range(image.height):
            for x in range(image.width):
                base = image.get(x, y)
                if base[3] == 0:
                    out.set(x, y, base)
                    continue
                red = image.sample(x + dx, y + dy)
                blue = image.sample(x - dx, y - dy)
                out.set(x, y, (red[0], base[1], blue[2], base[3]))
        return out

    def svg_filter(self, uid, ctx):
        dx = math.cos(math.radians(self.angle)) * self.offset
        dy = math.sin(math.radians(self.angle)) * self.offset
        return (f'<filter id="{uid}" x="-10%" y="-10%" width="120%" height="120%" '
                f'color-interpolation-filters="sRGB">'
                f'<feColorMatrix in="SourceGraphic" type="matrix" '
                f'values="1 0 0 0 0  0 0 0 0 0  0 0 0 0 0  0 0 0 1 0" result="r0"/>'
                f'<feOffset in="r0" dx="{dx:.2f}" dy="{dy:.2f}" result="r"/>'
                f'<feColorMatrix in="SourceGraphic" type="matrix" '
                f'values="0 0 0 0 0  0 1 0 0 0  0 0 0 0 0  0 0 0 1 0" result="g"/>'
                f'<feColorMatrix in="SourceGraphic" type="matrix" '
                f'values="0 0 0 0 0  0 0 0 0 0  0 0 1 0 0  0 0 0 1 0" result="b0"/>'
                f'<feOffset in="b0" dx="{-dx:.2f}" dy="{-dy:.2f}" result="b"/>'
                f'<feBlend in="r" in2="g" mode="screen" result="rg"/>'
                f'<feBlend in="rg" in2="b" mode="screen"/></filter>')


class Glow(Shader):
    kind = "post"

    def __init__(self, radius: float = 3.0, amount: float = 0.9,
                 color: ColorLike = None) -> None:
        super().__init__(radius=radius, amount=amount, color=color)
        self.radius, self.amount = radius, amount
        self.color = Color.parse(color) if color is not None else None

    def post(self, image, ctx):
        from .image import Pixmap
        blur = _box_blur(image, int(max(self.radius, 1)))
        out = image.copy()
        amount = self.amount
        for y in range(image.height):
            row = y * image.width * 4
            for x in range(image.width):
                i = row + x * 4
                b = blur.get(x, y)
                alpha = (b[3] / 255.0) * amount
                if alpha <= 0:
                    continue
                glow = self.color.rgba if self.color else (b[0], b[1], b[2], 255)
                dst = (image.data[i], image.data[i + 1], image.data[i + 2], image.data[i + 3])
                src = (glow[0], glow[1], glow[2], int(alpha * 255))
                out.data[i:i + 4] = bytes(_compose(dst, src, alpha))
        return out

    def svg_filter(self, uid, ctx):
        flood = (f'<feFlood flood-color="{self.color.hex()}" result="tint"/>'
                 f'<feComposite in="tint" in2="blur" operator="in" result="colored"/>'
                 if self.color else "")
        node = "colored" if self.color else "blur"
        return (f'<filter id="{uid}" x="-20%" y="-20%" width="140%" height="140%">'
                f'<feGaussianBlur in="SourceGraphic" stdDeviation="{self.radius:.2f}" '
                f'result="blur"/>{flood}'
                f'<feComponentTransfer in="{node}" result="boost">'
                f'<feFuncA type="linear" slope="{self.amount:.2f}"/></feComponentTransfer>'
                f'<feMerge><feMergeNode in="boost"/><feMergeNode in="SourceGraphic"/></feMerge>'
                f'</filter>')


class Outline(Shader):
    """Draw a stroke around every dark module."""

    def __init__(self, color: ColorLike = "#ffffff", width: float = 1.5) -> None:
        super().__init__(color=color, width=width)
        self.color = Color.parse(color)
        self.width = width

    def post(self, image, ctx):
        from .image import Pixmap
        w = max(1, int(round(self.width)))
        alpha = image.data
        width, height = image.width, image.height
        mask = bytearray(width * height)
        for y in range(height):
            for x in range(width):
                if alpha[(y * width + x) * 4 + 3] == 0:
                    continue
                edge = False
                for dy in range(-w, w + 1):
                    for dx in range(-w, w + 1):
                        nx, ny = x + dx, y + dy
                        if 0 <= nx < width and 0 <= ny < height and \
                                alpha[(ny * width + nx) * 4 + 3] == 0:
                            edge = True
                            break
                    if edge:
                        break
                if edge:
                    mask[y * width + x] = 1
        out = image.copy()
        rgba = self.color.rgba
        for i, flag in enumerate(mask):
            if flag:
                out.data[i * 4:i * 4 + 4] = bytes(rgba)
        return out

    def svg_filter(self, uid, ctx):
        return (f'<filter id="{uid}" x="-20%" y="-20%" width="140%" height="140%">'
                f'<feMorphology in="SourceAlpha" operator="dilate" radius="{self.width:.2f}" '
                f'result="fat"/>'
                f'<feFlood flood-color="{self.color.hex()}" '
                f'flood-opacity="{self.color.alpha:.3f}" result="tint"/>'
                f'<feComposite in="tint" in2="fat" operator="in" result="ring"/>'
                f'<feComposite in="ring" in2="SourceAlpha" operator="out" result="stroke"/>'
                f'<feMerge><feMergeNode in="stroke"/><feMergeNode in="SourceGraphic"/></feMerge>'
                f'</filter>')


class Scanlines(Shader):
    kind = "overlay"

    def __init__(self, gap: int = 4, amount: float = 0.28, color: ColorLike = "#000000") -> None:
        super().__init__(kind="overlay", gap=gap, amount=amount, color=color)
        self.gap, self.amount = max(2, int(gap)), amount
        self.color = Color.parse(color)

    def pixel(self, x, y, color, ctx):
        if y % self.gap < self.gap // 2:
            base = color.mix(self.color, self.amount)
            return Color(base.r, base.g, base.b, color.a)
        return color

    def svg_overlay(self, uid, ctx):
        return (f'<defs><pattern id="{uid}" patternUnits="userSpaceOnUse" width="{self.gap}" '
                f'height="{self.gap}"><rect width="{self.gap}" height="{self.gap // 2}" '
                f'fill="{self.color.hex()}" fill-opacity="{self.amount:.3f}"/></pattern></defs>'
                f'<rect width="{ctx.width}" height="{ctx.height}" fill="url(#{uid})"/>')


class Halftone(Shader):
    kind = "post"

    def __init__(self, cell: float = 0, color: ColorLike = None,
                 background: ColorLike = None) -> None:
        super().__init__(cell=cell, color=color, background=background)
        #: ``cell`` 0 = snap to the module grid (keeps the code scannable).
        self.cell = float(cell)
        self.color = Color.parse(color) if color else None
        self.background = Color.parse(background) if background else None

    def post(self, image, ctx):
        from .image import Pixmap
        ox, oy = ctx.symbol[0], ctx.symbol[1]
        cell = self.cell if self.cell > 0 else max(ctx.module_size, 2.0)
        out = Pixmap(image.width, image.height,
                     self.background.rgba if self.background else (0, 0, 0, 0))
        x0 = int(math.floor(ox))
        y0 = int(math.floor(oy))
        for by in range(y0, image.height, int(round(cell))):
            for bx in range(x0, image.width, int(round(cell))):
                total, count, cr, cg, cb = 0.0, 0, 0.0, 0.0, 0.0
                for y in range(by, min(by + int(cell), image.height)):
                    for x in range(bx, min(bx + int(cell), image.width)):
                        px = image.get(x, y)
                        if px[3] == 0:
                            continue
                        lum = (px[0] * 0.299 + px[1] * 0.587 + px[2] * 0.114) / 255
                        total += 1 - lum
                        count += 1
                        cr += px[0]
                        cg += px[1]
                        cb += px[2]
                if count == 0:
                    continue
                coverage = total / count
                # keep dark modules solid so they stay readable
                radius = math.sqrt(coverage) * (cell / 2.0) * (1.15 if coverage > 0.5 else 1.0)
                if radius <= 0.1:
                    continue
                base = (int(cr / count), int(cg / count), int(cb / count), 255)
                if self.color:
                    base = self.color.rgba
                cx, cy = bx + cell / 2.0, by + cell / 2.0
                for y in range(max(0, int(by - 1)), min(image.height, int(by + cell) + 1)):
                    for x in range(max(0, int(bx - 1)), min(image.width, int(bx + cell) + 1)):
                        d = math.hypot(x + 0.5 - cx, y + 0.5 - cy)
                        alpha = clamp(radius - d + 0.5)
                        if alpha > 0:
                            out.set(x, y, _compose(out.get(x, y), base, alpha))
        return out


def _compose(dst, src, alpha):
    if alpha >= 1.0:
        return (src[0], src[1], src[2], src[3])
    da = dst[3] / 255.0
    out_a = alpha + da * (1 - alpha)
    if out_a <= 0:
        return (0, 0, 0, 0)
    return tuple(int(round((src[i] * alpha + dst[i] * da * (1 - alpha)) / out_a))
                 for i in range(3)) + (int(round(out_a * 255)),)


def _box_blur(image, radius: int):
    from .image import Pixmap
    if radius <= 0:
        return image.copy()
    w, h = image.width, image.height
    tmp = Pixmap(w, h)
    out = Pixmap(w, h)
    span = radius * 2 + 1
    for y in range(h):
        row = y * w * 4
        for x in range(w):
            sums = [0.0, 0.0, 0.0, 0.0]
            for dx in range(-radius, radius + 1):
                nx = min(max(x + dx, 0), w - 1)
                i = row + nx * 4
                for c in range(4):
                    sums[c] += image.data[i + c]
            i = row + x * 4
            for c in range(4):
                tmp.data[i + c] = int(sums[c] / span)
    for y in range(h):
        for x in range(w):
            sums = [0.0, 0.0, 0.0, 0.0]
            for dy in range(-radius, radius + 1):
                ny = min(max(y + dy, 0), h - 1)
                i = (ny * w + x) * 4
                for c in range(4):
                    sums[c] += tmp.data[i + c]
            i = (y * w + x) * 4
            for c in range(4):
                out.data[i + c] = int(sums[c] / span)
    return out


# ------------------------------------------------------------------- registry
def _factory(kind, **defaults):
    def make(**params):
        merged = dict(defaults)
        merged.update(params)
        return kind(**merged)
    return make


FACTORIES: Dict[str, Callable[..., Shader]] = {
    "grain": _factory(Grain),
    "noise": _factory(Grain),
    "vignette": _factory(Vignette),
    "duotone": _factory(Duotone),
    "posterize": lambda levels=4, amount=1.0: ComponentTransfer(
        "posterize", levels=levels, amount=amount),
    "sepia": lambda amount=1.0: ComponentTransfer(
        "sepia", matrix=[0.393, 0.769, 0.189, 0, 0,
                         0.349, 0.686, 0.168, 0, 0,
                         0.272, 0.534, 0.131, 0, 0,
                         0, 0, 0, 1, 0], amount=amount),
    "greyscale": lambda amount=1.0: ComponentTransfer(
        "greyscale", matrix=[0.2126, 0.7152, 0.0722, 0, 0,
                             0.2126, 0.7152, 0.0722, 0, 0,
                             0.2126, 0.7152, 0.0722, 0, 0,
                             0, 0, 0, 1, 0], amount=amount),
    "invert": lambda: ComponentTransfer(
        "invert", matrix=[-1, 0, 0, 0, 1, 0, -1, 0, 0, 1, 0, 0, -1, 0, 1, 0, 0, 0, 1, 0]),
    "wave": _factory(Wave),
    "twist": _factory(Twist),
    "swirl": _factory(Twist),
    "bulge": _factory(Bulge),
    "glitch": _factory(Glitch),
    "chromatic": _factory(Chromatic),
    "glow": _factory(Glow),
    "bloom": _factory(Glow),
    "outline": _factory(Outline),
    "stroke": _factory(Outline),
    "scanlines": _factory(Scanlines),
    "halftone": _factory(Halftone),
}


def build(spec: Any) -> Shader:
    """Coerce a shader spec into a :class:`Shader`.

    Accepts a :class:`Shader`, a registered name (``"grain"``), a
    ``(name, params)`` pair, a ``"name:k=v"`` string, or a callable.
    """
    if isinstance(spec, Shader):
        return spec
    if callable(spec) and not isinstance(spec, type):
        return FunctionShader(spec)
    if isinstance(spec, (tuple, list)) and len(spec) == 2 and isinstance(spec[0], str):
        name, params = spec
        return build(name)(**params) if isinstance(params, dict) else build(f"{name}:{params}")
    if isinstance(spec, str):
        text = spec.strip()
        if text in FACTORIES:
            return FACTORIES[text]()
        if ":" in text or "(" in text:
            name, _, args = text.partition(":")
            name = name.strip()
            if name not in FACTORIES:
                raise StyleError(f"unknown shader {name!r}; available: {', '.join(sorted(FACTORIES))}")
            params = {}
            if args.strip():
                for pair in args.split(","):
                    key, _, value = pair.partition("=")
                    params[key.strip()] = _coerce(value.strip())
            return FACTORIES[name](**params)
        raise StyleError(f"unknown shader {spec!r}; available: {', '.join(sorted(FACTORIES))}")
    raise StyleError(f"cannot build a shader from {spec!r}")


def _coerce(value: str):
    if value.lower() in ("true", "false"):
        return value.lower() == "true"
    if value.lower() in ("none", "null"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        pass
    return value.strip("'\"")


def shader(fn: Optional[Callable] = None, *, kind: str = "pixel", name: Optional[str] = None):
    """Decorator that turns a function into a reusable shader.

    ::

        @qrforge.shader
        def heat(x, y, color, ctx):
            return color.mix("#ff4400", ctx.uv(x, y)[1])

        qrforge.save("hi", "out.png", shaders=[heat])
    """
    def wrap(f):
        made = FunctionShader(f, kind=kind, name=name)
        FACTORIES[name or f.__name__] = lambda **kw: FunctionShader(f, kind=kind,
                                                                    name=name or f.__name__)
        return made
    if fn is None:
        return wrap
    return wrap(fn)


def names() -> List[str]:
    return sorted(FACTORIES)
