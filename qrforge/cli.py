"""Command line interface: ``python -m qrforge``."""

from __future__ import annotations

import argparse
import sys

from . import presets, shaders, shapes
from .api import QR


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="qrforge",
        description="Generate and style QR codes from the command line.")
    parser.add_argument("data", nargs="?", help="the text to encode")
    parser.add_argument("-o", "--output", help="output file (.png/.svg/.pdf/.txt/.html)")
    parser.add_argument("-p", "--preset", help="a named style; see --list-presets")
    parser.add_argument("-e", "--ec", default="M", choices="LMQH", help="error correction")
    parser.add_argument("-v", "--version", type=int, help="force QR version (1-40)")
    parser.add_argument("-m", "--mask", type=int, help="force mask (0-7)")
    parser.add_argument("-s", "--scale", type=int, default=10, help="pixels per module")
    parser.add_argument("--shape", help="module shape; see --list-shapes")
    parser.add_argument("--fg", help="foreground colour or comma separated gradient")
    parser.add_argument("--bg", help="background colour (or 'none' for transparent)")
    parser.add_argument("--logo", help="path to a logo image")
    parser.add_argument("--shader", action="append", help="shader, repeatable; see --list-shaders")
    parser.add_argument("--seed", type=int, help="seed for randomised effects")
    parser.add_argument("--terminal", action="store_true", help="print to the terminal")
    parser.add_argument("--info", action="store_true", help="show encoding info")
    parser.add_argument("--list-presets", action="store_true")
    parser.add_argument("--list-shapes", action="store_true")
    parser.add_argument("--list-shaders", action="store_true")
    parser.add_argument("--version-info", action="store_true", help="print the library version")
    return parser


def main(argv=None) -> int:
    args = build_parser().parse_args(argv)

    if args.list_presets:
        print(", ".join(presets.names()))
        return 0
    if args.list_shapes:
        print(", ".join(shapes.names()))
        return 0
    if args.list_shaders:
        print(", ".join(shaders.names()))
        return 0
    if args.version_info:
        from . import __version__
        print(__version__)
        return 0

    if not args.data:
        build_parser().print_help()
        return 1

    options = {"ec": args.ec, "version": args.version, "mask": args.mask}
    options = {k: v for k, v in options.items() if v is not None}
    qr = QR(args.data, **options)

    style = {}
    if args.shape:
        style["module_shape"] = args.shape.split(",") if "," in args.shape else args.shape
    if args.fg:
        style["fg"] = args.fg.split(",") if "," in args.fg else args.fg
    if args.bg:
        style["bg"] = None if args.bg.lower() in ("none", "transparent") else args.bg
    if args.logo:
        style["logo"] = args.logo
    if args.shader:
        style["shaders"] = tuple(args.shader)
    if args.seed is not None:
        style["seed"] = args.seed

    if args.info:
        for key, value in qr.info().items():
            print(f"{key}: {value}")
        return 0

    if args.terminal or not args.output:
        print(qr.terminal(args.preset, **style))
        return 0

    qr.save(args.output, args.preset, scale=args.scale, **style)
    print(f"saved {args.output}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
