"""Packaging entry-point for qrforge.

The CI workflow (``.github/workflows/build_and_publish.yaml``) replaces
``{{VERSION_PLACEHOLDER}}`` with the git tag before building, so the version in
this file is the single source of truth for releases.  For local development
the placeholder falls back to a dev version.
"""

import os

from setuptools import find_packages, setup

HERE = os.path.abspath(os.path.dirname(__file__))

VERSION = "{{VERSION_PLACEHOLDER}}"
if VERSION.startswith("{{"):
    VERSION = "1.0.0"  # local development fallback (CI replaces the token)

with open(os.path.join(HERE, "README.md"), encoding="utf-8") as fh:
    LONG_DESCRIPTION = fh.read()

setup(
    name="qrforge",
    version=VERSION,
    description=(
        "Generate and heavily customise QR codes (shapes, gradients, shaders, "
        "logos, textures) in pure Python; Pillow optional."
    ),
    long_description=LONG_DESCRIPTION,
    long_description_content_type="text/markdown",
    author="qrforge contributors",
    license="MIT",
    packages=find_packages(include=["qrforge", "qrforge.*"]),
    python_requires=">=3.8",
    install_requires=[],  # zero hard dependencies
    extras_require={
        "imaging": ["pillow>=9"],
    },
    entry_points={
        "console_scripts": [
            "qrforge=qrforge.cli:main",
        ],
    },
    keywords=["qr", "qrcode", "barcode", "svg", "png", "generator", "art"],
    classifiers=[
        "Development Status :: 5 - Production/Stable",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3 :: Only",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
        "Programming Language :: Python :: 3.12",
        "Topic :: Multimedia :: Graphics",
    ],
)
