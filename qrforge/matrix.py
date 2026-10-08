"""Symbol matrix construction: function patterns, data placement and masking.

The resulting :class:`QRMatrix` carries not only the dark/light grid but also a
*role map* that says what every module is (finder, timing, data, ...).  The
renderers use it to style eyes, timing lines and data modules differently.
"""

from __future__ import annotations

from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

from .encoder import encode_codewords, normalize, pick_version
from .tables import LEVEL_BITS, alignment_positions, total_codewords, version_size

ROLE_DATA = 0
ROLE_FINDER = 1
ROLE_SEPARATOR = 2
ROLE_TIMING = 3
ROLE_ALIGNMENT = 4
ROLE_FORMAT = 5
ROLE_VERSION = 6
ROLE_DARK = 7

ROLE_NAMES = {
    ROLE_DATA: "data",
    ROLE_FINDER: "finder",
    ROLE_SEPARATOR: "separator",
    ROLE_TIMING: "timing",
    ROLE_ALIGNMENT: "alignment",
    ROLE_FORMAT: "format",
    ROLE_VERSION: "version",
    ROLE_DARK: "dark",
}

#: modules that belong to the three position detection patterns
EYE_ROLES = frozenset({ROLE_FINDER, ROLE_SEPARATOR, ROLE_DARK})
#: everything that is not payload
FUNCTION_ROLES = frozenset({ROLE_FINDER, ROLE_SEPARATOR, ROLE_TIMING, ROLE_ALIGNMENT,
                            ROLE_FORMAT, ROLE_VERSION, ROLE_DARK})

PENALTY_N1, PENALTY_N2, PENALTY_N3, PENALTY_N4 = 3, 3, 40, 10

MASKS = (
    lambda r, c: (r + c) % 2 == 0,
    lambda r, c: r % 2 == 0,
    lambda r, c: c % 3 == 0,
    lambda r, c: (r + c) % 3 == 0,
    lambda r, c: (r // 2 + c // 3) % 2 == 0,
    lambda r, c: (r * c) % 2 + (r * c) % 3 == 0,
    lambda r, c: ((r * c) % 2 + (r * c) % 3) % 2 == 0,
    lambda r, c: ((r + c) % 2 + (r * c) % 3) % 2 == 0,
)


def _bch_format(data5: int) -> int:
    """Format information: 5 payload bits -> 15 bits, masked as per spec."""
    v = data5 << 10
    for i in range(14, 9, -1):
        if v & (1 << i):
            v ^= 0b10100110111 << (i - 10)
    return ((data5 << 10) | v) ^ 0b101010000010010


def _bch_version(version: int) -> int:
    """Version information: 6 bits -> 18 bits."""
    v = version << 12
    for i in range(17, 11, -1):
        if v & (1 << i):
            v ^= 0b1111100100101 << (i - 12)
    return (version << 12) | v


class QRMatrix:
    """An encoded QR symbol, ready to be rendered."""

    __slots__ = ("version", "level", "mask", "size", "modules", "roles", "segments", "penalty_score")

    def __init__(self, version: int, level: str, mask: int, modules: List[bytearray],
                 roles: List[bytearray], segments: Sequence = (), penalty_score: int = 0) -> None:
        self.version = version
        self.level = level
        self.mask = mask
        self.size = version_size(version)
        self.modules = modules
        self.roles = roles
        self.segments = tuple(segments)
        self.penalty_score = penalty_score

    # ------------------------------------------------------------- basic access
    def __getitem__(self, pos: Tuple[int, int]) -> bool:
        row, col = pos
        return bool(self.modules[row][col])

    def is_dark(self, row: int, col: int) -> bool:
        return bool(self.modules[row][col])

    def role(self, row: int, col: int) -> int:
        return self.roles[row][col]

    def role_name(self, row: int, col: int) -> str:
        return ROLE_NAMES[self.roles[row][col]]

    @property
    def width(self) -> int:
        return self.size

    @property
    def height(self) -> int:
        return self.size

    def rows(self) -> List[List[bool]]:
        return [[bool(v) for v in row] for row in self.modules]

    def iter_modules(self) -> Iterator[Tuple[int, int, bool, int]]:
        for r, row in enumerate(self.modules):
            roles = self.roles[r]
            for c, value in enumerate(row):
                yield r, c, bool(value), roles[c]

    def dark_ratio(self) -> float:
        dark = sum(sum(row) for row in self.modules)
        return dark / (self.size * self.size)

    def total_codewords(self) -> int:
        return total_codewords(self.version, self.level)

    def ascii(self, dark: str = "##", light: str = "  ") -> str:
        return "\n".join("".join(dark if v else light for v in row) for row in self.modules)

    def __repr__(self) -> str:
        return (f"<QRMatrix version={self.version} level={self.level} mask={self.mask} "
                f"size={self.size}x{self.size}>")

    def to_dict(self) -> dict:
        return {
            "version": self.version,
            "level": self.level,
            "mask": self.mask,
            "size": self.size,
            "modules": ["".join("1" if v else "0" for v in row) for row in self.modules],
        }


# ------------------------------------------------------------------- construction
def build(text, level: str = "M", version: Optional[int] = None,
          mask: Optional[int] = None, mode: str = "auto") -> QRMatrix:
    """Encode ``text`` and return its :class:`QRMatrix`."""
    text = normalize(text)
    level = level.upper()
    if mask is not None and not 0 <= mask <= 7:
        raise ValueError("mask must be between 0 and 7")
    if version is None:
        chosen, segments = pick_version(text, level, mode)
    else:
        from .encoder import segment as _segment
        if not 1 <= version <= 40:
            raise ValueError("version must be between 1 and 40")
        segments = _segment(text, version, mode)
        from .encoder import capacity_bits, segment_bits
        if segment_bits(segments, version) + 4 > capacity_bits(version, level):
            from .exceptions import DataTooLong
            raise DataTooLong(f"data does not fit in version {version} at level {level}")
        chosen = version

    codewords = encode_codewords(text, chosen, level, segments)
    size = version_size(chosen)
    modules = [bytearray(size) for _ in range(size)]
    roles = [bytearray(size) for _ in range(size)]

    _place_function_patterns(size, chosen, modules, roles)
    _place_data(size, modules, roles, codewords)

    best_mask, best_penalty = 0, None
    candidates: Iterable[int] = range(8) if mask is None else (mask,)
    for m in candidates:
        _apply_mask(size, modules, roles, m)
        _place_format_info(size, chosen, level, m, modules, roles)
        score = _penalty(modules, size)
        if best_penalty is None or score < best_penalty:
            best_mask, best_penalty = m, score
        _apply_mask(size, modules, roles, m)  # undo, next candidate re-applies
    _apply_mask(size, modules, roles, best_mask)
    _place_format_info(size, chosen, level, best_mask, modules, roles)
    return QRMatrix(chosen, level, best_mask, modules, roles, segments, best_penalty or 0)


def _mark(modules: List[bytearray], roles: List[bytearray], row: int, col: int,
          value: int, role: int) -> None:
    modules[row][col] = value
    roles[row][col] = role


def _place_function_patterns(size: int, version: int, modules: List[bytearray],
                             roles: List[bytearray]) -> None:
    # finder patterns + separators
    for base_row, base_col in ((0, 0), (0, size - 7), (size - 7, 0)):
        for r in range(-1, 8):
            for c in range(-1, 8):
                rr, cc = base_row + r, base_col + c
                if not (0 <= rr < size and 0 <= cc < size):
                    continue
                if 0 <= r <= 6 and 0 <= c <= 6:
                    edge = r in (0, 6) or c in (0, 6)
                    core = 2 <= r <= 4 and 2 <= c <= 4
                    _mark(modules, roles, rr, cc, 1 if (edge or core) else 0, ROLE_FINDER)
                else:
                    _mark(modules, roles, rr, cc, 0, ROLE_SEPARATOR)
    # timing patterns
    for i in range(8, size - 8):
        _mark(modules, roles, 6, i, 1 if i % 2 == 0 else 0, ROLE_TIMING)
        _mark(modules, roles, i, 6, 1 if i % 2 == 0 else 0, ROLE_TIMING)
    # alignment patterns
    positions = alignment_positions(version)
    for r in positions:
        for c in positions:
            if roles[r][c] == ROLE_FINDER:  # sits on top of a finder pattern
                continue
            for dr in range(-2, 3):
                for dc in range(-2, 3):
                    ring = max(abs(dr), abs(dc))
                    _mark(modules, roles, r + dr, c + dc, 1 if ring != 1 else 0, ROLE_ALIGNMENT)
    # reserve format areas
    for i in range(9):
        if roles[8][i] == ROLE_DATA:
            roles[8][i] = ROLE_FORMAT
        if roles[i][8] == ROLE_DATA:
            roles[i][8] = ROLE_FORMAT
    for i in range(8):
        if roles[8][size - 1 - i] == ROLE_DATA:
            roles[8][size - 1 - i] = ROLE_FORMAT
        if roles[size - 1 - i][8] == ROLE_DATA:
            roles[size - 1 - i][8] = ROLE_FORMAT
    _mark(modules, roles, size - 8, 8, 1, ROLE_DARK)
    # version information
    if version >= 7:
        bits = _bch_version(version)
        for i in range(18):
            bit = (bits >> i) & 1
            a = size - 11 + i % 3
            b = i // 3
            _mark(modules, roles, b, a, bit, ROLE_VERSION)
            _mark(modules, roles, a, b, bit, ROLE_VERSION)


def _place_data(size: int, modules: List[bytearray], roles: List[bytearray],
                codewords: Sequence[int]) -> None:
    bits = [(byte >> (7 - i)) & 1 for byte in codewords for i in range(8)]
    index = 0
    total = len(bits)
    right = size - 1
    while right >= 1:
        if right == 6:
            right -= 1
        upward = ((right + 1) & 2) == 0
        for vert in range(size):
            row = (size - 1 - vert) if upward else vert
            for j in range(2):
                col = right - j
                if roles[row][col] != ROLE_DATA:
                    continue
                if index < total:
                    modules[row][col] = bits[index]
                    index += 1
        right -= 2


def _apply_mask(size: int, modules: List[bytearray], roles: List[bytearray], mask_id: int) -> None:
    fn = MASKS[mask_id]
    for r in range(size):
        row = modules[r]
        role_row = roles[r]
        for c in range(size):
            if role_row[c] == ROLE_DATA and fn(r, c):
                row[c] ^= 1


def _place_format_info(size: int, version: int, level: str, mask_id: int,
                       modules: List[bytearray], roles: List[bytearray]) -> None:
    bits = _bch_format((LEVEL_BITS[level] << 3) | mask_id)

    def put(row: int, col: int, value: int) -> None:
        modules[row][col] = value
        roles[row][col] = ROLE_FORMAT

    for i in range(6):
        put(i, 8, (bits >> i) & 1)
    put(7, 8, (bits >> 6) & 1)
    put(8, 8, (bits >> 7) & 1)
    put(8, 7, (bits >> 8) & 1)
    for i in range(9, 15):
        put(8, 14 - i, (bits >> i) & 1)
    for i in range(8):
        put(8, size - 1 - i, (bits >> i) & 1)
    for i in range(8, 15):
        put(size - 15 + i, 8, (bits >> i) & 1)
    put(size - 8, 8, 1)  # the always-dark module


# --------------------------------------------------------------------- penalties
def _finder_penalty_count(history: List[int]) -> int:
    n = history[1]
    core = n > 0 and history[2] == n and history[3] == n * 3 and history[4] == n and history[5] == n
    return int(core and history[0] >= n * 4 and history[6] >= n) + \
        int(core and history[6] >= n * 4 and history[0] >= n)


def _finder_penalty_add(length: int, history: List[int], size: int) -> None:
    if history[0] == 0:
        length += size
    history[1:] = history[:-1]
    history[0] = length


def _finder_penalty_finish(color: int, length: int, history: List[int], size: int) -> int:
    if color:
        _finder_penalty_add(length, history, size)
        length = 0
    length += size
    _finder_penalty_add(length, history, size)
    return _finder_penalty_count(history)


def _scan_line(values: Sequence[int], size: int) -> int:
    result = 0
    color = 0
    run = 0
    history = [0] * 7
    for value in values:
        if value == color:
            run += 1
            if run == 5:
                result += PENALTY_N1
            elif run > 5:
                result += 1
        else:
            _finder_penalty_add(run, history, size)
            if not color:
                result += _finder_penalty_count(history) * PENALTY_N3
            color = value
            run = 1
    return result + _finder_penalty_finish(color, run, history, size) * PENALTY_N3


def penalty(modules: Sequence[Sequence[int]], size: int) -> int:
    """Total penalty score of a matrix (the lower the better)."""
    result = 0
    for r in range(size):
        result += _scan_line(modules[r], size)
    for c in range(size):
        result += _scan_line([modules[r][c] for r in range(size)], size)
    for r in range(size - 1):
        row_a, row_b = modules[r], modules[r + 1]
        for c in range(size - 1):
            v = row_a[c]
            if v == row_a[c + 1] == row_b[c] == row_b[c + 1]:
                result += PENALTY_N2
    dark = sum(sum(row) for row in modules)
    total = size * size
    k = (abs(dark * 20 - total * 10) + total - 1) // total - 1
    return result + k * PENALTY_N4


_penalty = penalty
