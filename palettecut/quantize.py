"""核心量化：6bit 直方图 + 确定性 median-cut + 盒内映射。

确定性保证：无随机初始化、无集合遍历参与输出；所有并列情形按固定规则
（通道顺序 r/g/b、箱内排序键、盒选择键）打破。
"""

from collections import namedtuple

Result = namedtuple(
    "Result", ["palette", "indices", "mean_abs_error", "max_pixel_error"]
)

_BITS = 6
_SHIFT = 8 - _BITS
_NBIN = 1 << _BITS
_HIST_SIZE = 1 << (3 * _BITS)


def _expand6(v):
    """把 6bit 箱值还原成 8bit 代表值（误差 <= 3）。"""
    return (v << 2) | (v >> 4)


def quantize(pixels, k):
    """pixels: RGB 行优先字节串；k: 颜色数上限（1..256）。

    返回 Result(palette=[(r,g,b), ...] 按 (r,g,b) 升序, indices=bytes,
    mean_abs_error=float, max_pixel_error=int)。
    """
    if not 1 <= k <= 256:
        raise ValueError("颜色数上限必须在 1..256")
    n = len(pixels) // 3
    if n == 0:
        raise ValueError("空图像")

    hist = [0] * _HIST_SIZE
    uniques = set()
    capped = False
    px = pixels
    hh = hist
    for i in range(0, len(px), 3):
        r = px[i]
        g = px[i + 1]
        b = px[i + 2]
        hh[(r >> 2) << 12 | (g >> 2) << 6 | b >> 2] += 1
        if not capped:
            uniques.add(r << 16 | g << 8 | b)
            if len(uniques) > k:
                capped = True
                uniques = None

    if not capped:
        return _exact_path(px, n, uniques)
    return _median_cut_path(px, n, hist, k)


def _exact_path(px, n, uniques):
    """不同颜色数 <= k：调色板即这些颜色本身，误差为 0。"""
    colors = sorted(uniques)  # 打包整数排序 == (r,g,b) 字典序
    index_of = {c: i for i, c in enumerate(colors)}
    indices = bytearray(n)
    j = 0
    for i in range(0, len(px), 3):
        indices[j] = index_of[px[i] << 16 | px[i + 1] << 8 | px[i + 2]]
        j += 1
    palette = [((c >> 16) & 255, (c >> 8) & 255, c & 255) for c in colors]
    return Result(palette, bytes(indices), 0.0, 0)


def _box_stats(box, hist):
    minr = maxr = (box[0] >> 12) & 63
    ming = maxg = (box[0] >> 6) & 63
    minb = maxb = box[0] & 63
    pop = 0
    for bi in box:
        r = bi >> 12
        g = (bi >> 6) & 63
        b = bi & 63
        pop += hist[bi]
        if r < minr:
            minr = r
        elif r > maxr:
            maxr = r
        if g < ming:
            ming = g
        elif g > maxg:
            maxg = g
        if b < minb:
            minb = b
        elif b > maxb:
            maxb = b
    ext = (maxr - minr, maxg - ming, maxb - minb)
    return max(ext), pop, ext


def _median_cut_path(px, n, hist, k):
    bins = [bi for bi, c in enumerate(hist) if c]
    boxes = [bins]
    stats = [_box_stats(bins, hist)]

    while len(boxes) < k:
        # 选盒：跨度最大优先，并列取像素多者，再并列取编号小者。
        pick = -1
        best = None
        for idx, (span, pop, _ext) in enumerate(stats):
            if span <= 0:
                continue
            key = (span, pop, -idx)
            if best is None or key > best:
                best = key
                pick = idx
        if pick < 0:
            break
        box = boxes[pick]
        ext = stats[pick][2]
        ch = ext.index(max(ext))  # 并列时固定 r->g->b
        shift = (2 - ch) * _BITS
        box.sort(key=lambda bi: ((bi >> shift) & 63, bi))
        total = stats[pick][1]
        half = total // 2 if total % 2 == 0 else total // 2 + 1
        cum = 0
        sp = 0
        for j, bi in enumerate(box):
            cum += hist[bi]
            if cum >= half:
                sp = j + 1
                break
        if sp <= 0:
            sp = 1
        elif sp >= len(box):
            sp = len(box) - 1
        head, tail = box[:sp], box[sp:]
        boxes[pick] = head
        boxes.append(tail)
        stats[pick] = _box_stats(head, hist)
        stats.append(_box_stats(tail, hist))

    # 每个盒一条代表色：箱内计数加权平均。
    palette = []
    for box in boxes:
        sr = sg = sb = sc = 0
        for bi in box:
            c = hist[bi]
            sr += (bi >> 12) * c
            sg += ((bi >> 6) & 63) * c
            sb += (bi & 63) * c
            sc += c
        palette.append(
            (
                _expand6((sr + sc // 2) // sc),
                _expand6((sg + sc // 2) // sc),
                _expand6((sb + sc // 2) // sc),
            )
        )

    # 调色板按 (r,g,b) 升序；同步重排 箱->条目 映射。
    order = sorted(range(len(palette)), key=palette.__getitem__)
    remap = bytearray(256)
    for new, old in enumerate(order):
        remap[old] = new
    palette = [palette[old] for old in order]

    table = bytearray(_HIST_SIZE)
    for ei, box in enumerate(boxes):
        for bi in box:
            table[bi] = ei
    table = table.translate(bytes(remap))

    indices = bytearray(n)
    total_abs = 0
    max_err = 0
    j = 0
    for i in range(0, len(px), 3):
        r = px[i]
        g = px[i + 1]
        b = px[i + 2]
        e = table[(r >> 2) << 12 | (g >> 2) << 6 | b >> 2]
        indices[j] = e
        j += 1
        pr, pg, pb = palette[e]
        dr = r - pr
        if dr < 0:
            dr = -dr
        dg = g - pg
        if dg < 0:
            dg = -dg
        db = b - pb
        if db < 0:
            db = -db
        total_abs += dr + dg + db
        m = dr if dr > dg else dg
        if db > m:
            m = db
        if m > max_err:
            max_err = m

    mean_abs_error = round(total_abs / (3 * n), 3)
    return Result(palette, bytes(indices), mean_abs_error, max_err)
