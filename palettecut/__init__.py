"""palettecut：确定性调色板量化库。

读取未压缩 PPM(P6) 位图，按颜色数上限选出代表色，
产出调色板、索引图与误差统计。只用标准库。
"""

from .ppmio import ImageFormatError, read_ppm, write_pgm
from .quantizer import quantize

__all__ = ["ImageFormatError", "read_ppm", "write_pgm", "quantize"]

__version__ = "1.0.0"
