"""Terminal output with ANSI true-colour half blocks.

Two modules map onto one terminal cell using ``▀``: the upper half is the
foreground colour, the lower half the background.  Gradients therefore show up
correctly in the terminal.
"""

from __future__ import annotations

from typing import Optional

from ..color import Color
from ..gradient import resolve as resolve_color
from ..matrix import QRMatrix
from ..style import Style

_RESET = "\x1b[0m"


def render(matrix: QRMatrix, style: Style, color: bool = True) -> str:
    margin = style.quiet_zone
    total = matrix.size + 2 * margin
    fg = resolve_color(style.fg)
    bg = resolve_color(style.bg) if style.bg is not None else None

    def dark(row: int, col: int) -> bool:
        r, c = row - margin, col - margin
        if 0 <= r < matrix.size and 0 <= c < matrix.size:
            return matrix.is_dark(r, c)
        return False

    lines = []
    for top in range(0, total, 2):
        out = []
        for col in range(total):
            t = dark(top, col)
            b = dark(top + 1, col) if top + 1 < total else False
            if not color:
                out.append(_block(t, b))
                continue
            top_color = fg.at(col / max(total - 1, 1), top / max(total - 1, 1)) \
                if t else _bg(bg, col, top, total)
            bottom_color = fg.at(col / max(total - 1, 1), (top + 1) / max(total - 1, 1)) \
                if b else _bg(bg, col, top + 1, total)
            out.append(_rgb(top_color, bottom_color) + "▀")
        if color:
            lines.append("".join(out) + _RESET)
        else:
            lines.append("".join(out))
    return "\n".join(lines)


def _block(top: bool, bottom: bool) -> str:
    if top and bottom:
        return "█"
    if top:
        return "▀"
    if bottom:
        return "▄"
    return " "


def _bg(bg, col: int, row: int, total: int) -> Optional[Color]:
    if bg is None:
        return None
    return bg.at(col / max(total - 1, 1), row / max(total - 1, 1))


def _rgb(top: Optional[Color], bottom: Optional[Color]) -> str:
    if top is None and bottom is None:
        return "\x1b[39m\x1b[49m"
    fg_code = (f"\x1b[38;2;{top.r};{top.g};{top.b}m" if top is not None else "\x1b[39m")
    bg_code = (f"\x1b[48;2;{bottom.r};{bottom.g};{bottom.b}m"
               if bottom is not None else "\x1b[49m")
    return fg_code + bg_code
