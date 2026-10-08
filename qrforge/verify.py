"""A small QR *decoder* used for round-trip verification and demos.

QRForge is a generator, but shipping a decoder lets the test-suite prove that
every symbol it produces actually scans, and lets you demonstrate error
correction by damaging a symbol and reading it back.

    >>> from qrforge import QR
    >>> qr = QR("hello")
    >>> qr.verify()
    'hello'
"""

from __future__ import annotations

from typing import List, Sequence, Tuple

from .bits import BitBuffer
from .gf import rs_correct
from .matrix import MASKS, ROLE_DATA, _place_function_patterns
from .tables import ALNUM_CHARS, LEVELS, LEVEL_BITS, block_layout, count_bits, version_size
from .exceptions import QRForgeError


def _popcount(x: int) -> int:
    return bin(x).count("1")


def read_format(matrix: Sequence[Sequence[int]], size: int) -> Tuple[str, int]:
    """Recover the error correction level and mask from the format information."""
    first = 0
    positions = [(i, 8) for i in range(6)] + [(7, 8), (8, 8), (8, 7)] + \
                [(8, 14 - i) for i in range(9, 15)]
    for i, (row, col) in enumerate(positions):
        first |= (matrix[row][col] & 1) << i
    second = 0
    positions2 = [(8, size - 1 - i) for i in range(8)] + [(size - 15 + i, 8) for i in range(8, 15)]
    for i, (row, col) in enumerate(positions2):
        second |= (matrix[row][col] & 1) << i

    for candidate, raw in ((first, first), (second, second)):
        for value in range(32):
            encoded = _encode_format(value)
            if _popcount(encoded ^ raw) <= 3:
                level = next(k for k, v in LEVEL_BITS.items() if v == value >> 3)
                return level, value & 0b111
    raise QRForgeError("could not read the format information")


def _encode_format(value5: int) -> int:
    v = value5 << 10
    for i in range(14, 9, -1):
        if v & (1 << i):
            v ^= 0b10100110111 << (i - 10)
    return ((value5 << 10) | v) ^ 0b101010000010010


def _function_roles(version: int) -> List[bytearray]:
    size = version_size(version)
    modules = [bytearray(size) for _ in range(size)]
    roles = [bytearray(size) for _ in range(size)]
    _place_function_patterns(size, version, modules, roles)
    return roles


def read_codewords(matrix: Sequence[Sequence[int]], size: int, version: int,
                   mask_id: int) -> List[int]:
    roles = _function_roles(version)
    fn = MASKS[mask_id]
    bits: List[int] = []
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
                value = matrix[row][col] & 1
                if fn(row, col):
                    value ^= 1
                bits.append(value)
        right -= 2
    codewords = []
    for i in range(0, len(bits) - 7, 8):
        byte = 0
        for bit in bits[i:i + 8]:
            byte = (byte << 1) | bit
        codewords.append(byte)
    return codewords


def deinterleave(codewords: Sequence[int], version: int, level: str) -> List[List[int]]:
    ec_len, groups = block_layout(version, level)
    blocks: List[List[int]] = []
    sizes: List[int] = []
    for count, per_block in groups:
        for _ in range(count):
            blocks.append([])
            sizes.append(per_block)
    index = 0
    max_data = max(sizes)
    for i in range(max_data):
        for b, block in enumerate(blocks):
            if i < sizes[b]:
                block.append(codewords[index])
                index += 1
    for i in range(ec_len):
        for block in blocks:
            block.append(codewords[index])
            index += 1
    return blocks


def _read_text(data: Sequence[int], version: int) -> str:
    bits = BitBuffer()
    for byte in data:
        bits.append(byte, 8)
    pos = 0

    def take(n: int) -> int:
        nonlocal pos
        value = 0
        for _ in range(n):
            value = (value << 1) | (bits.bit(pos) if pos < bits.length else 0)
            pos += 1
        return value

    out = bytearray()
    while pos + 4 <= bits.length:
        mode = take(4)
        if mode == 0:
            break
        if mode == 0b0001:  # numeric
            n = take(count_bits("numeric", version))
            digits = ""
            while n >= 3:
                digits += f"{take(10):03d}"
                n -= 3
            if n == 2:
                digits += f"{take(7):02d}"
            elif n == 1:
                digits += str(take(4))
            out += digits.encode("ascii")
        elif mode == 0b0010:  # alphanumeric
            n = take(count_bits("alnum", version))
            chars = ""
            while n >= 2:
                value = take(11)
                chars += ALNUM_CHARS[value // 45] + ALNUM_CHARS[value % 45]
                n -= 2
            if n == 1:
                chars += ALNUM_CHARS[take(6)]
            out += chars.encode("ascii")
        elif mode == 0b0100:  # byte
            n = take(count_bits("byte", version))
            for _ in range(n):
                out.append(take(8))
        elif mode == 0b0111:  # ECI header, assignment 26 == UTF-8, safe to skip
            first = take(8)
            if first & 0b10000000:
                take(8)
            if first & 0b11000000 == 0b11000000:
                take(16)
        else:
            break
    for encoding in ("utf-8", "iso-8859-1"):
        try:
            return out.decode(encoding)
        except UnicodeDecodeError:
            continue
    return out.decode("iso-8859-1", errors="replace")


class DecodeResult:
    """Outcome of decoding a symbol."""

    __slots__ = ("text", "version", "level", "mask", "corrected")

    def __init__(self, text: str, version: int, level: str, mask: int, corrected: int) -> None:
        self.text = text
        self.version = version
        self.level = level
        self.mask = mask
        self.corrected = corrected

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return (f"DecodeResult(text={self.text!r}, version={self.version}, "
                f"level={self.level!r}, mask={self.mask}, corrected={self.corrected})")


def decode(matrix: Sequence[Sequence[int]]) -> DecodeResult:
    """Decode a matrix of 0/1 rows back into text."""
    size = len(matrix)
    version = (size - 17) // 4
    if version_size(version) != size or not 1 <= version <= 40:
        raise QRForgeError(f"{size}x{size} is not a valid QR symbol size")
    level, mask_id = read_format(matrix, size)
    codewords = read_codewords(matrix, size, version, mask_id)
    blocks = deinterleave(codewords, version, level)
    ec_len = block_layout(version, level)[0]
    corrected = 0
    data: List[int] = []
    for block in blocks:
        block, fixed = rs_correct(list(block), ec_len)
        corrected += fixed
        data.extend(block[:len(block) - ec_len])
    return DecodeResult(_read_text(data, version), version, level, mask_id, corrected)
