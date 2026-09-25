"""命令行入口：python -m palettecut quantize|page。

退出码：0 成功；1 输入不可用（文件缺失、头不合法、目录里缺输出）；
2 用法错误。非 0 时不写半成品。
"""

import argparse
import sys

from .page import run_page
from .ppmio import ImageFormatError
from .report import run_quantize


def _build_parser():
    parser = argparse.ArgumentParser(
        prog="palettecut", description="确定性调色板量化：PPM(P6) -> 调色板 + 索引图"
    )
    sub = parser.add_subparsers(dest="command", required=True)

    quantize = sub.add_parser("quantize", help="量化一张 PPM 并写出产物")
    quantize.add_argument("input", help="输入 PPM 文件路径")
    quantize.add_argument("colors", type=int, help="颜色数上限（1-256 的整数）")
    quantize.add_argument("--out", required=True, help="输出目录（不存在则创建）")

    page = sub.add_parser("page", help="用 quantize 的产出生成对比页面")
    page.add_argument("--ppm", required=True, help="原图 PPM 文件路径")
    page.add_argument("--dir", required=True, help="quantize 的输出目录")
    page.add_argument("--html", required=True, help="页面输出文件路径")
    return parser


def main(argv=None):
    args = _build_parser().parse_args(argv)
    if args.command == "quantize":
        if not 1 <= args.colors <= 256:
            print("palettecut: 颜色上限必须是 1-256 的整数", file=sys.stderr)
            return 2
        try:
            summary = run_quantize(args.input, args.colors, args.out)
        except (ImageFormatError, OSError) as exc:
            print(f"palettecut: {exc}", file=sys.stderr)
            return 1
        print(summary)
        return 0
    try:
        run_page(args.ppm, args.dir, args.html)
    except (ImageFormatError, OSError) as exc:
        print(f"palettecut: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
