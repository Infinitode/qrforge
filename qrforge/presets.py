"""Ready-made looks.  ``qrforge.save("hi", "out.png", "neon")``."""

from __future__ import annotations

from typing import Dict

from .exceptions import StyleError
from .style import Style

_PRESETS: Dict[str, Dict] = {
    "classic": dict(fg="#000000", bg="#ffffff", module_shape="square", module_scale=1.0),
    "dots": dict(module_shape="dot", module_scale=0.92, eye_shape="rounded", eye_dot_shape="dot",
                 fg="#111111", bg="#ffffff"),
    "rounded": dict(module_shape="rounded", module_radius=0.3, module_scale=0.96,
                    eye_shape="rounded", eye_dot_shape="rounded"),
    "soft": dict(module_shape="squircle", module_scale=0.94, eye_shape="squircle",
                 eye_dot_shape="squircle"),
    "confetti": dict(module_shape=["dot", "diamond", "star", "hexagon", "leaf"],
                     module_scale=0.9, module_jitter=0.25, eye_shape="rounded",
                     fg=["#ff5f6d", "#ffc371", "#47e5bc", "#5b86e5"], seed=3),
    "neon": dict(fg=["#00f0ff", "#7b2ff7", "#ff2ec4"], bg="#0a0118", module_shape="rounded",
                 module_radius=0.28, module_scale=0.94, eye_shape="rounded",
                 eye_dot_shape="rounded", shaders=("glow:radius=2,amount=0.75",
                                                   "grain:amount=0.06")),
    "sunset": dict(fg={"kind": "linear", "angle": 135,
                       "colors": ["#ff9a3c", "#ff4d6d", "#7b2ff7"]},
                   bg="#fff6ec", module_shape="rounded", module_radius=0.25,
                   module_scale=0.95, eye_shape="rounded", eye_dot_shape="circle"),
    "blueprint": dict(fg="#e8f4ff", bg="#0d2b45", module_shape="square", module_scale=0.86,
                      eye_shape="square", eye_dot_shape="square",
                      shaders=("scanlines:gap=3,amount=0.12,color=#ffffff",)),
    "brutal": dict(fg="#000000", bg="#f2f2f2", module_shape="square", module_scale=1.0,
                   eye_shape="square", stroke=("#f2f2f2", 0.12)),
    "vapor": dict(fg={"kind": "conic", "colors": ["#ff71ce", "#01cdfe", "#05ffa1",
                                                  "#b967ff", "#ff71ce"]},
                  bg="#1a0b2e", module_shape="dot", module_scale=0.9, eye_shape="circle",
                  eye_dot_shape="dot", shaders=("chromatic:offset=1.5",)),
    "film": dict(fg="#201a17", bg="#f4efe6", module_shape="dot", module_scale=0.88,
                 eye_shape="rounded", eye_dot_shape="dot",
                 shaders=("duotone:shadow=#2b2118,highlight=#f7ecd8,amount=0.85",
                          "grain:amount=0.16", "vignette:amount=0.35")),
    "halftone": dict(fg="#101010", bg="#ffffff", module_shape="square", module_scale=1.0,
                     shaders=("halftone:cell=0,color=#101010,background=#ffffff",)),
    "gold": dict(fg=["#f7d488", "#b8860b", "#fff3c4"], bg="#14100c", module_shape="rounded",
                 module_radius=0.3, module_scale=0.94, eye_shape="rounded",
                 shaders=("grain:amount=0.08", "vignette:amount=0.45")),
    "ice": dict(fg={"kind": "radial", "colors": ["#ffffff", "#8ed6ff", "#1f6feb"]},
                bg="#04121f", module_shape="circle", module_scale=0.86, eye_shape="circle",
                eye_dot_shape="circle", shaders=("glow:radius=2,amount=0.55",)),
    "leaf": dict(fg=["#2f9e44", "#087f5b"], bg="#f4fce3", module_shape="leaf",
                 module_scale=0.94, module_rotation=45, eye_shape="rounded",
                 eye_dot_shape="leaf"),
    "circuit": dict(fg="#00ffa3", bg="#041014", module_shape="square", module_scale=0.8,
                    function_shape="bar_h", eye_shape="square", eye_dot_shape="square",
                    shaders=("glow:radius=1.5,amount=0.6",)),
    "retro": dict(fg="#3b2b20", bg="#efe3c8", module_shape="square", module_scale=1.0,
                  shaders=("sepia:amount=0.9", "scanlines:gap=4,amount=0.25,color=#3b2b20",
                           "grain:amount=0.1")),
    "glitch": dict(fg="#ffffff", bg="#0b0b0f", module_shape="square", module_scale=1.0,
                   shaders=("glitch:offset=0.32,band=1,probability=0.5",
                            "chromatic:offset=1.5")),
    "minimal": dict(fg="#111111", bg="#ffffff", module_shape="circle", module_scale=0.62,
                    eye_shape="circle", eye_dot_shape="circle", eye_ring=1.2),
    "badge": dict(fg="#111827", bg="#ffffff", module_shape="rounded", module_radius=0.3,
                  module_scale=0.94, eye_shape="rounded", eye_dot_shape="rounded",
                  quiet_zone=4, padding=2, bg_radius=0.06,
                  shadow={"color": "#0b1020", "dy": 6, "blur": 5, "opacity": 0.25}),
    # data modules are stars, but the finder patterns stay solid so scanners
    # can still lock on; the grain is kept subtle on purpose.
    "starry": dict(fg="#ffffff", bg={"kind": "radial", "colors": ["#1b2a6b", "#05070f"]},
                   module_shape="star", module_scale=1.0, eye_shape="rounded",
                   eye_dot_shape="rounded", shaders=("grain:amount=0.06",)),
    "cross": dict(fg="#e63946", bg="#fff8f0", module_shape="cross", module_scale=0.96,
                  eye_shape="cross", eye_dot_shape="cross"),
}


def get(name: str, **overrides) -> Style:
    """Return the :class:`~qrforge.style.Style` for a preset name.

    Any style field can be overridden, e.g. ``presets.get("neon", fg="#0f0")``.
    """
    key = str(name).lower().replace(" ", "_").replace("-", "_")
    if key not in _PRESETS:
        raise StyleError(f"unknown preset {name!r}; available: {', '.join(names())}")
    base = dict(_PRESETS[key])
    base.update(overrides)
    return Style(**base)


def names():
    return sorted(_PRESETS)


def register(name: str, **options) -> None:
    """Add your own preset."""
    _PRESETS[str(name).lower()] = dict(options)
