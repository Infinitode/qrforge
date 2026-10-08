"""Exceptions raised by :mod:`qrforge`."""

from __future__ import annotations


class QRForgeError(Exception):
    """Base class for every error raised by this library."""


class DataTooLong(QRForgeError):
    """The payload does not fit into a QR symbol with the requested settings."""


class UnsupportedFeature(QRForgeError):
    """The requested feature needs an optional dependency that is missing."""


class StyleError(QRForgeError):
    """A style/shader option was invalid."""
