"""quantize 三份输出（palette.txt / indices.pgm / report.json）的写与读。"""

import json
import os

from .ppm import InputError


def write_outputs(out_dir, image_name, width, height, colors_limit, result, elapsed_ms):
    """写 palette.txt、indices.pgm、report.json，返回报告 dict。"""
    os.makedirs(out_dir, exist_ok=True)

    palette_path = os.path.join(out_dir, "palette.txt")
    lines = [str(len(result.palette))]
    lines += [f"{r} {g} {b}" for r, g, b in result.palette]
    with open(palette_path, "w", encoding="ascii", newline="\n") as fh:
        fh.write("\n".join(lines) + "\n")

    pgm_path = os.path.join(out_dir, "indices.pgm")
    with open(pgm_path, "wb") as fh:
        fh.write(f"P5\n{width} {height}\n255\n".encode("ascii"))
        fh.write(result.indices)

    report = {
        "image": image_name,
        "width": width,
        "height": height,
        "pixels": width * height,
        "colors_limit": colors_limit,
        "colors_used": len(result.palette),
        "mean_abs_error": result.mean_abs_error,
        "max_pixel_error": result.max_pixel_error,
        "elapsed_ms": elapsed_ms,
    }
    report_path = os.path.join(out_dir, "report.json")
    with open(report_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(_report_json(report))
    return report


def _report_json(report):
    """固定键序、mean_abs_error 保留 3 位小数的 JSON 文本。"""
    image = json.dumps(report["image"], ensure_ascii=False)
    lines = [
        "{",
        f'  "image": {image},',
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


def read_palette(path):
    try:
        with open(path, "r", encoding="ascii") as fh:
            lines = fh.read().split("\n")
    except (OSError, UnicodeDecodeError) as exc:
        raise InputError(f"无法读取调色板 {path}: {exc}") from exc
    if not lines or lines[-1] != "":
        raise InputError(f"{path}: 末行缺少换行")
    lines = lines[:-1]
    if not lines:
        raise InputError(f"{path}: 空文件")
    try:
        count = int(lines[0])
        entries = [tuple(int(v) for v in ln.split(" ")) for ln in lines[1:]]
    except ValueError as exc:
        raise InputError(f"{path}: 内容不合法: {exc}") from exc
    if count != len(entries) or count < 1:
        raise InputError(f"{path}: 条目数与首行不符")
    for e in entries:
        if len(e) != 3 or not all(0 <= v <= 255 for v in e):
            raise InputError(f"{path}: 条目必须是 0-255 的 r g b")
    return entries


def read_pgm(path):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise InputError(f"无法读取索引图 {path}: {exc}") from exc
    parts = data.split(b"\n", 3)
    if len(parts) < 4 or parts[0] != b"P5":
        raise InputError(f"{path}: 不是规范形式的 P5 PGM")
    dims = parts[1].split()
    if len(dims) != 2 or not all(d.isdigit() for d in dims) or parts[2] != b"255":
        raise InputError(f"{path}: 头部不合法")
    width, height = int(dims[0]), int(dims[1])
    body = parts[3]
    if len(body) != width * height:
        raise InputError(f"{path}: 数据长度与宽高不符")
    return width, height, body


def read_report(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            report = json.load(fh)
    except (OSError, ValueError) as exc:
        raise InputError(f"无法读取报告 {path}: {exc}") from exc
    required = {
        "image", "width", "height", "pixels", "colors_limit",
        "colors_used", "mean_abs_error", "max_pixel_error", "elapsed_ms",
    }
    if not isinstance(report, dict) or not required.issubset(report):
        raise InputError(f"{path}: 缺少必要字段")
    return report
