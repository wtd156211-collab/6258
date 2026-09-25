"""未压缩 PPM(P6) 读取与 PGM(P5) 写出。

只认规范形式 ``P6\\n<宽> <高>\\n255\\n`` 紧跟 ``宽*高*3`` 字节，
RGB 行优先、无注释、无填充、最大值 255；其余变体一律视为输入不可用。
"""


class ImageFormatError(ValueError):
    """输入文件缺失或不符合规定的 PPM 规范形式。"""


def read_ppm(path):
    """读取 PPM，返回 (width, height, raw_rgb_bytes)。

    文件缺失、头不合法或像素数据长度不符时抛 ImageFormatError。
    """
    try:
        with open(path, "rb") as fh:
            data = fh.read()
    except OSError as exc:
        raise ImageFormatError(f"无法读取输入文件: {path} ({exc})") from exc

    if not data.startswith(b"P6\n"):
        raise ImageFormatError(f"不是规范形式的 P6 PPM: {path}")
    rest = data[3:]
    nl = rest.find(b"\n")
    if nl < 0:
        raise ImageFormatError(f"PPM 头不完整: {path}")
    parts = rest[:nl].split()
    if len(parts) != 2:
        raise ImageFormatError(f"PPM 宽高行不合法: {path}")
    try:
        width = int(parts[0])
        height = int(parts[1])
    except ValueError as exc:
        raise ImageFormatError(f"PPM 宽高不是整数: {path}") from exc
    if width <= 0 or height <= 0:
        raise ImageFormatError(f"PPM 宽高必须为正整数: {path}")
    rest = rest[nl + 1:]
    if not rest.startswith(b"255\n"):
        raise ImageFormatError(f"PPM 最大值只认 255: {path}")
    raw = rest[4:]
    expected = width * height * 3
    if len(raw) != expected:
        raise ImageFormatError(
            f"PPM 像素数据长度不符: 期望 {expected} 字节, 实际 {len(raw)} 字节"
        )
    return width, height, raw


def pgm_bytes(width, height, indices):
    """拼出 P5 PGM 的完整字节内容（头 + 每像素 1 字节）。"""
    if len(indices) != width * height:
        raise ValueError("索引图长度与宽高不符")
    header = f"P5\n{width} {height}\n255\n".encode("ascii")
    return header + bytes(indices)


def write_pgm(path, width, height, indices):
    with open(path, "wb") as fh:
        fh.write(pgm_bytes(width, height, indices))
