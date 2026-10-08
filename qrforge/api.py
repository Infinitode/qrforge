"""The public API: :class:`QR`, :class:`Artwork` and the shortcut functions."""

from __future__ import annotations

from typing import Any, Optional, Tuple

from . import matrix as matrix_mod
from .exceptions import QRForgeError, UnsupportedFeature
from .image import Pixmap
from .style import Style, parse as parse_style

__all__ = ["QR", "QRCode", "Artwork", "make", "save", "svg", "png", "terminal"]


class Artwork:
    """A rendered symbol: either vector markup or a pixel buffer."""

    def __init__(self, kind: str, payload: Any, style: Style, matrix) -> None:
        self.kind = kind  # "svg" | "pixmap" | "text" | "pdf" | "bytes"
        self.payload = payload
        self.style = style
        self.matrix = matrix

    # ------------------------------------------------------------------ access
    @property
    def pixmap(self) -> Pixmap:
        if self.kind != "pixmap":
            raise QRForgeError(f"this artwork is {self.kind}, not a pixel buffer")
        return self.payload

    @property
    def text(self) -> str:
        if self.kind not in ("svg", "text"):
            raise QRForgeError(f"this artwork is {self.kind}, not text")
        return self.payload

    @property
    def width(self) -> int:
        return self.pixmap.width if self.kind == "pixmap" else len(self.payload)

    def __str__(self) -> str:
        return self.payload if isinstance(self.payload, str) else repr(self.payload)

    def __repr__(self) -> str:
        if self.kind == "pixmap":
            return f"<Artwork pixmap {self.payload.width}x{self.payload.height}>"
        return f"<Artwork {self.kind} {len(self.payload)} bytes>"

    # ------------------------------------------------------------------ output
    def save(self, path: str) -> str:
        """Write the artwork to ``path``; the format follows the extension."""
        suffix = path.lower().rsplit(".", 1)[-1] if "." in path else "png"
        if self.kind == "pixmap":
            if suffix in ("png",):
                with open(path, "wb") as handle:
                    handle.write(self.payload.to_png())
            elif suffix in ("jpg", "jpeg", "webp", "bmp", "gif", "tiff"):
                self.payload.save(path)  # needs Pillow
            elif suffix in ("svg",):
                raise QRForgeError("cannot write a raster artwork as SVG; call .svg() instead")
            else:
                self.payload.save(path)
            return path
        data = self.payload
        if isinstance(data, str):
            data = data.encode("utf-8")
        with open(path, "wb") as handle:
            handle.write(data)
        return path

    def to_bytes(self) -> bytes:
        if self.kind == "pixmap":
            return self.payload.to_png()
        data = self.payload
        return data.encode("utf-8") if isinstance(data, str) else bytes(data)

    def to_pil(self):
        return self.pixmap.to_pil()

    def to_data_uri(self) -> str:
        import base64
        if self.kind == "svg":
            return "data:image/svg+xml;base64," + base64.b64encode(self.to_bytes()).decode()
        return "data:image/png;base64," + base64.b64encode(self.to_bytes()).decode()

    # --------------------------------------------------------- notebook magic
    def _repr_png_(self):  # pragma: no cover - Jupyter
        return self.to_bytes() if self.kind == "pixmap" else None

    def _repr_svg_(self):  # pragma: no cover - Jupyter
        return self.payload if self.kind == "svg" else None

    def _repr_html_(self):  # pragma: no cover - Jupyter
        if self.kind == "svg":
            return self.payload
        return f'<img src="{self.to_data_uri()}"/>'


class QR:
    """A QR code with its rendering style.

    ::

        qr = qrforge.QR("https://example.com", ec="h")
        qr.style(module_shape="dot", fg=["#ff0080", "#7928ca"], logo="logo.png")
        qr.save("poster.png", scale=16)
    """

    def __init__(self, data: Any, *, ec: str = "M", version: Optional[int] = None,
                 mask: Optional[int] = None, mode: str = "auto",
                 style: Any = None, **style_options: Any) -> None:
        self.data = data
        self.ec = ec.upper()
        self.version = version
        self.mask = mask
        self.mode = mode
        self._matrix = None
        self._style = parse_style(style, **style_options)

    # ---------------------------------------------------------------- encoding
    @property
    def matrix(self):
        """The encoded :class:`~qrforge.matrix.QRMatrix` (built on first use)."""
        if self._matrix is None:
            self._matrix = matrix_mod.build(self.data, self.ec, self.version, self.mask, self.mode)
        return self._matrix

    @property
    def size(self) -> int:
        return self.matrix.size

    @property
    def style(self) -> Style:
        return self._style

    def encode(self, data: Any = None, **options: Any) -> "QR":
        """Change the payload/encoding options and drop the cached matrix."""
        if data is not None:
            self.data = data
        for key in ("ec", "version", "mask", "mode"):
            if key in options:
                setattr(self, key, options.pop(key))
        if options:
            raise QRForgeError(f"unknown encoding option(s): {', '.join(options)}")
        self._matrix = None
        return self

    def styled(self, style: Any = None, **options: Any) -> "QR":
        """Return a copy of this code with a different style."""
        clone = QR(self.data, ec=self.ec, version=self.version, mask=self.mask, mode=self.mode)
        clone._matrix = self._matrix
        clone._style = self._resolve(style, options)
        return clone

    def use_style(self, style: Any = None, **options: Any) -> "QR":
        """Change this code's style in place (chainable)."""
        if isinstance(style, Style):
            self._style = self._style.merged(style, **options)
        elif isinstance(style, dict):
            self._style = self._style.merged(**style, **options)
        elif isinstance(style, str) and style:
            from .presets import get as preset_get
            self._style = preset_get(style).merged(self._style, **options)
        elif options:
            self._style = self._style.merged(**options)
        return self

    # ----------------------------------------------------------------- outputs
    def render(self, style: Any = None, **options: Any) -> Artwork:
        """Render to a pixel buffer (PNG-ready)."""
        return self._artwork("pixmap", style, options)

    def svg(self, style: Any = None, **options: Any) -> str:
        """Render to an SVG document."""
        return self._artwork("svg", style, options).payload

    def png(self, style: Any = None, **options: Any) -> bytes:
        """Render and encode as PNG bytes."""
        return self._artwork("pixmap", style, options).payload.to_png()

    def pdf(self, style: Any = None, **options: Any) -> bytes:
        """Render to a single-page vector PDF."""
        from .render.pdf import render
        return render(self.matrix, self._resolve(style, options))

    def terminal(self, style: Any = None, color: bool = True, **options: Any) -> str:
        """Render as ANSI half-block text for a terminal."""
        from .render.ansi import render
        return render(self.matrix, self._resolve(style, options), color=color)

    def print(self, style: Any = None, **options: Any) -> "QR":
        print(self.terminal(style, **options))
        return self

    def ascii(self, dark: str = "██", light: str = "  ") -> str:
        """Plain text art of the symbol."""
        return self.matrix.ascii(dark, light)

    def to_pil(self, style: Any = None, **options: Any):
        """Render and return a Pillow ``Image`` (requires Pillow)."""
        return self.render(style, **options).to_pil()

    def save(self, path: str, style: Any = None, **options: Any) -> str:
        """Render and write to ``path``; format chosen by extension."""
        suffix = path.lower().rsplit(".", 1)[-1] if "." in path else "png"
        if suffix in ("svg", "html"):
            artwork = self._artwork("svg", style, options)
            payload = artwork.payload
            if suffix == "html":
                payload = _html_page(payload, str(self.data))
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(payload)
            return path
        if suffix == "pdf":
            with open(path, "wb") as handle:
                handle.write(self.pdf(style, **options))
            return path
        if suffix in ("txt", "ansi"):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write(self.terminal(style, color=suffix == "ansi", **options))
            return path
        return self.render(style, **options).save(path)

    def show(self, style: Any = None, **options: Any) -> "QR":  # pragma: no cover - interactive
        """Open the rendered symbol in the system image viewer."""
        import os
        import tempfile
        path = os.path.join(tempfile.gettempdir(), "qrforge.png")
        self.render(style, **options).save(path)
        try:
            import webbrowser
            webbrowser.open(f"file://{path}")
        except Exception:
            pass
        return self

    # ------------------------------------------------------------------- misc
    def verify(self) -> str:
        """Decode the symbol again and return the text (round-trip check)."""
        from .verify import decode
        return decode([list(row) for row in self.matrix.modules]).text

    def info(self) -> dict:
        matrix = self.matrix
        return {
            "data": str(self.data) if not isinstance(self.data, (bytes, bytearray)) else "<bytes>",
            "version": matrix.version,
            "level": matrix.level,
            "mask": matrix.mask,
            "size": matrix.size,
            "modules": matrix.size ** 2,
            "codewords": matrix.total_codewords(),
            "dark_ratio": round(matrix.dark_ratio(), 4),
            "penalty": matrix.penalty_score,
            "segments": [(s.mode, len(s.text)) for s in matrix.segments],
        }

    def _resolve(self, style: Any, options: dict) -> Style:
        if style is None:
            return self._style.merged(**options) if options else self._style
        if isinstance(style, Style):
            return self._style.merged(style, **options)
        if isinstance(style, dict):
            return self._style.merged(**style, **options)
        if isinstance(style, str):
            from .presets import get as preset_get
            return preset_get(style).merged(**options)
        raise QRForgeError(f"cannot use {style!r} as a style")

    def _artwork(self, kind: str, style: Any, options: dict) -> Artwork:
        resolved = self._resolve(style, options)
        matrix = self.matrix
        if kind == "svg":
            from .render.svg import render
            return Artwork("svg", render(matrix, resolved), resolved, matrix)
        from .render.raster import render as raster_render
        return Artwork("pixmap", raster_render(matrix, resolved), resolved, matrix)

    def __repr__(self) -> str:
        return f"<QR {str(self.data)[:28]!r} ec={self.ec} style={self._style!r}>"


QRCode = QR  # friendly alias


def _html_page(svg: str, title: str) -> str:
    return ("<!doctype html><meta charset='utf-8'>"
            f"<title>{title[:60]}</title>"
            "<style>body{margin:0;display:grid;place-items:center;min-height:100vh;"
            "background:#111;font:14px system-ui}"
            "main{padding:32px;background:#fff;border-radius:16px;box-shadow:0 20px 60px #0008}"
            "</style><main>" + svg + "</main>")


# ------------------------------------------------------------------- shortcuts
def make(data: Any, style: Any = None, **options: Any) -> Artwork:
    """Render ``data`` in one call::

        qrforge.make("hello", "dots", fg="#123").save("hello.png")
    """
    preset = style if isinstance(style, str) else None
    extra = dict(style) if isinstance(style, dict) else {}
    qr = QR(data)
    qr._style = parse_style(preset, **{**extra, **options})
    return qr.render()


def save(data: Any, path: str, style: Any = None, **options: Any) -> str:
    """Render ``data`` straight to ``path``."""
    preset = style if isinstance(style, str) else None
    extra = dict(style) if isinstance(style, dict) else {}
    qr = QR(data)
    qr._style = parse_style(preset, **{**extra, **options})
    return qr.save(path)


def svg(data: Any, style: Any = None, **options: Any) -> str:
    preset = style if isinstance(style, str) else None
    extra = dict(style) if isinstance(style, dict) else {}
    qr = QR(data)
    qr._style = parse_style(preset, **{**extra, **options})
    return qr.svg()


def png(data: Any, style: Any = None, **options: Any) -> bytes:
    preset = style if isinstance(style, str) else None
    extra = dict(style) if isinstance(style, dict) else {}
    qr = QR(data)
    qr._style = parse_style(preset, **{**extra, **options})
    return qr.png()


def terminal(data: Any, style: Any = None, **options: Any) -> str:
    preset = style if isinstance(style, str) else None
    extra = dict(style) if isinstance(style, dict) else {}
    qr = QR(data)
    qr._style = parse_style(preset, **{**extra, **options})
    return qr.terminal()
