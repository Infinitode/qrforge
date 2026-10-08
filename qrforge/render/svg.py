"""Vector rendering to a standalone SVG document.

Modules of the same shape are merged into a single ``<path>`` with many
sub-paths, which keeps files small and lets symbol-wide gradients and
patterns apply uniformly.  Everything is inline, so the file works anywhere.
"""

from __future__ import annotations

import base64
import math
from typing import Dict, List, Optional

from .. import shapes as shape_lib
from ..gradient import SolidFill, resolve as resolve_color
from ..image import Pixmap
from ..matrix import (ROLE_DARK, ROLE_FINDER, ROLE_SEPARATOR, QRMatrix)
from ..shaders import Context, build as build_shader
from ..style import Style

FUNCTION_ROLES = ("timing", "format", "version", "alignment", "dark")

UNIT = 1.0  # one module


def render(matrix: QRMatrix, style: Style) -> str:
    return SvgRenderer(matrix, style).render()


class SvgRenderer:
    def __init__(self, matrix: QRMatrix, style: Style) -> None:
        self.matrix = matrix
        self.style = style
        self.margin = style.quiet_zone + style.padding
        self.total = matrix.size + 2 * self.margin
        self.defs: List[str] = []
        self._uid = 0

    def uid(self, base: str) -> str:
        self._uid += 1
        return f"qf{base}{self._uid}"

    def cx(self, col: float) -> float:
        return self.margin + col + 0.5

    def cy(self, row: float) -> float:
        return self.margin + row + 0.5

    # ------------------------------------------------------------------- entry
    def render(self) -> str:
        style = self.style
        size_px = int(self.total * style.scale)

        bg_paint = self._background()
        fg_paint = self._paint("fg", style.fg)
        eye_paint = self._paint("eye", style.eye_fg) if style.eye_fg is not None else fg_paint
        function_paint = (self._paint("fn", style.function_fg)
                          if style.function_fg is not None else fg_paint)
        texture_paint = self._texture_paint()
        if texture_paint:
            fg_paint = texture_paint

        symbol_group = self._module_paths(fg_paint, eye_paint, function_paint) + self._logo()

        ctx = Context(self.total, self.total,
                      (self.margin, self.margin, self.matrix.size, self.matrix.size),
                      1.0, style.seed_or(0), None, self.matrix)
        overlays: List[str] = []
        filter_uids: List[str] = []
        for spec in style.shaders or ():
            shader = build_shader(spec)
            uid = self.uid("fx")
            markup = shader.svg_filter(uid, ctx)
            if markup:
                self.defs.append(markup)
                filter_uids.append(uid)
            overlay = shader.svg_overlay(self.uid("ov"), ctx)
            if overlay:
                overlays.append(overlay)

        wrapped = symbol_group
        for uid in reversed(filter_uids):
            wrapped = f'<g filter="url(#{uid})">{wrapped}</g>'
        shadow = self._shadow()
        if shadow:
            wrapped = f'<g filter="url(#{shadow})">{wrapped}</g>'

        clip = self._card_clip()
        parts = [f'<svg xmlns="http://www.w3.org/2000/svg" '
                 f'xmlns:xlink="http://www.w3.org/1999/xlink" '
                 f'viewBox="0 0 {self.total} {self.total}" width="{size_px}" '
                 f'height="{size_px}" role="img" aria-label="QR code">']
        if self.defs:
            parts.append("<defs>" + "".join(self.defs) + "</defs>")
        if clip:
            parts.append(f'<g clip-path="url(#{clip})">')
        if bg_paint:
            parts.append(bg_paint)
        parts.append(wrapped)
        parts.extend(overlays)
        if clip:
            parts.append("</g>")
        parts.append("</svg>")
        return "".join(parts)

    # ------------------------------------------------------------- background
    def _background(self) -> str:
        style = self.style
        radius = style.bg_radius * self.total
        if style.bg_image is not None:
            image = Pixmap.open(style.bg_image)
            uri = "data:image/png;base64," + base64.b64encode(image.to_png()).decode()
            return (f'<image href="{uri}" x="0" y="0" width="{self.total}" '
                    f'height="{self.total}" preserveAspectRatio="xMidYMid slice" '
                    f'opacity="{style.bg_opacity:.3f}"/>')
        if style.bg is None:
            return ""
        paint = self._paint("bg", style.bg)
        return (f'<rect x="0" y="0" width="{self.total}" height="{self.total}" '
                f'rx="{radius:.3f}" fill="{paint}"/>')

    def _card_clip(self) -> Optional[str]:
        if self.style.bg_radius <= 0:
            return None
        uid = self.uid("clip")
        radius = self.style.bg_radius * self.total
        self.defs.append(f'<clipPath id="{uid}"><rect x="0" y="0" width="{self.total}" '
                         f'height="{self.total}" rx="{radius:.3f}"/></clipPath>')
        return uid

    # ------------------------------------------------------------------ paints
    def _paint(self, kind: str, spec) -> str:
        source = resolve_color(spec)
        if isinstance(source, SolidFill):
            return source.color.css
        uid = self.uid(kind)
        return source.svg_paint(uid, 0, 0, self.total, self.total, self.defs)

    def _texture_paint(self) -> Optional[str]:
        style = self.style
        if style.texture is None:
            return None
        image = Pixmap.open(style.texture)
        uri = "data:image/png;base64," + base64.b64encode(image.to_png()).decode()
        uid = self.uid("tex")
        x = self.margin
        size = self.matrix.size
        if style.texture_mode == "stretch" or style.texture_mode == "cover":
            self.defs.append(
                f'<pattern id="{uid}" patternUnits="userSpaceOnUse" x="{x}" y="{x}" '
                f'width="{size}" height="{size}">'
                f'<image href="{uri}" x="0" y="0" width="{size}" height="{size}" '
                f'preserveAspectRatio="xMidYMid slice"/></pattern>')
        else:  # contain
            self.defs.append(
                f'<pattern id="{uid}" patternUnits="userSpaceOnUse" x="{x}" y="{x}" '
                f'width="{size}" height="{size}"><rect x="0" y="0" width="{size}" '
                f'height="{size}" fill="#ffffff"/>'
                f'<image href="{uri}" x="0" y="0" width="{size}" height="{size}" '
                f'preserveAspectRatio="xMidYMid meet"/></pattern>')
        return f"url(#{uid})"

    def _shadow(self) -> Optional[str]:
        style = self.style
        if not style.shadow:
            return None
        spec = dict(style.shadow)
        uid = self.uid("shadow")
        color = _rgb(spec.get("color", "#000000"))
        self.defs.append(
            f'<filter id="{uid}" x="-20%" y="-20%" width="140%" height="140%">'
            f'<feDropShadow dx="{spec.get("dx", 0)}" dy="{spec.get("dy", 0.5)}" '
            f'stdDeviation="{spec.get("blur", 0.5)}" flood-color="{color}" '
            f'flood-opacity="{spec.get("opacity", 0.3):.3f}"/></filter>')
        return uid

    # ---------------------------------------------------------------- modules
    def _module_subpath(self, shape: shape_lib.Shape, cx: float, cy: float,
                        scale: float, rotation: float, radius: float) -> str:
        cos_a, sin_a = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        h = scale / 2.0
        if shape.name in ("square", "rect"):
            if rotation == 0:
                return f'M{cx - h} {cy - h}H{cx + h}V{cy + h}H{cx - h}Z'
            pts = shape.outline(4)
            return self._poly(cx, cy, scale, rotation, pts)
        if shape.name in ("rounded",):
            r = min(radius or 0.25, h)
            return (f'M{cx - h} {cy - h + r}Q{cx - h} {cy - h} {cx - h + r} {cy - h}'
                    f'H{cx + h - r}Q{cx + h} {cy - h} {cx + h} {cy - h + r}'
                    f'V{cy + h - r}Q{cx + h} {cy + h} {cx + h - r} {cy + h}'
                    f'H{cx - h + r}Q{cx - h} {cy + h} {cx - h} {cy + h - r}Z')
        pts = shape.outline(48 if shape.name in ("star", "heart", "leaf") else 16,
                            radius=radius)
        return self._poly(cx, cy, scale, rotation, pts)

    def _poly(self, cx, cy, scale, rotation, pts) -> str:
        cos_a, sin_a = math.cos(math.radians(rotation)), math.sin(math.radians(rotation))
        out = ["M"]
        for i, (px, py) in enumerate(pts):
            x = px * scale * cos_a - py * scale * sin_a + cx
            y = px * scale * sin_a + py * scale * cos_a + cy
            out.append(f'{x:.3f} {y:.3f}' + ("L" if i < len(pts) - 1 else ""))
        return "".join(out) + "Z"

    def _module_paths(self, fg_paint: str, eye_paint: str, function_paint: str) -> str:
        style = self.style
        paths: Dict[str, str] = {}
        random_choices = (isinstance(style.module_shape, (list, tuple)))
        import random
        rng = random.Random(style.seed_or(0))
        for row, col, dark, role in self.matrix.iter_modules():
            if not dark or role == ROLE_FINDER or role == ROLE_SEPARATOR:
                continue
            paint = fg_paint
            if role in FUNCTION_ROLES or role == ROLE_DARK:
                if style.function_shape is not None:
                    shape = shape_lib.get(style.function_shape)
                else:
                    shape = shape_lib.get("square")
                paint = function_paint
            elif random_choices:
                shape = shape_lib.get(rng.choice(style.module_shape))
            else:
                shape = shape_lib.get(style.module_shape)
            scale = max(0.05, style.module_scale - style.module_gap)
            rotation = style.module_rotation
            if style.module_jitter:
                scale *= 1 + (rng.random() - 0.5) * style.module_jitter * 0.6
                rotation += (rng.random() - 0.5) * style.module_jitter * 90
            key = (paint, 0)
            paths[key] = paths.get(key, "") + self._module_subpath(
                shape, self.cx(col), self.cy(row), scale, rotation,
                style.module_radius or 0.0)
        out = "".join(f'<path d="{d}" fill="{paint}" fill-rule="nonzero"/>'
                      for (paint, _), d in paths.items())
        return out + self._eye_paths(eye_paint)

    def _eye_paths(self, eye_paint: str) -> str:
        style = self.style
        size = self.matrix.size
        shape = shape_lib.get(style.eye_shape) if style.eye_shape is not None else \
            shape_lib.get(style.module_shape if not isinstance(style.module_shape, (list, tuple))
                          else style.module_shape[0])
        dot = shape_lib.get(style.eye_dot_shape) if style.eye_dot_shape is not None else shape
        combined = ""
        for top, left in ((0, 0), (0, size - 7), (size - 7, 0)):
            cx, cy = self.cx(left + 3) - 0.5, self.cy(top + 3) - 0.5
            scale = 7.0 * style.eye_scale
            outer = self._eye_poly(shape, cx, cy, scale, 1.0)
            ring_modules = max(0.35, min(style.eye_ring, 3.0))
            shrink = 1.0 - 2.0 * ring_modules / 7.0
            inner = (self._eye_poly(shape, cx, cy, scale, shrink) if shrink > 0.08 else "")
            dot_scale = 3.0 * style.eye_dot_scale
            dot_path = self._eye_poly(dot, cx, cy, scale, dot_scale / 7.0)
            combined += outer + inner + dot_path
        return f'<path d="{combined}" fill="{eye_paint}" fill-rule="evenodd"/>'

    def _eye_poly(self, shape: shape_lib.Shape, cx: float, cy: float,
                  eye_span: float, factor: float) -> str:
        scale = eye_span * factor
        pts = shape.outline(16)
        return self._poly(cx, cy, scale, 0.0, pts)

    # -------------------------------------------------------------------- logo
    def _logo(self) -> str:
        style = self.style
        if style.logo is None:
            return ""
        image = Pixmap.open(style.logo)
        size_px = style.logo_size * self.matrix.size
        cx = self.cx(self.matrix.size / 2.0 - 0.5)
        cy = self.cy(self.matrix.size / 2.0 - 0.5)
        pad = style.logo_padding
        box = size_px + 2 * pad
        radius = box / 2 if style.logo_shape == "circle" else style.logo_radius
        uri = "data:image/png;base64," + base64.b64encode(image.to_png()).decode()
        out = ""
        if style.logo_stroke is not None:
            color, width = style.logo_stroke
            sw = box + 2 * width
            out += (f'<rect x="{cx - sw / 2}" y="{cy - sw / 2}" width="{sw}" height="{sw}" '
                    f'rx="{radius + width:.3f}" fill="none" stroke="{_rgb(color)}" '
                    f'stroke-width="{2 * width:.3f}"/>')
        if style.logo_bg is not None:
            out += (f'<rect x="{cx - box / 2}" y="{cy - box / 2}" width="{box}" height="{box}" '
                    f'rx="{radius:.3f}" fill="{_rgb(style.logo_bg)}"/>')
        # clip + rotate the logo image itself for rounded/circle shapes
        clip = ""
        if style.logo_shape in ("circle", "rounded"):
            uid = self.uid("logoclip")
            self.defs.append(
                f'<clipPath id="{uid}"><rect x="{cx - size_px / 2}" y="{cy - size_px / 2}" '
                f'width="{size_px}" height="{size_px}" rx="{radius:.3f}"/></clipPath>')
            clip = f' clip-path="url(#{uid})"'
        transform = ""
        if style.logo_rotation:
            transform = (f' transform="rotate({style.logo_rotation:.2f} {cx:.2f} {cy:.2f})"')
        opacity = (f' opacity="{style.logo_opacity:.3f}"' if style.logo_opacity < 1 else "")
        out += (f'<g{clip}{transform}><image href="{uri}" x="{cx - size_px / 2}" '
                f'y="{cy - size_px / 2}" width="{size_px}" height="{size_px}" '
                f'preserveAspectRatio="xMidYMid meet"{opacity}/></g>')
        return out


def _rgb(color) -> str:
    from ..color import Color
    return Color.parse(color).hex()


def _escape(text: str) -> str:
    return (text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))
