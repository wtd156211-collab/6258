"""样例验收测试：逐张核对 samples/expected 里的上限与确定性。"""

import unittest
from pathlib import Path

from palettecut.ppmio import read_ppm
from palettecut.quantizer import quantize

ROOT = Path(__file__).resolve().parent.parent
IMAGES = ROOT / "samples" / "images"
EXPECTED = ROOT / "samples" / "expected"


def load_expected(name):
    limits = {}
    for line in (EXPECTED / f"{name}.txt").read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        limits[key.strip()] = value.strip()
    return limits


def sample_names():
    return sorted(p.stem for p in IMAGES.glob("*.ppm"))


class SampleLimitsTest(unittest.TestCase):
    def test_samples_meet_expected_limits(self):
        for name in sample_names():
            with self.subTest(sample=name):
                limits = load_expected(name)
                width, height, raw = read_ppm(IMAGES / f"{name}.ppm")
                self.assertEqual(width * height, int(limits["pixels"]))
                k = int(limits["colors_limit"])
                palette, indices, mae, worst = quantize(raw, width, height, k)
                self.assertLessEqual(len(palette), k)
                if "colors_used_exact" in limits:
                    self.assertEqual(len(palette), int(limits["colors_used_exact"]))
                self.assertLessEqual(mae, float(limits["mean_abs_error_max"]) + 0.001)
                self.assertLessEqual(worst, int(limits["max_pixel_error_max"]))
                self.assertEqual(palette, sorted(palette))
                self.assertEqual(len(indices), width * height)
                self.assertLess(max(indices), len(palette))
                self.assertEqual(set(indices), set(range(len(palette))))

    def test_samples_deterministic(self):
        for name in sample_names():
            with self.subTest(sample=name):
                limits = load_expected(name)
                width, height, raw = read_ppm(IMAGES / f"{name}.ppm")
                k = int(limits["colors_limit"])
                first = quantize(raw, width, height, k)
                second = quantize(raw, width, height, k)
                self.assertEqual(first[0], second[0])
                self.assertEqual(bytes(first[1]), bytes(second[1]))
                self.assertEqual(first[2:], second[2:])

    def test_flat_is_lossless(self):
        width, height, raw = read_ppm(IMAGES / "flat.ppm")
        palette, indices, mae, worst = quantize(raw, width, height, 8)
        self.assertEqual(len(palette), 6)
        self.assertEqual((mae, worst), (0.0, 0))


if __name__ == "__main__":
    unittest.main()
