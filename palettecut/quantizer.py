"""调色板量化核心：直方图统计 + 加权中位切分。

确定性约束贯穿始终：
- 颜色项先按 (r, g, b) 全序排序再进入切分；
- 切分通道在最大跨度并列时固定取编号小的通道；
- 堆元素带单调序号，并列时按入堆顺序弹出，不依赖遍历顺序；
- 不使用任何随机初始化。

每个像素独立映射到所属盒子的代表色（不做抖动与误差扩散）。
"""

import heapq
from collections import Counter


def build_histogram(raw):
    """统计精确颜色直方图：{(r, g, b): 像素数}。"""
    return Counter(zip(raw[0::3], raw[1::3], raw[2::3]))


def _box_stats(box):
    """返回 (总像素数, (r 跨度, g 跨度, b 跨度))。"""
    pop = 0
    r_lo = g_lo = b_lo = 255
    r_hi = g_hi = b_hi = 0
    for r, g, b, count in box:
        pop += count
        if r < r_lo:
            r_lo = r
        if r > r_hi:
            r_hi = r
        if g < g_lo:
            g_lo = g
        if g > g_hi:
            g_hi = g
        if b < b_lo:
            b_lo = b
        if b > b_hi:
            b_hi = b
    return pop, (r_hi - r_lo, g_hi - g_lo, b_hi - b_lo)


def _box_mean(box):
    """盒子的加权平均色，四舍五入到整数，确定性取整。"""
    pop = 0
    r_sum = g_sum = b_sum = 0
    for r, g, b, count in box:
        pop += count
        r_sum += r * count
        g_sum += g * count
        b_sum += b * count
    half = pop // 2
    return ((r_sum + half) // pop, (g_sum + half) // pop, (b_sum + half) // pop)


def _split_box(box, pop, ranges):
    """沿跨度最大的通道（并列取编号小者）按加权中位数切成两个非空盒子。"""
    channel = ranges.index(max(ranges))
    box.sort(key=lambda it: (it[channel], it[0], it[1], it[2]))
    half = pop / 2
    acc = 0
    split = len(box) - 1
    for i, item in enumerate(box):
        acc += item[3]
        if acc >= half:
            split = i + 1
            break
    split = max(1, min(split, len(box) - 1))
    return box[:split], box[split:]


def median_cut(items, k):
    """把颜色项切分成至多 k 个非空盒子。

    items 是已按 (r, g, b) 排序的 (r, g, b, count) 列表。
    每轮弹出「总像素数 × (最大通道跨度 + 1)」最大的盒子切分，
    兼顾整体平均误差与单像素最坏误差。
    """
    heap = []
    serial = 0

    def push(box):
        nonlocal serial
        pop, ranges = _box_stats(box)
        priority = pop * (max(ranges) + 1)
        heapq.heappush(heap, (-priority, serial, box))
        serial += 1

    push(items)
    final = []
    count = 1
    while count < k and heap:
        _, _, box = heapq.heappop(heap)
        if len(box) == 1:
            final.append(box)
            continue
        pop, ranges = _box_stats(box)
        left, right = _split_box(box, pop, ranges)
        push(left)
        push(right)
        count += 1
    final.extend(entry[2] for entry in heap)
    return final


def select_palette(items, k):
    """从颜色项选出调色板与「颜色 -> 调色板索引」映射。

    返回 (palette, color_to_index)；palette 按 (r, g, b) 字典序升序，
    条目数不超过 k，且每条至少被 items 里的一种颜色使用。
    """
    if len(items) <= k:
        palette = [(r, g, b) for r, g, b, _ in items]
        return palette, {color: i for i, color in enumerate(palette)}
    boxes = median_cut(items, k)
    entries = [(_box_mean(box), box) for box in boxes]
    # 调色板按代表色字典序升序；代表色并列时用盒内最小颜色兜底，保证全序。
    entries.sort(key=lambda entry: (entry[0], min(entry[1])[:3]))
    palette = [mean for mean, _ in entries]
    color_to_index = {}
    for index, (_, box) in enumerate(entries):
        for r, g, b, _count in box:
            color_to_index[(r, g, b)] = index
    return palette, color_to_index


def map_pixels(raw, color_to_index):
    """逐像素映射为调色板索引（行优先，每像素 1 字节）。"""
    return bytearray(
        map(color_to_index.__getitem__, zip(raw[0::3], raw[1::3], raw[2::3]))
    )


def measure_errors(items, palette, color_to_index, pixels):
    """按 README 口径统计 (mean_abs_error, max_pixel_error)。"""
    total = 0
    worst = 0
    for r, g, b, count in items:
        pr, pg, pb = palette[color_to_index[(r, g, b)]]
        dr = abs(r - pr)
        dg = abs(g - pg)
        db = abs(b - pb)
        total += count * (dr + dg + db)
        err = dr if dr > dg else dg
        if db > err:
            err = db
        if err > worst:
            worst = err
    return total / (3.0 * pixels), worst


def quantize(raw, width, height, k):
    """量化主流程。

    返回 (palette, indices, mean_abs_error, max_pixel_error)：
    palette 为升序的 (r, g, b) 列表，indices 为行优先索引图。
    """
    if not 1 <= k <= 256:
        raise ValueError("颜色上限必须是 1-256 的整数")
    pixels = width * height
    histogram = build_histogram(raw)
    items = sorted((r, g, b, c) for (r, g, b), c in histogram.items())
    del histogram
    palette, color_to_index = select_palette(items, k)
    indices = map_pixels(raw, color_to_index)
    mean_abs_error, max_pixel_error = measure_errors(
        items, palette, color_to_index, pixels
    )
    return palette, indices, mean_abs_error, max_pixel_error
