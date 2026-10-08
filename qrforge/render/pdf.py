"""A tiny, dependency-free, single-page vector PDF writer.

Gradients are approximated by sampling the colour source once per module (which
is visually indistinguishable at print size).  Squares emit rectangles; every
other shape emits a polygon from its outline.
"""

from __future__ import annotations

import zlib
from typing import List

from .. import shapes as shape_lib
from ..color import Color
from ..gradient import resolve as resolve_color
from ..matrix import ROLE_FINDER, ROLE_SEPARATOR, QRMatrix
from ..style import Style

PTS = 8.0  # points per module


def render(matrix: QRMatrix, style: Style) -> bytes:
    margin = style.quiet_zone
    total = matrix.size + 2 * margin
    page = total * PTS
    fg = resolve_color(style.fg)
    parts: List[str] = []
    if style.bg is not None:
        c = resolve_color(style.bg).at(0.5, 0.5)
        parts.append(_fill(c) + f"0 0 {page:.2f} {page:.2f} re f\n")

    def emit_shape(row: int, col: int) -> None:
        u = (col - margin) / matrix.size
        v = (row - margin) / matrix.size
        color = fg.at(u, v)
        x = (col) * PTS
        y = page - (row + 1) * PTS
        parts.append(_fill(color))
        if True:
            shape = shape_lib.get(style.module_shape
                                  if not isinstance(style.module_shape, (list, tuple))
                                  else style.module_shape[0])
            scale = (style.module_scale - style.module_gap) * PTS
            cx, cy = x + PTS / 2, y + PTS / 2
            if shape.name in ("square", "rect"):
                h = scale / 2
                parts.append(f"{cx - h:.2f} {cy - h:.2f} {scale:.2f} {scale:.2f} re f\n")
            else:
                pts = shape.outline(12)
                d = f"{cx + pts[0][0] * scale:.2f} {cy + pts[0][1] * scale:.2f} m "
                d += "".join(f"{cx + px * scale:.2f} {cy + py * scale:.2f} l " for px, py in pts[1:])
                parts.append(d + "f\n")

    for row in range(-margin, matrix.size + margin):
        for col in range(-margin, matrix.size + margin):
            if 0 <= row < matrix.size and 0 <= col < matrix.size:
                role = matrix.role(row, col)
                if role in (ROLE_FINDER, ROLE_SEPARATOR):
                    continue
                if matrix.is_dark(row, col):
                    emit_shape(row, col)
    # finder patterns
    for top, left in ((0, 0), (0, matrix.size - 7), (matrix.size - 7, 0)):
        _finder(parts, top, left, page)

    content = "".join(parts).encode("latin-1", "replace")
    return _pdf(page, content)



def _fill(color: Color) -> str:
    return f"{color.r / 255:.3f} {color.g / 255:.3f} {color.b / 255:.3f} rg\n"


def _finder(parts: List[str], top: int, left: int, page: float) -> None:
    x = left * PTS
    y = page - (top + 7) * PTS
    size = 7 * PTS
    parts.append("0 0 0 rg\n")
    parts.append(f"{x:.2f} {y:.2f} {size:.2f} {size:.2f} re f\n")
    parts.append("1 1 1 rg\n")
    inner = 5 * PTS
    parts.append(f"{x + PTS:.2f} {y + PTS:.2f} {inner:.2f} {inner:.2f} re f\n")
    parts.append("0 0 0 rg\n")
    core = 3 * PTS
    parts.append(f"{x + 2 * PTS:.2f} {y + 2 * PTS:.2f} {core:.2f} {core:.2f} re f\n")


def _pdf(page: float, content: bytes) -> bytes:
    compressed = zlib.compress(content, 9)
    objects: List[bytes] = []
    offsets: List[int] = []

    def add(body: bytes) -> None:
        offsets.append(len(b"".join([b"%PDF-1.4\n"] + objects)) )
        objects.append(body)

    header = b"%PDF-1.4\n"
    offsets: List[int] = []
    objs = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        (f"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 {page:.2f} {page:.2f}] "
         f"/Resources << >> /Contents 4 0 R >>").encode(),
        (f"<< /Length {len(compressed)} /Filter /FlateDecode >>").encode()
        + b"\nstream\n" + compressed + b"\nendstream",
    ]
    out = bytearray(header)
    for index, body in enumerate(objs, start=1):
        offsets.append(len(out))
        out += f"{index} 0 obj\n".encode() + body + b"\nendobj\n"
    xref_pos = len(out)
    out += f"xref\n0 {len(objs) + 1}\n".encode()
    out += b"0000000000 65535 f \n"
    for off in offsets:
        out += f"{off:010d} 00000 n \n".encode()
    out += (f"trailer\n<< /Size {len(objs) + 1} /Root 1 0 R >>\n"
            f"startxref\n{xref_pos}\n%%EOF\n").encode()
    return bytes(out)
