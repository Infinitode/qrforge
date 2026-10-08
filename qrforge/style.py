"""The :class:`Style` object: every knob QRForge exposes.

A ``Style`` is a plain dataclass, so you can build one, tweak it, pass it
around, or hand it to several renders::

    style = qrforge.Style(module_shape="dot", fg=["#ff0080", "#7928ca"])
    qr = qrforge.QR("hello").style(style)
    qr.save("a.svg")
    qr.save("b.png", scale=16)
"""

from __future__ import annotations

from dataclasses import dataclass, field, fields, replace
from typing import Any, Dict, Optional, Sequence, Tuple, Union

from .exceptions import StyleError

__all__ = ["Style"]


@dataclass
class Style:
    # ---------------------------------------------------------------- modules
    #: shape of the data modules -- a name from :data:`qrforge.shapes.SHAPES`,
    #: a :class:`~qrforge.shapes.Shape`, an SDF function, or a sequence of
    #: those to pick from at random.
    module_shape: Any = "square"
    #: size of the shape inside its cell (1.0 = modules touch, 0.8 = gaps).
    module_scale: float = 1.0
    #: extra inset in module units.
    module_gap: float = 0.0
    #: corner radius in module units (rounded shapes).
    module_radius: Optional[float] = None
    #: rotation of every module in degrees.
    module_rotation: float = 0.0
    #: 0..1 random variation of scale/rotation/shape per module.
    module_jitter: float = 0.0
    #: draw function modules (timing, format, alignment) with a different shape.
    function_shape: Any = None
    #: colour source for function modules; defaults to ``fg``.
    function_fg: Any = None
    #: make the symbol read as "light on dark" without touching the colours.
    invert: bool = False

    # ------------------------------------------------------------------- eyes
    #: shape of the three finder patterns; ``None`` derives it from the module.
    eye_shape: Any = None
    #: shape of the dot in the middle of an eye.
    eye_dot_shape: Any = None
    #: thickness of the eye ring in module units.
    eye_ring: float = 1.0
    #: scale of the whole eye / its dot.
    eye_scale: float = 1.0
    eye_dot_scale: float = 1.0
    #: separate colour source for the eyes; defaults to ``fg``.
    eye_fg: Any = None
    #: keep a quiet gap between the eye and the data modules.
    eye_padding: float = 0.0

    # ----------------------------------------------------------------- colours
    #: colour, gradient (list of colours) or gradient dict for the modules.
    fg: Any = "#101014"
    #: background colour/gradient, or ``None`` for transparency.
    bg: Any = "#ffffff"
    #: background image (path, bytes, PIL image or Pixmap).
    bg_image: Any = None
    bg_opacity: float = 1.0
    #: corner radius of the background card, as a fraction of the symbol width.
    bg_radius: float = 0.0
    #: extra padding around the symbol in module units.
    padding: float = 0.0

    # ---------------------------------------------------------------- texture
    #: image painted *inside* the modules instead of ``fg``.
    texture: Any = None
    texture_mode: str = "cover"  # cover | contain | stretch
    texture_opacity: float = 1.0
    #: how the texture mixes with ``fg``: source | multiply | screen | overlay | tint
    texture_blend: str = "source"
    #: sample the texture per symbol (``False`` = per module, i.e. tiled).
    texture_global: bool = True

    # ------------------------------------------------------------------- logo
    logo: Any = None
    #: logo width as a fraction of the symbol width.
    logo_size: float = 0.22
    #: corner radius of the logo cut-out, in module units.
    logo_radius: float = 0.0
    #: clear zone around the logo in module units.
    logo_padding: float = 0.75
    #: colour behind the logo; ``None`` keeps whatever is underneath.
    logo_bg: Any = "#ffffff"
    logo_shape: str = "square"  # square | circle | rounded
    #: rotation of the logo in degrees.
    logo_rotation: float = 0.0
    #: opacity of the logo image (0..1).
    logo_opacity: float = 1.0
    #: stroke drawn around the logo cut-out: (colour, width_in_modules) or None.
    logo_stroke: Any = None
    #: "center", or an (x, y) fraction of the symbol size.
    logo_position: Any = "center"

    # ----------------------------------------------------------------- effects
    #: shaders applied in order; names, tuples, callables or Shader objects.
    shaders: Tuple[Any, ...] = ()
    #: drop shadow: ``{"color": ..., "dx":, "dy":, "blur":, "opacity":}``.
    shadow: Optional[Dict[str, Any]] = None
    #: outline/stroke drawn around modules, as ``(colour, width_in_modules)``.
    stroke: Optional[Tuple[Any, float]] = None

    # ---------------------------------------------------------------- geometry
    #: pixels per module for raster output.
    scale: int = 8
    #: quiet zone in modules (the spec asks for 4).
    quiet_zone: int = 4
    #: seed for every randomised effect; ``None`` picks one at random.
    seed: Optional[int] = None
    #: supersampling factor used when rasterising shapes (1 = analytic AA).
    supersample: int = 1

    # ------------------------------------------------------------------ helper
    def copy(self, **overrides: Any) -> "Style":
        return replace(self, **overrides)

    def merged(self, other: Optional["Style"] = None, **overrides: Any) -> "Style":
        """Return a new style with ``other`` and then ``overrides`` applied."""
        result = self
        if other is not None:
            result = replace(result, **other.to_dict(include_defaults=False))
        known = {f.name for f in fields(self)}
        unknown = set(overrides) - known
        if unknown:
            raise StyleError(f"unknown style option(s): {', '.join(sorted(unknown))}")
        return replace(result, **overrides) if overrides else result

    def to_dict(self, include_defaults: bool = True) -> Dict[str, Any]:
        out = {}
        for f in fields(self):
            value = getattr(self, f.name)
            if not include_defaults and value == f.default:
                continue
            out[f.name] = value
        return out

    def seed_or(self, default: int = 0) -> int:
        return default if self.seed is None else int(self.seed)

    def __repr__(self) -> str:
        parts = ", ".join(f"{k}={v!r}" for k, v in self.to_dict(include_defaults=False).items())
        return f"Style({parts})"


def parse(spec: Any, **overrides: Any) -> Style:
    """Build a :class:`Style` from a dict, a preset name, a Style or kwargs."""
    from .presets import get as preset_get, names as preset_names

    base: Style = Style()
    if isinstance(spec, Style):
        base = spec
    elif isinstance(spec, dict):
        base = Style(**_clean(spec))
    elif isinstance(spec, str):
        base = preset_get(spec)
    elif spec is not None:
        raise StyleError(f"cannot build a style from {spec!r}")
    if overrides:
        base = base.merged(**_clean(overrides))
    return base


def _clean(kwargs: Dict[str, Any]) -> Dict[str, Any]:
    known = {f.name for f in fields(Style)}
    unknown = set(kwargs) - known
    if unknown:
        raise StyleError(f"unknown style option(s): {', '.join(sorted(unknown))}")
    out = dict(kwargs)
    if isinstance(out.get("shaders"), (str, list)) and not isinstance(out.get("shaders"), tuple):
        value = out["shaders"]
        out["shaders"] = (value,) if isinstance(value, str) else tuple(value)
    return out


def options() -> Tuple[str, ...]:
    return tuple(f.name for f in fields(Style))
