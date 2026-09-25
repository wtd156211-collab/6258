"""命令行入口：quantize 与 page 两个子命令。"""

import argparse
import os
import sys
import time

from .files import read_palette, read_pgm, read_report, write_outputs
from .page import build_html
from .ppm import InputError, read_ppm
from .quantize import quantize


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="palettecut", description="调色板量化：位图 -> 调色板 + 索引图"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    q = sub.add_parser("quantize", help="量化一张 P6 PPM")
    q.add_argument("input", help="输入 .ppm（P6，最大值 255）")
    q.add_argument("colors", type=int, help="颜色数上限（1-256）")
    q.add_argument("--out", required=True, help="输出目录（不存在则创建）")

    p = sub.add_parser("page", help="由 quantize 输出生成对比页面")
    p.add_argument("--ppm", required=True, help="原始输入 .ppm")
    p.add_argument("--dir", required=True, help="quantize 的输出目录")
    p.add_argument("--html", required=True, help="页面输出文件")
    return parser


def _cmd_quantize(args, parser):
    if not 1 <= args.colors <= 256:
        parser.error("颜色数上限必须是 1-256 的整数")
    try:
        start = time.perf_counter()
        width, height, pixels = read_ppm(args.input)
        result = quantize(pixels, args.colors)
        elapsed_ms = int((time.perf_counter() - start) * 1000)
    except InputError as exc:
        print(f"palettecut: {exc}", file=sys.stderr)
        return 1
    if elapsed_ms < 0:
        elapsed_ms = 0
    try:
        write_outputs(
            args.out,
            os.path.basename(args.input),
            width,
            height,
            args.colors,
            result,
            elapsed_ms,
        )
    except OSError as exc:
        print(f"palettecut: 无法写输出目录 {args.out}: {exc}", file=sys.stderr)
        return 1
    print(
        f"colors_used={len(result.palette)} "
        f"mean_abs_error={result.mean_abs_error:.3f} "
        f"max_pixel_error={result.max_pixel_error} "
        f"elapsed_ms={elapsed_ms}"
    )
    return 0


def _cmd_page(args):
    try:
        width, height, pixels = read_ppm(args.ppm)
        palette = read_palette(os.path.join(args.dir, "palette.txt"))
        gw, gh, indices = read_pgm(os.path.join(args.dir, "indices.pgm"))
        report = read_report(os.path.join(args.dir, "report.json"))
    except InputError as exc:
        print(f"palettecut: {exc}", file=sys.stderr)
        return 1
    if (gw, gh) != (width, height):
        print("palettecut: 索引图尺寸与原图不符", file=sys.stderr)
        return 1
    if len(palette) != report["colors_used"]:
        print("palettecut: 调色板条目数与报告不符", file=sys.stderr)
        return 1
    if len(palette) > 256 or any(i >= len(palette) for i in indices):
        print("palettecut: 索引越界", file=sys.stderr)
        return 1
    page = build_html(
        os.path.basename(args.ppm), width, height, pixels, palette, indices, report
    )
    parent = os.path.dirname(os.path.abspath(args.html))
    try:
        os.makedirs(parent, exist_ok=True)
        with open(args.html, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(page)
    except OSError as exc:
        print(f"palettecut: 无法写页面 {args.html}: {exc}", file=sys.stderr)
        return 1
    return 0


def main(argv=None):
    parser = _build_parser()
    args = parser.parse_args(argv)
    if args.command == "quantize":
        return _cmd_quantize(args, parser)
    return _cmd_page(args)
