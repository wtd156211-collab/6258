"""page 子命令：用 quantize 的产出生成自包含并排对比页面。

页面只消费 palette.txt / indices.pgm / report.json 与原图 PPM，
量化图由调色板 + 索引图在 Canvas 上重建，误差与耗时直接照抄
report.json，不在页面里重新选色或重算误差。
"""

import base64
import json
import os
from string import Template

from .ppmio import ImageFormatError, read_ppm
from .report import INDICES_FILE, PALETTE_FILE, REPORT_FILE

HTML_TEMPLATE = Template("""<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>palettecut 对比 - $image</title>
<style>
  body { font-family: system-ui, sans-serif; margin: 24px; background: #f5f5f5; color: #222; }
  h1 { font-size: 18px; }
  .row { display: flex; gap: 16px; flex-wrap: wrap; }
  figure { margin: 0; background: #fff; padding: 8px; border: 1px solid #ddd; }
  figcaption { font-size: 13px; color: #555; margin-bottom: 6px; }
  canvas { display: block; image-rendering: pixelated; max-width: 100%; }
  dl.metrics { display: flex; gap: 24px; margin: 16px 0 0; padding: 12px 16px;
               background: #fff; border: 1px solid #ddd; width: fit-content; }
  dl.metrics div { text-align: center; }
  dl.metrics dt { font-size: 12px; color: #666; }
  dl.metrics dd { margin: 4px 0 0; font-size: 18px; font-variant-numeric: tabular-nums; }
</style>
</head>
<body>
<h1>palettecut 量化对比：$image</h1>
<div class="row">
  <figure>
    <figcaption>原图（$width × $height）</figcaption>
    <canvas id="original" width="$width" height="$height"></canvas>
  </figure>
  <figure>
    <figcaption>量化结果（$colors_used 色）</figcaption>
    <canvas id="quantized" width="$width" height="$height"></canvas>
  </figure>
</div>
<dl class="metrics">
  <div><dt>颜色数</dt><dd data-metric="colors">$colors_used</dd></div>
  <div><dt>整体平均误差</dt><dd data-metric="mean_abs_error">$mean_abs_error</dd></div>
  <div><dt>单像素最坏误差</dt><dd data-metric="max_pixel_error">$max_pixel_error</dd></div>
  <div><dt>耗时 (ms)</dt><dd data-metric="elapsed_ms">$elapsed_ms</dd></div>
</dl>
<script>
"use strict";
// 以下数据全部来自 quantize 写出的 palette.txt / indices.pgm / report.json 与原图。
const WIDTH = $width;
const HEIGHT = $height;
const PALETTE = $palette_json;
const ORIGINAL_B64 = "$original_b64";
const INDICES_B64 = "$indices_b64";

function decodeBase64(text) {
  const bin = atob(text);
  const out = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) out[i] = bin.charCodeAt(i);
  return out;
}

function drawOriginal() {
  const rgb = decodeBase64(ORIGINAL_B64);
  const image = new ImageData(WIDTH, HEIGHT);
  const px = image.data;
  for (let i = 0, j = 0; i < rgb.length; i += 3, j += 4) {
    px[j] = rgb[i];
    px[j + 1] = rgb[i + 1];
    px[j + 2] = rgb[i + 2];
    px[j + 3] = 255;
  }
  document.getElementById("original").getContext("2d").putImageData(image, 0, 0);
}

function drawQuantized() {
  const indices = decodeBase64(INDICES_B64);
  const image = new ImageData(WIDTH, HEIGHT);
  const px = image.data;
  for (let i = 0, j = 0; i < indices.length; i++, j += 4) {
    const c = PALETTE[indices[i]];
    px[j] = c[0];
    px[j + 1] = c[1];
    px[j + 2] = c[2];
    px[j + 3] = 255;
  }
  document.getElementById("quantized").getContext("2d").putImageData(image, 0, 0);
}

drawOriginal();
drawQuantized();
</script>
</body>
</html>
""")


def _read_palette(path):
    try:
        with open(path, "r", encoding="ascii") as fh:
            lines = fh.read().split("\n")
    except OSError as exc:
        raise ImageFormatError(f"缺少调色板文件: {path} ({exc})") from exc
    if not lines or not lines[0].strip():
        raise ImageFormatError(f"调色板文件为空: {path}")
    try:
        count = int(lines[0])
        palette = []
        for line in lines[1:count + 1]:
            r, g, b = line.split(" ")
            palette.append([int(r), int(g), int(b)])
    except (ValueError, IndexError) as exc:
        raise ImageFormatError(f"调色板文件格式不合法: {path}") from exc
    if len(palette) != count:
        raise ImageFormatError(f"调色板条目数与声明不符: {path}")
    return palette


def _read_indices(path, pixels):
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ImageFormatError(f"缺少索引图文件: {path} ({exc})") from exc
    nl = data.find(b"\n255\n")
    if not data.startswith(b"P5\n") or nl < 0:
        raise ImageFormatError(f"索引图不是规范形式的 P5 PGM: {path}")
    indices = data[nl + 5:]
    if len(indices) != pixels:
        raise ImageFormatError(f"索引图长度与原图像素数不符: {path}")
    return indices


def _read_report(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError) as exc:
        raise ImageFormatError(f"缺少或无法解析报告文件: {path} ({exc})") from exc


def render_html(ppm_path, out_dir):
    """从产物目录与原图拼出自包含 HTML 字符串。"""
    width, height, raw = read_ppm(ppm_path)
    palette = _read_palette(os.path.join(out_dir, PALETTE_FILE))
    indices = _read_indices(os.path.join(out_dir, INDICES_FILE), width * height)
    report = _read_report(os.path.join(out_dir, REPORT_FILE))
    return HTML_TEMPLATE.substitute(
        image=os.path.basename(ppm_path),
        width=width,
        height=height,
        colors_used=len(palette),
        mean_abs_error=f"{float(report['mean_abs_error']):.3f}",
        max_pixel_error=int(report["max_pixel_error"]),
        elapsed_ms=int(report["elapsed_ms"]),
        palette_json=json.dumps(palette, separators=(",", ":")),
        original_b64=base64.b64encode(raw).decode("ascii"),
        indices_b64=base64.b64encode(indices).decode("ascii"),
    )


def run_page(ppm_path, out_dir, html_path):
    """生成对比页面；产物缺失或不一致时抛 ImageFormatError。"""
    html = render_html(ppm_path, out_dir)
    parent = os.path.dirname(os.path.abspath(html_path))
    os.makedirs(parent, exist_ok=True)
    with open(html_path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(html)
