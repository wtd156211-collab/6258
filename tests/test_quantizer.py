"""量化核心的单元测试（合成数据，不读 samples）。"""

import unittest

from palettecut.quantizer import (
    build_histogram,
    map_pixels,
    measure_errors,
    median_cut,
    quantize,
    select_palette,
)


def make_raw(colors, reps):
    """按 (颜色, 重复次数) 列表拼出行优先 RGB 字节串。"""
    raw = bytearray()
    for (r, g, b), n in zip(colors, reps):
        raw += bytes([r, g, b]) * n
    return bytes(raw)


class QuantizeTest(unittest.TestCase):
    def test_lossless_when_colors_within_limit(self):
        colors = [(10, 20, 30), (200, 100, 50), (0, 0, 0)]
        raw = make_raw(colors, [3, 5, 2])
        palette, indices, mae, worst = quantize(raw, 5, 2, 3)
        self.assertEqual(palette, sorted(colors))
        self.assertEqual((mae, worst), (0.0, 0))
        self.assertEqual(len(indices), 10)
        self.assertEqual(len(set(indices)), 3)

    def test_single_color_limit(self):
        raw = make_raw([(0, 0, 0), (255, 255, 255)], [4, 4])
        palette, indices, mae, worst = quantize(raw, 4, 2, 1)
        self.assertEqual(len(palette), 1)
        self.assertEqual(set(indices), {0})
        self.assertEqual(palette[0], (128, 128, 128))
        self.assertEqual(worst, 128)

    def test_deterministic_across_runs(self):
        colors = [(i * 37 % 256, i * 91 % 256, i * 53 % 256) for i in range(500)]
        raw = make_raw(colors, [i % 7 + 1 for i in range(500)])
        first = quantize(raw, 100, 35, 16)
        second = quantize(raw, 100, 35, 16)
        self.assertEqual(first[0], second[0])
        self.assertEqual(bytes(first[1]), bytes(second[1]))
        self.assertEqual(first[2:], second[2:])

    def test_palette_sorted_and_fully_used(self):
        colors = [(i % 256, (i * 3) % 256, (i * 7) % 256) for i in range(300)]
        raw = make_raw(colors, [1] * 300)
        palette, indices, _, _ = quantize(raw, 60, 5, 32)
        self.assertEqual(palette, sorted(palette))
        self.assertLessEqual(len(palette), 32)
        self.assertEqual(set(indices), set(range(len(palette))))
        self.assertLess(max(indices), len(palette))

    def test_invalid_limit(self):
        with self.assertRaises(ValueError):
            quantize(bytes(12), 2, 2, 0)
        with self.assertRaises(ValueError):
            quantize(bytes(12), 2, 2, 257)


class MedianCutTest(unittest.TestCase):
    def test_boxes_cover_all_items_and_nonempty(self):
        items = [((i * 11) % 256, (i * 29) % 256, (i * 47) % 256, i % 5 + 1)
                 for i in range(200)]
        items.sort()
        boxes = median_cut(items, 17)
        self.assertLessEqual(len(boxes), 17)
        self.assertTrue(all(boxes))
        merged = sorted(item for box in boxes for item in box)
        self.assertEqual(merged, items)

    def test_singleton_boxes_stop_splitting(self):
        items = [(i, i, i, 1) for i in range(5)]
        boxes = median_cut(items, 256)
        self.assertEqual(len(boxes), 5)


class MappingTest(unittest.TestCase):
    def test_histogram_and_mapping(self):
        raw = bytes([1, 2, 3, 1, 2, 3, 9, 9, 9])
        hist = build_histogram(raw)
        self.assertEqual(hist[(1, 2, 3)], 2)
        self.assertEqual(hist[(9, 9, 9)], 1)
        lut = {(1, 2, 3): 0, (9, 9, 9): 1}
        self.assertEqual(map_pixels(raw, lut), bytearray([0, 0, 1]))

    def test_measure_errors(self):
        items = [(0, 0, 0, 1), (10, 20, 30, 2)]
        palette = [(4, 0, 0), (10, 22, 28)]
        lut = {(0, 0, 0): 0, (10, 20, 30): 1}
        mae, worst = measure_errors(items, palette, lut, 3)
        self.assertAlmostEqual(mae, 12 / 9)
        self.assertEqual(worst, 4)

    def test_select_palette_lossless_branch(self):
        items = [(1, 2, 3, 5), (7, 8, 9, 1)]
        palette, lut = select_palette(items, 2)
        self.assertEqual(palette, [(1, 2, 3), (7, 8, 9)])
        self.assertEqual(lut[(7, 8, 9)], 1)


if __name__ == "__main__":
    unittest.main()
