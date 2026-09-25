"""二进制 PPM（P6）读取。只认规范形式：P6\\n<宽> <高>\\n255\\n + 像素字节。"""


class InputError(Exception):
    """输入不可用（文件缺失、头不合法、数据长度不符等）。"""


def read_ppm(path):
    """读取 P6 PPM，返回 (width, height, pixels)。失败抛 InputError。"""
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise InputError(f"无法读取输入文件 {path}: {exc}") from exc
    return parse_ppm(data, path)


def parse_ppm(data, source="<bytes>"):
    parts = data.split(b"\n", 3)
    if len(parts) < 4:
        raise InputError(f"{source}: 不是规范形式的 P6 PPM（头部不完整）")
    magic, dims, maxval, pixels = parts
    if magic != b"P6":
        raise InputError(f"{source}: 魔数不是 P6")
    dims = dims.split()
    if len(dims) != 2 or not all(d.isdigit() for d in dims):
        raise InputError(f"{source}: 宽高行不合法")
    width, height = int(dims[0]), int(dims[1])
    if width < 1 or height < 1:
        raise InputError(f"{source}: 宽高必须为正整数")
    if maxval != b"255":
        raise InputError(f"{source}: 最大值只认 255")
    expected = width * height * 3
    if len(pixels) != expected:
        raise InputError(
            f"{source}: 像素数据长度 {len(pixels)} 与 {width}x{height}x3={expected} 不符"
        )
    return width, height, pixels
