"""Galois field GF(256) arithmetic and Reed-Solomon coding.

The QR code specification uses GF(256) with the primitive polynomial
``x^8 + x^4 + x^3 + x^2 + 1`` (0x11D).  Everything in this module is
pure Python and dependency free.
"""

from __future__ import annotations

from typing import Dict, List, Sequence, Tuple

PRIMITIVE_POLY = 0x11D

# ---------------------------------------------------------------- lookup tables
EXP: List[int] = [1] * 512
LOG: List[int] = [0] * 256


def _build_tables() -> None:
    x = 1
    for i in range(255):
        EXP[i] = x
        LOG[x] = i
        x <<= 1
        if x & 0x100:
            x ^= PRIMITIVE_POLY
    for i in range(255, 512):  # duplicate so a*b needs no modulo
        EXP[i] = EXP[i - 255]


_build_tables()


def mul(a: int, b: int) -> int:
    """Multiply two field elements."""
    if a == 0 or b == 0:
        return 0
    return EXP[LOG[a] + LOG[b]]


def div(a: int, b: int) -> int:
    if b == 0:
        raise ZeroDivisionError("division by zero in GF(256)")
    if a == 0:
        return 0
    return EXP[(LOG[a] - LOG[b]) % 255]


def inv(a: int) -> int:
    if a == 0:
        raise ZeroDivisionError("zero has no inverse in GF(256)")
    return EXP[255 - LOG[a]]


def pow_(a: int, n: int) -> int:
    if a == 0:
        return 0
    return EXP[(LOG[a] * n) % 255]


# ------------------------------------------------------------------ polynomials
# Polynomials are lists of coefficients ordered from the highest power down to
# the constant term, e.g. ``x^2 + 1`` -> ``[1, 0, 1]``.


def poly_mul(p: Sequence[int], q: Sequence[int]) -> List[int]:
    out = [0] * (len(p) + len(q) - 1)
    for i, a in enumerate(p):
        if a == 0:
            continue
        la = LOG[a]
        for j, b in enumerate(q):
            if b:
                out[i + j] ^= EXP[la + LOG[b]]
    return out


def poly_eval(p: Sequence[int], x: int) -> int:
    """Horner evaluation of ``p`` at ``x``."""
    acc = 0
    for coef in p:
        acc = mul(acc, x) ^ coef
    return acc


def generator_poly(degree: int) -> List[int]:
    """Reed-Solomon generator polynomial for ``degree`` error-correction bytes."""
    g: List[int] = [1]
    for i in range(degree):
        g = poly_mul(g, (1, EXP[i]))
    return g


_GEN_CACHE: Dict[int, List[int]] = {}


def rs_encode(data: Sequence[int], ec_len: int) -> List[int]:
    """Return the ``ec_len`` Reed-Solomon parity bytes for ``data``."""
    if ec_len not in _GEN_CACHE:
        _GEN_CACHE[ec_len] = generator_poly(ec_len)
    gen = _GEN_CACHE[ec_len]
    res = list(data) + [0] * ec_len
    for i in range(len(data)):
        coef = res[i]
        if coef == 0:
            continue
        log_coef = LOG[coef]
        for j in range(1, len(gen)):  # gen[0] is always 1
            g = gen[j]
            if g:
                res[i + j] ^= EXP[log_coef + LOG[g]]
    return res[len(data):]


# ------------------------------------------------------------------- RS decoding
# Used by :mod:`qrforge.verify` to prove (and demonstrate) error correction.


def _syndromes(msg: Sequence[int], nsym: int) -> List[int]:
    return [poly_eval(msg, EXP[i]) for i in range(nsym)]


def _poly_scale(p: Sequence[int], k: int) -> List[int]:
    return [mul(c, k) for c in p]


def _poly_add(p: Sequence[int], q: Sequence[int]) -> List[int]:
    out = [0] * max(len(p), len(q))
    for i, c in enumerate(p):
        out[i + len(out) - len(p)] ^= c
    for i, c in enumerate(q):
        out[i + len(out) - len(q)] ^= c
    return out


def _berlekamp_massey(synd: Sequence[int], nsym: int) -> List[int]:
    """Berlekamp-Massey: returns the error locator (highest power first)."""
    err_loc = [1]
    old_loc = [1]
    for i in range(nsym):
        delta = synd[i]
        for j in range(1, len(err_loc)):
            delta ^= mul(err_loc[-(j + 1)], synd[i - j])
        old_loc = old_loc + [0]
        if delta != 0:
            if len(old_loc) > len(err_loc):
                new_loc = _poly_scale(old_loc, delta)
                old_loc = _poly_scale(err_loc, inv(delta))
                err_loc = new_loc
            err_loc = _poly_add(err_loc, _poly_scale(old_loc, delta))
    while len(err_loc) > 1 and err_loc[0] == 0:
        err_loc.pop(0)
    return err_loc


def _chien_search(err_loc: Sequence[int], msg_len: int) -> List[int]:
    """Roots of the locator give the damaged symbol positions."""
    expected = len(err_loc) - 1
    positions = []
    for i in range(255):
        if poly_eval(err_loc, EXP[i]) == 0:
            pos = (255 - i) % 255
            if pos < msg_len:
                positions.append(pos)
    if len(positions) != expected:
        raise ValueError("could not locate all errors (message too damaged)")
    return sorted(positions)


def _solve_magnitudes(synd: Sequence[int], positions: Sequence[int]) -> List[int]:
    """Solve ``sum_k Y_k * X_k**j = S_j`` for the error magnitudes ``Y_k``.

    A tiny Gaussian elimination over GF(256) -- the system is at most 15x30,
    so this stays fast and is far easier to trust than Forney's formula.
    """
    n = len(positions)
    rows = []
    for j in range(len(synd)):
        row = [EXP[(positions[k] * j) % 255] for k in range(n)]
        row.append(synd[j])
        rows.append(row)
    pivot_row = 0
    for col in range(n):
        sel = next((r for r in range(pivot_row, len(rows)) if rows[r][col] != 0), None)
        if sel is None:
            raise ValueError("singular system while correcting errors")
        rows[pivot_row], rows[sel] = rows[sel], rows[pivot_row]
        scale = inv(rows[pivot_row][col])
        rows[pivot_row] = [mul(v, scale) for v in rows[pivot_row]]
        for r in range(len(rows)):
            if r != pivot_row and rows[r][col]:
                factor = rows[r][col]
                rows[r] = [a ^ mul(factor, b) for a, b in zip(rows[r], rows[pivot_row])]
        pivot_row += 1
    return [rows[k][n] for k in range(n)]


def rs_correct(msg: List[int], nsym: int) -> Tuple[List[int], int]:
    """Correct up to ``nsym // 2`` errors in ``msg`` in place.

    Returns the message and the number of corrected symbols.
    Raises :class:`ValueError` when the damage is beyond repair.
    """
    synd = _syndromes(msg, nsym)
    if max(synd) == 0:
        return msg, 0
    err_loc = _berlekamp_massey(synd, nsym)
    if (len(err_loc) - 1) * 2 > nsym:
        raise ValueError("too many errors to correct")
    exponents = _chien_search(err_loc, len(msg))
    magnitudes = _solve_magnitudes(synd, exponents)
    for exponent, mag in zip(exponents, magnitudes):
        # exponents count from the highest power; array index 0 is highest power
        msg[len(msg) - 1 - exponent] ^= mag
    if max(_syndromes(msg, nsym)) != 0:
        raise ValueError("message could not be corrected")
    return msg, len(exponents)

