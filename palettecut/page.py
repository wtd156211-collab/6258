"""自包含对比页面：原图与量化结果并排 Canvas，指标来自引擎输出文件。"""

import base64
import html

_TEMPLATE = """<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<title>palettecut 对比 - {title}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 24px; background: #f5f5f5; color: #222; }}
  h1 {{ font-size: 18px; }}
  .row {{ display: flex; gap: 16px; flex-wrap: wrap; }}
  figure {{ margin: 0; background: #fff; padding: 8px; border: 1px solid #ddd; }}
  figcaption {{ text-align: center; font-size: 13px; color: #555; padding-top: 6px; }}
  canvas {{ display: block; max-width: 46vw; height: auto; image-rendering: pixelated; }}
  dl {{ display: flex; gap: 24px; background: #fff; border: 1px solid #ddd; padding: 12px 16px; }}
  dt {{ font-size: 12px; color: #777; }}
  dd {{ margin: 2px 0 0; font-size: 16px; font-variant-numeric: tabular-nums; }}
</style>
</head>
<body>
<h1>{title}</h1>
<div class="row">
  <figure><canvas id="original" width="{width}" height="{height}"></canvas><figcaption>原图</figcaption></figure>
  <figure><canvas id="quantized" width="{width}" height="{height}"></canvas><figcaption>量化后</figcaption></figure>
</div>
<dl>
  <div><dt>颜色数</dt><dd data-metric="colors">{colors}</dd></div>
  <div><dt>整体平均误差 mean_abs_error</dt><dd data-metric="mean_abs_error">{mean_abs_error}</dd></div>
  <div><dt>单像素最坏误差 max_pixel_error</dt><dd data-metric="max_pixel_error">{max_pixel_error}</dd></div>
  <div><dt>耗时 elapsed_ms</dt><dd data-metric="elapsed_ms">{elapsed_ms}</dd></div>
</dl>
<script>
var WIDTH = {width}, HEIGHT = {height};
var ORIGINAL_B64 = "{original_b64}";
var QUANTIZED_B64 = "{quantized_b64}";
function draw(id, b64) {{
  var canvas = document.getElementById(id);
  var ctx = canvas.getContext("2d");
  var img = ctx.createImageData(WIDTH, HEIGHT);
  var rgb = Uint8Array.from(atob(b64), function (ch) {{ return ch.charCodeAt(0); }});
  var d = img.data;
  for (var i = 0, j = 0; i < rgb.length; i += 3, j += 4) {{
    d[j] = rgb[i]; d[j + 1] = rgb[i + 1]; d[j + 2] = rgb[i + 2]; d[j + 3] = 255;
  }}
  ctx.putImageData(img, 0, 0);
}}
draw("original", ORIGINAL_B64);
draw("quantized", QUANTIZED_B64);
</script>
</body>
</html>
"""


def render_quantized_rgb(palette, indices):
    """由调色板与索引图重建量化后的 RGB 字节串（页面端不再重算）。"""
    padded = list(palette) + [(0, 0, 0)] * (256 - len(palette))
    rtab = bytes(e[0] for e in padded)
    gtab = bytes(e[1] for e in padded)
    btab = bytes(e[2] for e in padded)
    out = bytearray(len(indices) * 3)
    out[0::3] = indices.translate(rtab)
    out[1::3] = indices.translate(gtab)
    out[2::3] = indices.translate(btab)
    return bytes(out)


def build_html(image_name, width, height, pixels, palette, indices, report):
    quantized_rgb = render_quantized_rgb(palette, indices)
    return _TEMPLATE.format(
        title=html.escape(image_name),
        width=width,
        height=height,
        colors=report["colors_used"],
        mean_abs_error=f'{report["mean_abs_error"]:.3f}',
        max_pixel_error=report["max_pixel_error"],
        elapsed_ms=report["elapsed_ms"],
        original_b64=base64.b64encode(pixels).decode("ascii"),
        quantized_b64=base64.b64encode(quantized_rgb).decode("ascii"),
    )
