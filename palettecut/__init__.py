"""palettecut：确定性调色板量化（仅标准库）。"""

from .ppm import InputError, read_ppm
from .quantize import Result, quantize

__all__ = ["InputError", "Result", "quantize", "read_ppm"]
__version__ = "0.1.0"
