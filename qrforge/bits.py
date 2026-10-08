"""A tiny MSB-first bit buffer."""

from __future__ import annotations

from typing import Iterable


class BitBuffer:
    __slots__ = ("_data", "length")

    def __init__(self) -> None:
        self._data = bytearray()
        self.length = 0

    def append(self, value: int, nbits: int) -> None:
        if nbits < 0 or value >> nbits:
            raise ValueError(f"cannot store {value} in {nbits} bits")
        for i in range(nbits - 1, -1, -1):
            bit = (value >> i) & 1
            if not (self.length & 7):
                self._data.append(0)
            self._data[self.length >> 3] |= bit << (7 - (self.length & 7))
            self.length += 1

    def append_all(self, bits: Iterable[bool]) -> None:
        for b in bits:
            self.append(1 if b else 0, 1)

    def bit(self, index: int) -> int:
        return (self._data[index >> 3] >> (7 - (index & 7))) & 1

    def to_bytes(self) -> bytes:
        return bytes(self._data)

    def __len__(self) -> int:
        return self.length

    def __repr__(self) -> str:  # pragma: no cover - debugging helper
        return "".join(str(self.bit(i)) for i in range(min(self.length, 64)))
