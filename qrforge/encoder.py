"""Data analysis, segmentation and Reed-Solomon block structuring.

Turns arbitrary bytes/strings into the final codeword stream that is written
into the symbol matrix.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import List, Sequence, Tuple

from .bits import BitBuffer
from .gf import rs_encode
from .tables import (
    ALNUM_CHARS,
    MODE_ALNUM,
    MODE_BYTE,
    MODE_NUMERIC,
    block_layout,
    count_bits,
    data_codewords,
)
from .exceptions import DataTooLong

_ALNUM_SET = frozenset(ALNUM_CHARS)
_DIGITS = frozenset("0123456789")
_MODES = ("numeric", "alnum", "byte")
_MODE_INDICATOR = {"numeric": MODE_NUMERIC, "alnum": MODE_ALNUM, "byte": MODE_BYTE}


@dataclass(frozen=True)
class Segment:
    mode: str
    text: str

    def __len__(self) -> int:
        return len(self.text)


def normalize(data) -> str:
    """Return the raw payload bytes as a latin-1 representable string.

    ``bytes`` are used verbatim; ``str`` is UTF-8 encoded when it contains
    non-ASCII characters (the convention every modern scanner expects).
    """
    if isinstance(data, (bytes, bytearray, memoryview)):
        return bytes(data).decode("latin-1")
    if not isinstance(data, str):
        data = str(data)
    if data.isascii():
        return data
    return data.encode("utf-8").decode("latin-1")


def _payload_bits(mode: str, n: int) -> int:
    if mode == "numeric":
        extra = n % 3
        return 10 * (n // 3) + (0 if extra == 0 else 4 if extra == 1 else 7)
    if mode == "alnum":
        return 11 * (n // 2) + (6 if n % 2 else 0)
    return 8 * n


def _valid(mode: str, ch: str) -> bool:
    if mode == "numeric":
        return ch in _DIGITS
    if mode == "alnum":
        return ch in _ALNUM_SET
    return True


def segment(text: str, version: int, mode: str = "auto") -> List[Segment]:
    """Split ``text`` into QR mode segments.

    ``mode`` may be ``auto`` (a small dynamic program finds the cheapest mix of
    numeric / alphanumeric / byte segments) or one of ``numeric``, ``alnum``,
    ``byte`` to force a single mode.
    """
    if mode != "auto":
        if mode not in _MODES:
            raise ValueError(f"unknown mode {mode!r}")
        for ch in text:
            if not _valid(mode, ch):
                raise ValueError(f"{ch!r} cannot be encoded in {mode} mode")
        return [Segment(mode, text)]

    n = len(text)
    if n == 0:
        return []

    # Exact segmentation by dynamic programming.  The cost of a segment
    # [i, j) is ``dp_min[i] + header + payload(j - i)`` and every payload is
    # linear in the length plus a remainder term, so the minimum over ``i`` can
    # be tracked with a monotonic deque instead of a quadratic scan.
    INF = float("inf")
    header = [4 + count_bits(m, version) for m in _MODES]
    ok = [[ch in _DIGITS for ch in text],
          [ch in _ALNUM_SET for ch in text],
          [True] * n]

    dp = [[INF] * 3 for _ in range(n + 1)]
    parent: List[List[int]] = [[-1] * 3 for _ in range(n + 1)]
    dp_min = [INF] * (n + 1)
    dp_min[0] = 0

    # window state: three deques for numeric (i % 3), two for alnum (i % 2),
    # one for byte mode.  Entries are (scaled cost, start index).
    dq_num = [deque() for _ in range(3)]
    dq_alnum = [deque() for _ in range(2)]
    dq_byte = deque()
    lo = [0, 0, 0]
    NUM_ADJ = (0, 2, 1)  # extra thirds of a bit for L % 3 == 0, 1, 2

    def push(dq, value: int, index: int) -> None:
        while dq and dq[-1][0] >= value:
            dq.pop()
        dq.append((value, index))

    def prune(dq, limit: int):
        while dq and dq[0][1] < limit:
            dq.popleft()

    for j in range(1, n + 1):
        i = j - 1
        if dp_min[i] != INF:
            push(dq_num[i % 3], 3 * dp_min[i] - 10 * i, i)
            push(dq_alnum[i % 2], 2 * dp_min[i] - 11 * i, i)
            push(dq_byte, dp_min[i] - 8 * i, i)
        for m in range(3):
            if not ok[m][i]:
                lo[m] = j
        prune(dq_num[0], lo[0]); prune(dq_num[1], lo[0]); prune(dq_num[2], lo[0])
        prune(dq_alnum[0], lo[1]); prune(dq_alnum[1], lo[1])
        prune(dq_byte, lo[2])

        best_cost = INF
        best_i = -1
        for r in range(3):
            if dq_num[r]:
                value, index = dq_num[r][0]
                cost = (value + 3 * header[0] + 10 * j + NUM_ADJ[(j - r) % 3]) // 3
                if cost < best_cost:
                    best_cost, best_i = cost, index
        dp[j][0], parent[j][0] = best_cost, best_i

        best_cost = INF
        best_i = -1
        for parity in range(2):
            if dq_alnum[parity]:
                value, index = dq_alnum[parity][0]
                cost = (value + 2 * header[1] + 11 * j + (0 if parity == j % 2 else 1)) // 2
                if cost < best_cost:
                    best_cost, best_i = cost, index
        dp[j][1], parent[j][1] = best_cost, best_i

        best_cost = INF
        best_i = -1
        if dq_byte:
            value, index = dq_byte[0]
            best_cost, best_i = value + header[2] + 8 * j, index
        dp[j][2], parent[j][2] = best_cost, best_i

        dp_min[j] = min(dp[j])

    end_mode = min(range(3), key=lambda m: dp[n][m])
    if dp[n][end_mode] == INF:  # pragma: no cover - defensive
        raise DataTooLong("could not segment the input")
    out: List[Segment] = []
    j, m = n, end_mode
    while j > 0:
        i = parent[j][m]
        out.append(Segment(_MODES[m], text[i:j]))
        j = i
        if j > 0:
            m = min(range(3), key=lambda mm: dp[j][mm])
    out.reverse()
    return out


def segment_bits(segments: Sequence[Segment], version: int) -> int:
    total = 0
    for seg in segments:
        total += 4 + count_bits(seg.mode, version) + _payload_bits(seg.mode, len(seg))
    return total


def capacity_bits(version: int, level: str) -> int:
    return data_codewords(version, level) * 8


def pick_version(text: str, level: str, mode: str = "auto",
                 min_version: int = 1, max_version: int = 40) -> Tuple[int, List[Segment]]:
    """Return the smallest version that fits ``text`` plus its segmentation."""
    # cheap lower bound so we do not run the segmentation for tiny versions
    floor = 1
    for v in range(1, 41):
        if capacity_bits(v, level) >= 4 + 8 + 3.4 * len(text):
            floor = v
            break
    floor = max(floor, min_version)
    for version in range(floor, max_version + 1):
        segs = segment(text, version, mode)
        if segment_bits(segs, version) + 4 <= capacity_bits(version, level):
            return version, segs
    raise DataTooLong(
        f"data does not fit in version {max_version} at error correction level {level}"
    )


def build_data_bits(segments: Sequence[Segment], version: int, level: str) -> bytes:
    """Encode segments into the padded data codewords for one symbol."""
    total = capacity_bits(version, level)
    bits = BitBuffer()
    for seg in segments:
        bits.append(_MODE_INDICATOR[seg.mode], 4)
        bits.append(len(seg), count_bits(seg.mode, version))
        if seg.mode == "numeric":
            digits = seg.text
            for i in range(0, len(digits) - 2, 3):
                bits.append(int(digits[i:i + 3]), 10)
            rest = digits[len(digits) // 3 * 3:]
            if len(rest) == 2:
                bits.append(int(rest), 7)
            elif len(rest) == 1:
                bits.append(int(rest), 4)
        elif seg.mode == "alnum":
            chars = seg.text
            for i in range(0, len(chars) - 1, 2):
                value = ALNUM_CHARS.index(chars[i]) * 45 + ALNUM_CHARS.index(chars[i + 1])
                bits.append(value, 11)
            if len(chars) % 2:
                bits.append(ALNUM_CHARS.index(chars[-1]), 6)
        else:
            for byte in seg.text.encode("iso-8859-1"):
                bits.append(byte, 8)

    # terminator, byte alignment, pad codewords
    bits.append(0, min(4, total - bits.length))
    bits.append(0, (8 - bits.length % 8) % 8)
    data = bytearray(bits.to_bytes())
    pad = (0xEC, 0x11)
    i = 0
    while len(data) < total // 8:
        data.append(pad[i % 2])
        i += 1
    return bytes(data)


def interleave(data: Sequence[int], version: int, level: str) -> List[int]:
    """Split into blocks, compute Reed-Solomon parity and interleave."""
    ec_len, groups = block_layout(version, level)
    blocks: List[Tuple[List[int], List[int]]] = []
    offset = 0
    for count, per_block in groups:
        for _ in range(count):
            chunk = list(data[offset:offset + per_block])
            offset += per_block
            blocks.append((chunk, rs_encode(chunk, ec_len)))
    if offset != len(data):  # pragma: no cover - table/encoder mismatch guard
        raise ValueError("block layout does not match the data length")

    out: List[int] = []
    max_data = max(len(b[0]) for b in blocks)
    for i in range(max_data):
        for chunk, _ in blocks:
            if i < len(chunk):
                out.append(chunk[i])
    for i in range(ec_len):
        for _, ec in blocks:
            out.append(ec[i])
    return out


def encode_codewords(text: str, version: int, level: str,
                     segments: Sequence[Segment] | None = None) -> List[int]:
    if segments is None:
        segments = segment(text, version)
    return interleave(build_data_bits(segments, version, level), version, level)
