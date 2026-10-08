"""Module shapes.

Every shape is defined once as a *signed distance field* in module units (a
module cell spans ``-0.5 .. 0.5``).  The raster renderer evaluates the SDF per
pixel (which gives free anti-aliasing), while the SVG renderer emits the shape
as a reusable path in ``<defs>`` plus one ``<use>`` per module.
"""

from __future__ import annotations

import math
from typing import Callable, Dict, List, Optional, Sequence, Tuple

# ------------------------------------------------------------------ SDF helpers


def sd_box(x: float, y: float, hx: float, hy: float) -> float:
    dx, dy = abs(x) - hx, abs(y) - hy
    return math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0)


def sd_round_box(x: float, y: float, hx: float, hy: float, r: float) -> float:
    r = max(min(r, min(hx, hy)), 0.0)
    dx, dy = abs(x) - hx + r, abs(y) - hy + r
    return math.hypot(max(dx, 0.0), max(dy, 0.0)) + min(max(dx, dy), 0.0) - r


def sd_circle(x: float, y: float, r: float) -> float:
    return math.hypot(x, y) - r


def sd_diamond(x: float, y: float, r: float) -> float:
    return (abs(x) + abs(y) - r) * 0.7071067811865476


def sd_hexagon(x: float, y: float, r: float) -> float:
    k1, k2, k3 = 0.866025404, 0.5, 0.577350269
    x, y = abs(x), abs(y)
    proj = k1 * x + k2 * y
    if proj < 0:
        x, y = x - 2.0 * proj * k1, y - 2.0 * proj * k2
    x -= max(min(x, k3 * r), -k3 * r)
    y -= r
    return math.hypot(x, y) * (1.0 if y > 0 else -1.0)


def sd_triangle(x: float, y: float, r: float) -> float:
    k = math.sqrt(3.0)
    x = abs(x) - r
    y = y + r / k
    if x + k * y > 0:
        x, y = (x - k * y) / 2.0, (-k * x - y) / 2.0
    x -= max(min(x, 0.0), -2.0 * r)
    return -math.hypot(x, y) * (1.0 if y > 0 else -1.0)


def sd_star(x: float, y: float, outer: float = 0.5, inner: float = 0.27,
            points: int = 5) -> float:
    radius = math.hypot(x, y)
    if radius == 0:
        return -inner
    theta = math.atan2(y, x) + math.pi / 2
    sector = 2.0 * math.pi / max(points, 3)
    a = (theta % sector) - sector / 2.0
    t = min(abs(a) / (sector / 2.0), 1.0)
    inv = (1.0 / outer) + ((1.0 / inner) - (1.0 / outer)) * t
    return radius - 1.0 / inv


def sd_heart(x: float, y: float, r: float = 0.5) -> float:
    px, py = x / (r * 1.2), (-y + r * 0.15) / (r * 1.2)
    a = px * px + py * py - 1.0
    return (a * a * a - px * px * py * py * py) * r * 1.6


def sd_leaf(x: float, y: float, r: float = 0.5) -> float:
    """Vesica piscis: the intersection of two offset circles."""
    c = r * 0.55
    return max(math.hypot(x - c, y) - r, math.hypot(x + c, y) - r)


def sd_cross(x: float, y: float, arm: float = 0.17, r: float = 0.5) -> float:
    return min(sd_round_box(x, y, r, arm, arm * 0.6), sd_round_box(x, y, arm, r, arm * 0.6))


def sd_ring(x: float, y: float, radius: float = 0.36, thickness: float = 0.14) -> float:
    return abs(math.hypot(x, y) - radius) - thickness


def sd_squircle(x: float, y: float, r: float = 0.5, n: float = 4.0) -> float:
    ax, ay = abs(x) / r, abs(y) / r
    if ax == 0 and ay == 0:
        return -r
    return (ax ** n + ay ** n) ** (1.0 / n) * r - r


class Shape:
    """A drawable module shape."""

    def __init__(self, name: str, sdf: Callable[..., float],
                 svg: Optional[Callable[..., str]] = None,
                 gradient_scale: float = 1.0) -> None:
        self.name = name
        self._sdf = sdf
        self._svg = svg
        self.gradient_scale = gradient_scale

    def distance(self, x: float, y: float, radius: float = 0.0) -> float:
        return self._sdf(x, y, radius)

    # ---------------------------------------------------------------- geometry
    def outline(self, n: int = 96, radius: float = 0.0,
                max_radius: float = 0.72) -> List[Tuple[float, float]]:
        """Sample the boundary by bisecting the SDF along 360 degrees."""
        points = []
        for i in range(n):
            theta = 2.0 * math.pi * i / n
            dx, dy = math.cos(theta), math.sin(theta)
            lo, hi = 0.0, max_radius
            if self.distance(dx * hi, dy * hi, radius) < 0:
                points.append((dx * hi, dy * hi))
                continue
            for _ in range(18):
                mid = (lo + hi) / 2.0
                if self.distance(dx * mid, dy * mid, radius) < 0:
                    lo = mid
                else:
                    hi = mid
            points.append((dx * lo, dy * lo))
        return points

    def svg_body(self, radius: float = 0.0) -> str:
        """SVG markup for the shape centred on the origin, 1 module wide."""
        if self._svg is not None:
            return self._svg(radius)
        pts = " ".join(f"{x:.4f} {y:.4f}" for x, y in self.outline(radius=radius))
        return f'<polygon points="{pts}"/>'

    def __repr__(self) -> str:
        return f"Shape({self.name!r})"


def _fmt(v: float) -> str:
    return f"{v:.4f}".rstrip("0").rstrip(".")


def _svg_square(radius: float) -> str:
    if radius > 0:
        r = min(radius, 0.5)
        return f'<rect x="-0.5" y="-0.5" width="1" height="1" rx="{_fmt(r)}" ry="{_fmt(r)}"/>'
    return '<path d="M-0.5 -0.5H0.5V0.5H-0.5Z"/>'


def _svg_circle(radius: float) -> str:
    return '<circle cx="0" cy="0" r="0.5"/>'


def _svg_polygon(points: Sequence[Tuple[float, float]]) -> str:
    return '<polygon points="' + " ".join(f"{_fmt(x)} {_fmt(y)}" for x, y in points) + '"/>'


SHAPES: Dict[str, Shape] = {
    "square": Shape("square", lambda x, y, r=0.0: sd_box(x, y, 0.5, 0.5), _svg_square),
    "rect": Shape("rect", lambda x, y, r=0.0: sd_box(x, y, 0.5, 0.5), _svg_square),
    "rounded": Shape("rounded",
                     lambda x, y, r=0.0: sd_round_box(x, y, 0.5, 0.5, r or 0.22),
                     lambda r=0.0: _svg_square(r or 0.22)),
    "circle": Shape("circle", lambda x, y, r=0.0: sd_circle(x, y, 0.5), _svg_circle),
    "dot": Shape("dot", lambda x, y, r=0.0: sd_circle(x, y, 0.44),
                 lambda r=0.0: '<circle cx="0" cy="0" r="0.44"/>'),
    "diamond": Shape("diamond", lambda x, y, r=0.0: sd_diamond(x, y, 0.5),
                     lambda r=0.0: _svg_polygon([(0, -0.5), (0.5, 0), (0, 0.5), (-0.5, 0)])),
    "hexagon": Shape("hexagon", lambda x, y, r=0.0: sd_hexagon(x, y, 0.5),
                     lambda r=0.0: _svg_polygon(
                         [(0.5 * math.cos(math.radians(a)), 0.5 * math.sin(math.radians(a)))
                          for a in range(-90, 270, 60)])),
    "triangle": Shape("triangle", lambda x, y, r=0.0: sd_triangle(x, -y + 0.0, 0.5),
                      lambda r=0.0: _svg_polygon([(0, -0.5), (0.5, 0.37), (-0.5, 0.37)])),
    "star": Shape("star", lambda x, y, r=0.0: sd_star(x, y)),
    "star6": Shape("star6", lambda x, y, r=0.0: sd_star(x, y, 0.5, 0.28, 6)),
    "cross": Shape("cross", lambda x, y, r=0.0: sd_cross(x, y)),
    "plus": Shape("plus", lambda x, y, r=0.0: sd_cross(x, y, 0.22)),
    "bar_v": Shape("bar_v", lambda x, y, r=0.0: sd_round_box(x, y, 0.2, 0.5, r or 0.18)),
    "bar_h": Shape("bar_h", lambda x, y, r=0.0: sd_round_box(x, y, 0.5, 0.2, r or 0.18)),
    "ring": Shape("ring", lambda x, y, r=0.0: sd_ring(x, y)),
    "squircle": Shape("squircle", lambda x, y, r=0.0: sd_squircle(x, y), gradient_scale=1.4),
    "leaf": Shape("leaf", lambda x, y, r=0.0: sd_leaf(x, y)),
    "heart": Shape("heart", lambda x, y, r=0.0: sd_heart(x, y), gradient_scale=2.2),
}

ALIASES = {
    "dots": "dot", "round": "circle", "rect_round": "rounded", "roundrect": "rounded",
    "rrect": "rounded", "ellipse": "circle", "blob": "squircle", "hex": "hexagon",
    "tri": "triangle", "none": "square",
}


def get(spec) -> Shape:
    """Look up a shape by name, alias or return a user supplied :class:`Shape`."""
    if isinstance(spec, Shape):
        return spec
    if callable(spec):  # a bare SDF function
        return Shape("custom", spec)
    name = str(spec).lower()
    name = ALIASES.get(name, name)
    if name not in SHAPES:
        raise KeyError(f"unknown shape {spec!r}; available: {', '.join(sorted(SHAPES))}")
    return SHAPES[name]


def names() -> List[str]:
    return sorted(SHAPES)


def register(name: str, sdf: Callable[..., float], svg: Optional[Callable[..., str]] = None,
             gradient_scale: float = 1.0) -> Shape:
    """Add your own shape to the registry."""
    shape = Shape(name, sdf, svg, gradient_scale)
    SHAPES[name] = shape
    return shape


def custom(name: str = "custom"):
    """Decorator: register a function as a new shape SDF.

    ::

        @qrforge.shape("wave")
        def wave(x, y, radius=0.0):
            return sd_circle(x, y + 0.1 * math.sin(x * 10), 0.5)
    """
    def decorator(fn):
        return register(name, fn)
    return decorator
