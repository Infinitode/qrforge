"""Raster rendering: pure-Python, anti-aliased, no dependencies.

Shapes are rasterised from their signed distance field, which gives smooth
edges at any scale without an image library.
"""

from __future__ import annotations

import math
import random as _random
from typing import Any, Callable, Dict, List, Optional, Tuple

from .. import shapes as shape_lib
from ..color import Color, blend
from ..gradient import ColorSource, resolve as resolve_color
from ..image import Pixmap
from ..matrix import (ROLE_ALIGNMENT, ROLE_DARK, ROLE_FINDER, ROLE_FORMAT, ROLE_SEPARATOR,
                      ROLE_TIMING, ROLE_VERSION, QRMatrix)
from ..shaders import Context, build as build_shader
from ..style import Style

Color4 = Tuple[int, int, int, int]
FUNCTION_ROLES = (ROLE_TIMING, ROLE_FORMAT, ROLE_VERSION, ROLE_ALIGNMENT, ROLE_DARK)


def render(matrix: QRMatrix, style: Style) -> Pixmap:
    renderer = RasterRenderer(matrix, style)
    return renderer.render()


class RasterRenderer:
    def __init__(self, matrix: QRMatrix, style: Style) -> None:
        self.matrix = matrix
        self.style = style
        self.rng = _random.Random(style.seed_or(0))
        self.scale = max(1, int(style.scale))
        self.margin = style.quiet_zone + style.padding
        self.modules = matrix.size
        self.symbol_px = self.modules * self.scale
        self.size = int(math.ceil((self.modules + 2 * self.margin) * self.scale))
        self.offset = int(round(self.margin * self.scale))
        self.tiles: Dict[Tuple, List[List[float]]] = {}
        self.fg: ColorSource = resolve_color(style.fg)
        self.bg: Optional[ColorSource] = None if style.bg is None else resolve_color(style.bg)
        self.eye_fg: ColorSource = resolve_color(style.eye_fg) if style.eye_fg is not None else self.fg
        self.function_fg: ColorSource = (resolve_color(style.function_fg)
                                         if style.function_fg is not None else self.fg)
        self.texture: Optional[Pixmap] = None
        if style.texture is not None:
            self.texture = Pixmap.open(style.texture)
        self._per_module_shape: Optional[List[shape_lib.Shape]] = None

    # ------------------------------------------------------------------- entry
    def render(self) -> Pixmap:
        style = self.style
        symbol = Pixmap(self.size, self.size, (0, 0, 0, 0))
        self._draw_modules(symbol)
        self._draw_eyes(symbol)
        self._draw_logo(symbol)

        canvas = self._background()
        if style.shadow:
            self._draw_shadow(canvas, symbol)
        canvas.blit(symbol, 0, 0)

        ctx = Context(self.size, self.size,
                      (self.offset, self.offset, self.symbol_px, self.symbol_px),
                      self.scale, style.seed_or(0), self.texture, self.matrix)
        for spec in style.shaders or ():
            shader = build_shader(spec)
            result = shader.apply(canvas, ctx)
            if result is not canvas:
                canvas = result
        if style.bg_radius > 0:
            _rounded_mask(canvas, style.bg_radius * canvas.width)
        return canvas

    # -------------------------------------------------------------- background
    def _background(self) -> Pixmap:
        style = self.style
        canvas = Pixmap(self.size, self.size, (0, 0, 0, 0))
        if style.bg_image is not None:
            image = Pixmap.open(style.bg_image)
            canvas.paste_cover(image, style.bg_opacity)
        if self.bg is not None:
            data = canvas.data
            width = self.size
            for y in range(self.size):
                v = y / max(self.size - 1, 1)
                row = y * width * 4
                for x in range(width):
                    color = self.bg.at(x / max(width - 1, 1), v)
                    if color.a == 0:
                        continue
                    index = row + x * 4
                    base = (data[index], data[index + 1], data[index + 2], data[index + 3])
                    data[index:index + 4] = bytes(blend(base, color.rgba, style.bg_opacity))
        return canvas

    # ----------------------------------------------------------------- modules
    def _module_color(self, x: int, y: int, source: ColorSource) -> Color4:
        style = self.style
        u = (x - self.offset) / max(self.symbol_px, 1)
        v = (y - self.offset) / max(self.symbol_px, 1)
        color = source.at(u, v)
        if self.texture is not None:
            tex = self.texture
            if style.texture_mode == "contain":
                ratio = min(self.symbol_px / tex.width, self.symbol_px / tex.height)
                tw, th = tex.width * ratio, tex.height * ratio
                tx = (u * self.symbol_px - (self.symbol_px - tw) / 2) / max(tw, 1e-6)
                ty = (v * self.symbol_px - (self.symbol_px - th) / 2) / max(th, 1e-6)
            else:
                tx, ty = u, v
            sample = tex.sample(tx * (tex.width - 1), ty * (tex.height - 1))
            if 0 <= tx <= 1 and 0 <= ty <= 1:
                color = _mix_texture(color, sample, style)
        return color.rgba if isinstance(color, Color) else tuple(color)

    def _draw_modules(self, image: Pixmap) -> None:
        style = self.style
        module_shape = shape_lib.get(style.module_shape) if not _is_random(style.module_shape) \
            else None
        function_shape = (shape_lib.get(style.function_shape) if style.function_shape is not None
                          else None)
        if _is_random(style.module_shape):
            choices = [shape_lib.get(s) for s in style.module_shape]
            self._per_module_shape = choices
        for row, col, dark, role in self.matrix.iter_modules():
            if not dark or role == ROLE_FINDER or role == ROLE_SEPARATOR:
                continue
            if role in FUNCTION_ROLES and function_shape is not None:
                shape = function_shape
            elif self._per_module_shape is not None:
                shape = self._per_module_shape[
                    self.rng.randrange(len(self._per_module_shape))]
            else:
                shape = module_shape
            source = self.function_fg if role in FUNCTION_ROLES else self.fg
            self._stamp(image, shape, self.offset + col * self.scale,
                        self.offset + row * self.scale, self.scale, style.module_scale,
                        style.module_rotation, style.module_radius, source, row, col)

    def _draw_eyes(self, image: Pixmap) -> None:
        style = self.style
        size = self.matrix.size
        shape = shape_lib.get(style.eye_shape) if style.eye_shape is not None \
            else shape_lib.get(style.module_shape if not _is_random(style.module_shape)
                               else style.module_shape[0])
        dot_shape = shape_lib.get(style.eye_dot_shape) if style.eye_dot_shape is not None \
            else shape
        cell = self.scale
        span = 7 * cell
        for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
            cx = self.offset + (left + 3.5) * cell
            cy = self.offset + (top + 3.5) * cell
            self._stamp_sdf(image,
                            lambda x, y, r=0.0, s=shape, dot=dot_shape: _eye_sdf(
                                x, y, s, dot, style.eye_ring, style.eye_dot_scale),
                            cx, cy, span, style.eye_scale, self.eye_fg)

    # --------------------------------------------------------------- primitives
    def _stamp(self, image: Pixmap, shape: shape_lib.Shape, left: float, top: float,
               cell: int, scale_factor: float, rotation: float, radius: Optional[float],
               source: ColorSource, row: int, col: int) -> None:
        style = self.style
        jitter = style.module_jitter
        if jitter:
            scale_factor *= 1.0 + (self.rng.random() - 0.5) * jitter * 0.6
            rotation += (self.rng.random() - 0.5) * jitter * 90.0
        scale_factor = max(0.05, scale_factor - style.module_gap)
        radius = (radius if radius is not None else 0.22) if shape.name in ("rounded",) else (radius or 0.0)
        tile = self._tile(shape, cell, scale_factor, rotation, radius)
        self._blit_tile(image, tile, left, top, cell, source)

    def _stamp_sdf(self, image: Pixmap, sdf: Callable[..., float], cx: float, cy: float,
                   span: float, scale_factor: float, source: ColorSource) -> None:
        half = span / 2.0 * scale_factor
        x0, y0 = int(math.floor(cx - half)), int(math.floor(cy - half))
        x1, y1 = int(math.ceil(cx + half)) + 1, int(math.ceil(cy + half)) + 1
        data = image.data
        width, height = image.width, image.height
        solid = source.is_solid and self.texture is None
        color_solid = source.color.rgba if solid else None
        for y in range(max(0, y0), min(height, y1)):
            row = y * width * 4
            my = (y + 0.5 - cy) / span
            for x in range(max(0, x0), min(width, x1)):
                mx = (x + 0.5 - cx) / span
                d = sdf(mx, my) * span
                coverage = 0.5 - d
                if coverage <= 0:
                    continue
                if coverage > 1:
                    coverage = 1.0
                color = color_solid if solid else self._module_color(x, y, source)
                index = row + x * 4
                base = (data[index], data[index + 1], data[index + 2], data[index + 3])
                data[index:index + 4] = bytes(blend(base, color, coverage))

    def _tile(self, shape: shape_lib.Shape, cell: int, scale_factor: float,
              rotation: float, radius: float) -> List[List[float]]:
        key = (shape.name, cell, round(scale_factor, 4), round(rotation, 2), round(radius, 4),
               self.style.supersample)
        cached = self.tiles.get(key)
        if cached is not None:
            return cached
        super_n = max(1, int(self.style.supersample))
        size = int(math.ceil(cell))
        half = size / 2.0
        cos_a, sin_a = math.cos(math.radians(-rotation)), math.sin(math.radians(-rotation))
        sdf = shape.distance
        grad = shape.gradient_scale
        tile: List[List[float]] = []
        for py in range(size):
            row_out: List[float] = []
            for px in range(size):
                total = 0.0
                for sy in range(super_n):
                    yy = (py + (sy + 0.5) / super_n - half) / cell
                    for sx in range(super_n):
                        xx = (px + (sx + 0.5) / super_n - half) / cell
                        rx = xx * cos_a - yy * sin_a
                        ry = xx * sin_a + yy * cos_a
                        d = sdf(rx / scale_factor, ry / scale_factor, radius) * scale_factor
                        total += 0.5 - d * cell * grad
                row_out.append(max(0.0, min(1.0, total / (super_n * super_n))))
            tile.append(row_out)
        self.tiles[key] = tile
        return tile

    def _blit_tile(self, image: Pixmap, tile: List[List[float]], left: float, top: float,
                   cell: int, source: ColorSource) -> None:
        x0, y0 = int(math.floor(left)), int(math.floor(top))
        data = image.data
        width, height = image.width, image.height
        solid = source.is_solid and self.texture is None
        color_solid = source.color.rgba if solid else None
        for ty, row in enumerate(tile):
            y = y0 + ty
            if not 0 <= y < height:
                continue
            base_index = y * width * 4
            for tx, coverage in enumerate(row):
                if coverage <= 0:
                    continue
                x = x0 + tx
                if not 0 <= x < width:
                    continue
                color = color_solid if solid else self._module_color(x, y, source)
                index = base_index + x * 4
                if coverage >= 0.999 and color[3] == 255:
                    data[index:index + 4] = bytes(color)
                    continue
                base = (data[index], data[index + 1], data[index + 2], data[index + 3])
                data[index:index + 4] = bytes(blend(base, color, coverage))

    # -------------------------------------------------------------------- logo
    def _logo_coverage(self, dx: float, dy: float, half: float, radius: float) -> float:
        shape = self.style.logo_shape
        if shape == "circle":
            d = shape_lib.sd_circle(dx, dy, half)
        elif shape == "rounded":
            d = shape_lib.sd_round_box(dx, dy, half, half, min(radius, half))
        else:
            d = shape_lib.sd_box(dx, dy, half, half)
        return max(0.0, min(1.0, 0.5 - d))

    def _draw_logo(self, image: Pixmap) -> None:
        style = self.style
        if style.logo is None:
            return
        logo = Pixmap.open(style.logo)
        size_px = int(round(style.logo_size * self.symbol_px))
        if size_px < 1:
            return
        logo = logo.resized(size_px, size_px, "contain")
        if style.logo_rotation:
            logo = logo.rotated(style.logo_rotation)
        position = style.logo_position
        fx, fy = (0.5, 0.5) if position == "center" else position
        cx = self.offset + fx * self.symbol_px
        cy = self.offset + fy * self.symbol_px
        pad = style.logo_padding * self.scale
        box = size_px + 2 * pad
        radius = style.logo_radius * self.scale
        left, top = int(round(cx - box / 2)), int(round(cy - box / 2))

        def coverage_at(x: float, y: float, half: float) -> float:
            return self._logo_coverage(x - cx, y - cy, half, radius)

        if style.logo_stroke is not None:
            stroke_color, stroke_w = style.logo_stroke
            stroke_rgba = Color.parse(stroke_color).rgba
            sw = stroke_w * self.scale
            ext = int(sw) + 2
            for y in range(max(0, top - ext), min(self.size, top + int(box) + ext)):
                for x in range(max(0, left - ext), min(self.size, left + int(box) + ext)):
                    outer = coverage_at(x + 0.5, y + 0.5, box / 2 + sw)
                    inner = coverage_at(x + 0.5, y + 0.5, box / 2)
                    cov = max(0.0, min(outer, 1.0 - inner))
                    if cov <= 0:
                        continue
                    index = (y * self.size + x) * 4
                    base = tuple(image.data[index:index + 4])
                    image.data[index:index + 4] = bytes(blend(base, stroke_rgba, cov))

        if style.logo_bg is not None:
            color = Color.parse(style.logo_bg).rgba
            for y in range(max(0, top), min(self.size, top + int(box))):
                for x in range(max(0, left), min(self.size, left + int(box))):
                    coverage = coverage_at(x + 0.5, y + 0.5, box / 2)
                    if coverage <= 0:
                        continue
                    index = (y * self.size + x) * 4
                    base = tuple(image.data[index:index + 4])
                    image.data[index:index + 4] = bytes(blend(base, color, coverage))
        else:  # punch a transparent hole so the logo never touches modules
            for y in range(max(0, top), min(self.size, top + int(box))):
                for x in range(max(0, left), min(self.size, left + int(box))):
                    if coverage_at(x + 0.5, y + 0.5, box / 2) > 0:
                        image.data[(y * self.size + x) * 4 + 3] = 0

        # blit the (possibly rotated) logo, clipped to its shape and faded
        lx = cx - logo.width / 2.0
        ty = cy - logo.height / 2.0
        half_logo = size_px / 2.0

        def mask(col: int, row: int) -> float:
            return coverage_at(lx + col + 0.5, ty + row + 0.5, half_logo + 0.5)

        image.blit(logo, int(round(lx)), int(round(ty)), style.logo_opacity, mask)

    # ------------------------------------------------------------------ shadow
    def _draw_shadow(self, canvas: Pixmap, symbol: Pixmap) -> None:
        from ..shaders import _box_blur
        spec = dict(self.style.shadow or {})
        color = Color.parse(spec.get("color", "#000000")).rgba
        dx = int(spec.get("dx", 0))
        dy = int(spec.get("dy", 4))
        blur = int(spec.get("blur", 4))
        opacity = float(spec.get("opacity", 0.35))
        layer = Pixmap(symbol.width, symbol.height, (0, 0, 0, 0))
        for i in range(0, len(symbol.data), 4):
            if symbol.data[i + 3]:
                layer.data[i:i + 4] = bytes((color[0], color[1], color[2], symbol.data[i + 3]))
        layer = _box_blur(layer, max(blur, 1))
        canvas.blit(layer, dx, dy, opacity)


# --------------------------------------------------------------------- helpers
def _is_random(spec: Any) -> bool:
    return isinstance(spec, (list, tuple)) and len(spec) > 0


def _scaled_sdf(shape: shape_lib.Shape, x: float, y: float, factor: float) -> float:
    """SDF of ``shape`` drawn so that it spans ``factor`` of an eye's width.

    Coordinates are eye-normalised (the eye spans -0.5..0.5) while the shape
    SDFs work in module units, hence the factor of 7.
    """
    s = factor * 7.0
    return shape.distance(x / factor, y / factor, 0.0) * factor


def _eye_sdf(x: float, y: float, shape: shape_lib.Shape, dot: shape_lib.Shape,
             ring: float, dot_scale: float) -> float:
    """Ring plus centre dot of a finder pattern, in eye-normalised units."""
    ring = max(0.35, min(ring, 3.0))
    outer = _scaled_sdf(shape, x, y, 1.0)
    shrink = 1.0 - 2.0 * ring / 7.0
    if shrink <= 0.08:
        return outer
    inner = _scaled_sdf(shape, x, y, shrink)
    dot_sdf = _scaled_sdf(dot, x, y, dot_scale * 3.0 / 7.0)
    return min(max(outer, -inner), dot_sdf)


def _mix_texture(color: Color, sample: Color4, style: Style) -> Color:
    mode = style.texture_blend
    opacity = style.texture_opacity
    if mode == "source":
        mixed = Color(sample[0], sample[1], sample[2], sample[3])
    elif mode == "multiply":
        mixed = Color(color.r * sample[0] / 255, color.g * sample[1] / 255,
                      color.b * sample[2] / 255, sample[3])
    elif mode == "screen":
        mixed = Color(255 - (255 - color.r) * (255 - sample[0]) / 255,
                      255 - (255 - color.g) * (255 - sample[1]) / 255,
                      255 - (255 - color.b) * (255 - sample[2]) / 255, sample[3])
    elif mode == "overlay":
        def ch(c: int, s: int) -> float:  # noqa: E301
            return (2 * c * s / 255) if c < 128 else (255 - 2 * (255 - c) * (255 - s) / 255)
        mixed = Color(ch(color.r, sample[0]), ch(color.g, sample[1]),
                      ch(color.b, sample[2]), sample[3])
    else:  # average / tint
        mixed = Color((color.r + sample[0]) / 2, (color.g + sample[1]) / 2,
                      (color.b + sample[2]) / 2, sample[3])
    out = color.mix(mixed, opacity)
    return Color(out.r, out.g, out.b, max(color.a, sample[3]))


def _rounded_coverage(dx: float, dy: float, hx: float, hy: float, radius: float) -> float:
    d = shape_lib.sd_round_box(dx, dy, hx, hy, min(radius, min(hx, hy)))
    return max(0.0, min(1.0, 0.5 - d))


def _rounded_mask(image: Pixmap, radius: float) -> None:
    radius = max(0.0, min(radius, min(image.width, image.height) / 2))
    if radius <= 0:
        return
    hx, hy = image.width / 2.0, image.height / 2.0
    for y in range(image.height):
        for x in range(image.width):
            dx, dy = x + 0.5 - hx, y + 0.5 - hy
            if abs(dx) <= hx - radius and abs(dy) <= hy - radius:
                continue
            coverage = max(0.0, min(1.0, 0.5 - shape_lib.sd_round_box(dx, dy, hx, hy, radius)))
            if coverage < 1.0:
                index = (y * image.width + x) * 4 + 3
                image.data[index] = int(image.data[index] * coverage)
