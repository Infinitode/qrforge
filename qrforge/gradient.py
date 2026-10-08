"""Colour sources: solid colours and gradients (linear, radial, conic).

A *colour source* answers "what colour is this point?" where the point is given
in normalised symbol coordinates (``u`` = 0 at the left edge, 1 at the right).
Both the SVG and the raster renderer use the same objects, so a gradient looks
identical in either output.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

from .color import Color, ColorLike

SpreadKind = str  # "pad" | "reflect" | "repeat"


@dataclass(frozen=True)
class Stop:
    position: float
    color: Color

    @classmethod
    def make(cls, value: Any) -> "Stop":
        if isinstance(value, Stop):
            return value
        if isinstance(value, (tuple, list)) and len(value) == 2 and \
                isinstance(value[0], (int, float)):
            return cls(float(value[0]), Color.parse(value[1]))
        return cls(0.0, Color.parse(value))


def _spread_stops(stops: Sequence[Any]) -> List[Stop]:
    out = [Stop.make(s) for s in stops]
    if not out:
        raise ValueError("a gradient needs at least one stop")
    # colours without an explicit position are distributed evenly
    if all(s.position == 0.0 for s in out) and len(out) > 1:
        out = [Stop(i / (len(out) - 1), s.color) for i, s in enumerate(out)]
    else:
        if out[0].position != 0.0:
            out.insert(0, Stop(0.0, out[0].color))
        if out[-1].position != 1.0:
            out.append(Stop(1.0, out[-1].color))
        last = 0.0
        for i, stop in enumerate(out):
            if stop.position < last:
                out[i] = Stop(last, stop.color)
            else:
                last = stop.position
    return out


class ColorSource:
    """Base class for anything that can colour a pixel."""

    is_solid = False
    color: Optional[Color] = None

    def at(self, u: float, v: float) -> Color:  # pragma: no cover - abstract
        raise NotImplementedError

    def svg_paint(self, uid: str, x: float, y: float, w: float, h: float,
                  defs: List[str]) -> str:  # pragma: no cover - abstract
        raise NotImplementedError


class SolidFill(ColorSource):
    """A single flat colour."""

    is_solid = True

    def __init__(self, color: ColorLike) -> None:
        self.color = Color.parse(color)

    def at(self, u: float, v: float) -> Color:
        return self.color

    def svg_paint(self, uid, x, y, w, h, defs) -> str:
        return self.color.css

    def __repr__(self) -> str:
        return f"SolidFill({self.color.css})"


class Gradient(ColorSource):
    """Multi-stop gradient.

    ``kind`` is ``"linear"``, ``"radial"`` or ``"conic"``.  Stops may be plain
    colours (spread evenly) or ``(position, colour)`` pairs.
    """

    def __init__(self, stops: Sequence[Any], kind: str = "linear", angle: float = 135.0,
                 center: Tuple[float, float] = (0.5, 0.5), radius: float = 0.75,
                 inner: float = 0.0, start_angle: float = 0.0, spread: SpreadKind = "pad",
                 focal: Optional[Tuple[float, float]] = None) -> None:
        self.stops = _spread_stops(stops)
        self.kind = kind
        self.angle = float(angle)
        self.center = tuple(center)  # type: ignore[assignment]
        self.radius = float(radius)
        self.inner = float(inner)
        self.start_angle = float(start_angle)
        self.spread = spread
        self.focal = focal

    # ------------------------------------------------------------- constructors
    @classmethod
    def linear(cls, *colors: ColorLike, angle: float = 135.0, **kw: Any) -> "Gradient":
        return cls(_unpack(colors), "linear", angle=angle, **kw)

    @classmethod
    def radial(cls, *colors: ColorLike, center=(0.5, 0.5), radius: float = 0.75,
               inner: float = 0.0, **kw: Any) -> "Gradient":
        return cls(_unpack(colors), "radial", center=center, radius=radius, inner=inner, **kw)

    @classmethod
    def conic(cls, *colors: ColorLike, center=(0.5, 0.5), start_angle: float = 0.0,
              **kw: Any) -> "Gradient":
        return cls(_unpack(colors), "conic", center=center, start_angle=start_angle, **kw)

    @classmethod
    def parse(cls, spec: Any, default_angle: float = 135.0) -> "Gradient":
        if isinstance(spec, Gradient):
            return spec
        if isinstance(spec, dict):
            kw = dict(spec)
            colors = kw.pop("colors", kw.pop("stops", None))
            kind = kw.pop("kind", "linear")
            kw.setdefault("angle", default_angle)
            return cls(colors if colors is not None else (), kind, **kw)
        if isinstance(spec, (list, tuple)):
            return cls(list(spec), "linear", angle=default_angle)
        raise ValueError(f"cannot read gradient {spec!r}")

    # ---------------------------------------------------------------- sampling
    def _position(self, u: float, v: float) -> float:
        if self.kind == "linear":
            rad = math.radians(self.angle - 90.0)
            dx, dy = math.cos(rad), math.sin(rad)
            proj = u * dx + v * dy
            # normalise across the projection of the unit square
            lo = min(0.0, dx, dy, dx + dy)
            hi = max(0.0, dx, dy, dx + dy)
            return (proj - lo) / (hi - lo) if hi > lo else 0.0
        if self.kind == "radial":
            cx, cy = self.center
            d = math.hypot(u - cx, v - cy)
            span = max(self.radius - self.inner, 1e-9)
            return (d - self.inner) / span
        if self.kind == "conic":
            cx, cy = self.center
            theta = math.degrees(math.atan2(v - cy, u - cx)) + 90.0 - self.start_angle
            return (theta % 360.0) / 360.0
        raise ValueError(f"unknown gradient kind {self.kind!r}")

    def _apply_spread(self, t: float) -> float:
        if self.spread == "repeat":
            return t % 1.0
        if self.spread == "reflect":
            cycle = t % 2.0
            return 2.0 - cycle if cycle > 1.0 else cycle
        return 0.0 if t < 0 else (1.0 if t > 1 else t)

    def at(self, u: float, v: float) -> Color:
        t = self._apply_spread(self._position(u, v))
        stops = self.stops
        if t <= stops[0].position:
            return stops[0].color
        if t >= stops[-1].position:
            return stops[-1].color
        for i in range(1, len(stops)):
            if t <= stops[i].position:
                a, b = stops[i - 1], stops[i]
                span = b.position - a.position
                local = 0.0 if span <= 0 else (t - a.position) / span
                return a.color.mix(b.color, local)
        return stops[-1].color  # pragma: no cover - unreachable

    # --------------------------------------------------------------------- svg
    def svg_paint(self, uid: str, x: float, y: float, w: float, h: float,
                  defs: List[str]) -> str:
        def _stop(s: "Stop") -> str:
            # Built outside the f-string: backslashes inside f-string
            # expressions are only legal on Python 3.12+.
            opacity = ""
            if s.color.a != 255:
                opacity = ' stop-opacity="%.3f"' % s.color.alpha
            return ('<stop offset="%.4f" stop-color="%s"%s/>'
                    % (s.position, s.color.hex(), opacity))

        offsets = "".join(_stop(s) for s in self.stops)
        if self.kind == "linear":
            rad = math.radians(self.angle - 90.0)
            dx, dy = math.cos(rad), math.sin(rad)
            # the axis runs through the centre and spans the square's projection
            lo = min(0.0, dx, dy, dx + dy)
            hi = max(0.0, dx, dy, dx + dy)
            mid = (lo + hi) / 2.0
            x1n, y1n = 0.5 + (lo - mid) * dx, 0.5 + (lo - mid) * dy
            x2n, y2n = 0.5 + (hi - mid) * dx, 0.5 + (hi - mid) * dy
            defs.append(
                f'<linearGradient id="{uid}" gradientUnits="userSpaceOnUse" '
                f'x1="{x + x1n * w:.3f}" y1="{y + y1n * h:.3f}" '
                f'x2="{x + x2n * w:.3f}" y2="{y + y2n * h:.3f}" '
                f'spreadMethod="{_svg_spread(self.spread)}">{offsets}</linearGradient>')
            return f"url(#{uid})"
        if self.kind == "radial":
            cx, cy = self.center
            defs.append(
                f'<radialGradient id="{uid}" gradientUnits="userSpaceOnUse" '
                f'cx="{x + cx * w:.3f}" cy="{y + cy * h:.3f}" r="{max(self.radius, 1e-6) * max(w, h):.3f}" '
                + (f'fr="{self.inner * max(w, h):.3f}" ' if self.inner else "")
                + f'spreadMethod="{_svg_spread(self.spread)}">{offsets}</radialGradient>')
            return f"url(#{uid})"
        # conic: no SVG primitive, so paint it into a pattern of wedges
        steps = 90
        cx, cy = self.center
        px, py = x + cx * w, y + cy * h
        radius = math.hypot(w, h)
        wedges = []
        for i in range(steps):
            t0, t1 = i / steps, (i + 1) / steps
            color = self.at(cx + math.cos(2 * math.pi * t0 - math.pi / 2) * 0.1,
                            cy + math.sin(2 * math.pi * t0 - math.pi / 2) * 0.1)
            a0 = math.radians(self.start_angle + t0 * 360.0 - 90.0)
            a1 = math.radians(self.start_angle + t1 * 360.0 - 90.0)
            wedges.append(
                f'<path d="M{px:.2f} {py:.2f} L{px + math.cos(a0) * radius:.2f} '
                f'{py + math.sin(a0) * radius:.2f} A{radius:.2f} {radius:.2f} 0 0 1 '
                f'{px + math.cos(a1) * radius:.2f} {py + math.sin(a1) * radius:.2f} Z" '
                f'fill="{color.hex()}"/>')
        defs.append(
            f'<pattern id="{uid}" patternUnits="userSpaceOnUse" x="0" y="0" '
            f'width="{x + w:.3f}" height="{y + h:.3f}">'
            f'<g clip-path="url(#clip-{uid})">{"".join(wedges)}</g></pattern>'
            f'<clipPath id="clip-{uid}"><rect x="{x}" y="{y}" width="{w}" height="{h}"/></clipPath>')
        return f"url(#{uid})"

    def __repr__(self) -> str:
        colors = " -> ".join(s.color.hex() for s in self.stops)
        return f"Gradient({self.kind}, {colors})"


def _unpack(colors: Sequence[Any]) -> List[Any]:
    if len(colors) == 1 and isinstance(colors[0], (list, tuple)) and colors[0] and \
            not isinstance(colors[0][0], (int, float)) and not isinstance(colors[0], str):
        return list(colors[0])
    if len(colors) == 1 and isinstance(colors[0], (list, tuple)):
        return list(colors[0])
    return list(colors)


def _svg_spread(spread: str) -> str:
    return {"pad": "pad", "reflect": "reflect", "repeat": "repeat"}.get(spread, "pad")


def resolve(spec: Any, default_angle: float = 135.0) -> ColorSource:
    """Turn a user-supplied colour spec into a :class:`ColorSource`.

    A single colour (name, hex string, RGB tuple, :class:`~qrforge.color.Color`)
    becomes a solid fill; a sequence of colours or a mapping becomes a gradient.
    """
    if isinstance(spec, ColorSource):
        return spec
    if isinstance(spec, dict):
        return Gradient.parse(spec, default_angle)
    if isinstance(spec, (list, tuple)):
        if len(spec) in (3, 4) and all(isinstance(v, (int, float)) for v in spec):
            return SolidFill(spec)
        if len(spec) == 1:
            return SolidFill(spec[0])
        return Gradient.parse(list(spec), default_angle)
    return SolidFill(spec)
