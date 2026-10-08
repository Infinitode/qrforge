"""qrforge -- generate and style QR codes with no dependencies.

    import qrforge

    qrforge.save("https://example.com", "hello.png", "neon", scale=12)

    qr = qrforge.QR("hello", ec="h")
    qr.use_style(module_shape="dot", fg=["#ff0080", "#7928ca"], logo="logo.png")
    qr.save("hello.svg")

Everything (encoding, Reed-Solomon, rasterisation, the PNG codec) is written in
pure Python against the standard library.  Pillow is used only when you ask for
a non-PNG format, a PIL image, or a non-PNG logo.
"""

from .api import Artwork, QR, QRCode, make, png, save, svg, terminal
from .color import Color
from .exceptions import DataTooLong, QRForgeError, StyleError, UnsupportedFeature
from .gradient import Gradient, SolidFill
from .image import Pixmap
from .matrix import QRMatrix, build as build_matrix
from .shaders import Shader, expression, shader
from .shapes import Shape, custom as shape, register as register_shape
from .style import Style

__version__ = "1.0.0"

__all__ = [
    "QR", "QRCode", "Artwork", "make", "save", "svg", "png", "terminal",
    "Style", "Color", "Gradient", "SolidFill", "Pixmap", "QRMatrix", "build_matrix",
    "Shader", "shader", "expression", "Shape", "shape", "register_shape",
    "presets", "shapes", "shaders", "verify",
    "QRForgeError", "DataTooLong", "StyleError", "UnsupportedFeature",
    "__version__",
]


def __getattr__(name):
    """Lazily expose the heavier submodules (``qrforge.presets`` etc.)."""
    if name in ("presets", "shapes", "shaders", "verify", "matrix", "encoder", "tables", "gf"):
        from importlib import import_module
        module = import_module(f".{name}", __name__)
        globals()[name] = module
        return module
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


def preset(name: str) -> Style:
    """Shortcut for ``qrforge.presets.get(name)``."""
    from .presets import get
    return get(name)
