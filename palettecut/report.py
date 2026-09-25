"""quantize 子命令：读图、量化、写 palette.txt / indices.pgm / report.json。"""

import json
import os
import time

from .ppmio import pgm_bytes, read_ppm
from .quantizer import quantize

PALETTE_FILE = "palette.txt"
INDICES_FILE = "indices.pgm"
REPORT_FILE = "report.json"


def palette_text(palette):
    lines = [str(len(palette))]
    lines.extend(f"{r} {g} {b}" for r, g, b in palette)
    return "\n".join(lines) + "\n"


def report_text(report):
    """按固定键序拼 JSON；mean_abs_error 固定 3 位小数。"""
    lines = [
        "{",
        f'  "image": {json.dumps(report["image"], ensure_ascii=False)},',
        f'  "width": {report["width"]},',
        f'  "height": {report["height"]},',
        f'  "pixels": {report["pixels"]},',
        f'  "colors_limit": {report["colors_limit"]},',
        f'  "colors_used": {report["colors_used"]},',
        f'  "mean_abs_error": {report["mean_abs_error"]:.3f},',
        f'  "max_pixel_error": {report["max_pixel_error"]},',
        f'  "elapsed_ms": {report["elapsed_ms"]}',
        "}",
    ]
    return "\n".join(lines) + "\n"


def run_quantize(ppm_path, colors_limit, out_dir):
    """执行量化并写出三份产物，返回 stdout 汇总行。

    输入不可用抛 ImageFormatError；所有内容先在内存里备好，
    最后一步才落盘，失败时不留半成品。
    """
    started = time.perf_counter()
    width, height, raw = read_ppm(ppm_path)
    palette, indices, mean_abs_error, max_pixel_error = quantize(
        raw, width, height, colors_limit
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    report = {
        "image": os.path.basename(ppm_path),
        "width": width,
        "height": height,
        "pixels": width * height,
        "colors_limit": colors_limit,
        "colors_used": len(palette),
        "mean_abs_error": mean_abs_error,
        "max_pixel_error": max_pixel_error,
        "elapsed_ms": elapsed_ms,
    }
    palette_out = palette_text(palette).encode("ascii")
    indices_out = pgm_bytes(width, height, indices)
    report_out = report_text(report).encode("utf-8")
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, PALETTE_FILE), "wb") as fh:
        fh.write(palette_out)
    with open(os.path.join(out_dir, INDICES_FILE), "wb") as fh:
        fh.write(indices_out)
    with open(os.path.join(out_dir, REPORT_FILE), "wb") as fh:
        fh.write(report_out)
    return (
        f"colors_used={len(palette)}"
        f" mean_abs_error={mean_abs_error:.3f}"
        f" max_pixel_error={max_pixel_error}"
        f" elapsed_ms={elapsed_ms}"
    )
