"""palettecut 验收测试：只读 samples/，输出都进临时目录。"""

import contextlib
import io
import json
import os
import re
import tempfile
import unittest

from palettecut.cli import main
from palettecut.files import read_palette, read_pgm, read_report
from palettecut.ppm import InputError, parse_ppm, read_ppm
from palettecut.quantize import quantize

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMAGES = os.path.join(ROOT, "samples", "images")
EXPECTED = os.path.join(ROOT, "samples", "expected")

SAMPLES = {
    "flat": 8,
    "fewcolors": 16,
    "gradient": 32,
    "noise": 64,
    "mixed": 256,
}


def load_expected(name):
    limits = {}
    with open(os.path.join(EXPECTED, name + ".txt"), encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            limits[key] = value
    return limits


def run_quantize(image_path, k, out_dir):
    """通过 CLI 跑 quantize，返回 (exit_code, stdout_line)。"""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        code = main(["quantize", image_path, str(k), "--out", out_dir])
    return code, buf.getvalue()


def recompute_errors(image_path, out_dir):
    """按 README 第二节公式，从 palette.txt 与 indices.pgm 独立重算误差。"""
    width, height, pixels = read_ppm(image_path)
    palette = read_palette(os.path.join(out_dir, "palette.txt"))
    gw, gh, indices = read_pgm(os.path.join(out_dir, "indices.pgm"))
    assert (gw, gh) == (width, height)
    total = 0
    max_err = 0
    for i in range(len(indices)):
        r, g, b = pixels[3 * i], pixels[3 * i + 1], pixels[3 * i + 2]
        pr, pg, pb = palette[indices[i]]
        dr, dg, db = abs(r - pr), abs(g - pg), abs(b - pb)
        total += dr + dg + db
        max_err = max(max_err, dr, dg, db)
    mean = total / (3 * len(indices))
    return palette, indices, mean, max_err


class TestSamplesMeetExpected(unittest.TestCase):
    """逐样例核对 samples/expected/*.txt 给出的上限。"""

    def test_all_samples(self):
        for name, k in SAMPLES.items():
            with self.subTest(sample=name):
                limits = load_expected(name)
                self.assertEqual(int(limits["colors_limit"]), k)
                image = os.path.join(IMAGES, name + ".ppm")
                with tempfile.TemporaryDirectory() as out:
                    code, line = run_quantize(image, k, out)
                    self.assertEqual(code, 0)
                    self.assertRegex(
                        line.strip(),
                        r"^colors_used=\d+ mean_abs_error=\d+\.\d{3} "
                        r"max_pixel_error=\d+ elapsed_ms=\d+$",
                    )
                    palette, indices, mean, max_err = recompute_errors(image, out)
                    report = read_report(os.path.join(out, "report.json"))

                    self.assertLessEqual(len(palette), k)
                    if "colors_used_exact" in limits:
                        self.assertEqual(len(palette), int(limits["colors_used_exact"]))
                    self.assertAlmostEqual(
                        mean, float(limits["mean_abs_error_max"]),
                        delta=float(limits["mean_abs_error_max"]) + 0.001,
                    )
                    self.assertLessEqual(
                        mean, float(limits["mean_abs_error_max"]) + 0.001
                    )
                    self.assertLessEqual(max_err, int(limits["max_pixel_error_max"]))
                    # report.json 与独立重算一致（允许 0.001 显示误差）
                    self.assertAlmostEqual(
                        report["mean_abs_error"], round(mean, 3), delta=0.001
                    )
                    self.assertEqual(report["max_pixel_error"], max_err)
                    self.assertEqual(report["colors_used"], len(palette))
                    self.assertEqual(report["image"], name + ".ppm")
                    self.assertEqual(report["pixels"], int(limits["pixels"]))


class TestOutputFormat(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.out = cls.tmp.name
        image = os.path.join(IMAGES, "gradient.ppm")
        code, _ = run_quantize(image, 32, cls.out)
        assert code == 0
        cls.image = image

    @classmethod
    def tearDownClass(cls):
        cls.tmp.cleanup()

    def test_palette_txt_format(self):
        with open(os.path.join(self.out, "palette.txt"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r", raw)
        text = raw.decode("ascii")
        lines = text.split("\n")[:-1]
        self.assertTrue(all(lines), "不许有空行")
        count = int(lines[0])
        entries = [tuple(map(int, ln.split(" "))) for ln in lines[1:]]
        self.assertEqual(count, len(entries))
        self.assertEqual(entries, sorted(entries))
        for e in entries:
            self.assertTrue(all(0 <= v <= 255 for v in e))

    def test_indices_pgm_format(self):
        with open(os.path.join(self.out, "indices.pgm"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.startswith(b"P5\n320 240\n255\n"))
        body = raw.split(b"\n", 3)[3]
        self.assertEqual(len(body), 320 * 240)
        palette = read_palette(os.path.join(self.out, "palette.txt"))
        self.assertLess(max(body), len(palette))

    def test_every_entry_used_and_colors_used_matches(self):
        palette = read_palette(os.path.join(self.out, "palette.txt"))
        _, _, indices = read_pgm(os.path.join(self.out, "indices.pgm"))
        used = set(indices)
        self.assertEqual(used, set(range(len(palette))))
        report = read_report(os.path.join(self.out, "report.json"))
        self.assertEqual(report["colors_used"], len(used))

    def test_report_json_format(self):
        with open(os.path.join(self.out, "report.json"), "rb") as fh:
            raw = fh.read()
        self.assertTrue(raw.endswith(b"\n"))
        self.assertNotIn(b"\r", raw)
        report = json.loads(raw.decode("utf-8"))
        self.assertEqual(
            set(report),
            {"image", "width", "height", "pixels", "colors_limit", "colors_used",
             "mean_abs_error", "max_pixel_error", "elapsed_ms"},
        )
        self.assertIsInstance(report["elapsed_ms"], int)
        self.assertGreaterEqual(report["elapsed_ms"], 0)
        text = raw.decode("utf-8")
        m = re.search(r'"mean_abs_error": (\d+\.\d{3})', text)
        self.assertIsNotNone(m, "mean_abs_error 保留 3 位小数")


class TestLossless(unittest.TestCase):
    def test_flat_is_lossless(self):
        image = os.path.join(IMAGES, "flat.ppm")
        with tempfile.TemporaryDirectory() as out:
            code, _ = run_quantize(image, 8, out)
            self.assertEqual(code, 0)
            report = read_report(os.path.join(out, "report.json"))
            self.assertEqual(report["colors_used"], 6)
            self.assertEqual(report["mean_abs_error"], 0.0)
            self.assertEqual(report["max_pixel_error"], 0)
            _, _, mean, max_err = recompute_errors(image, out)
            self.assertEqual((mean, max_err), (0.0, 0))

    def test_exact_palette_when_few_colors(self):
        # 构造 3 色小图：调色板必须恰好是这些颜色（升序）
        pixels = bytes([10, 20, 30] * 4 + [200, 100, 50] * 4 + [0, 0, 0] * 4)
        result = quantize(pixels, 5)
        self.assertEqual(result.palette, [(0, 0, 0), (10, 20, 30), (200, 100, 50)])
        self.assertEqual(result.mean_abs_error, 0.0)
        self.assertEqual(result.max_pixel_error, 0)


class TestDeterminism(unittest.TestCase):
    def test_quantize_twice_byte_identical(self):
        image = os.path.join(IMAGES, "noise.ppm")
        with tempfile.TemporaryDirectory() as d1, tempfile.TemporaryDirectory() as d2:
            self.assertEqual(run_quantize(image, 64, d1)[0], 0)
            self.assertEqual(run_quantize(image, 64, d2)[0], 0)
            for fname in ("palette.txt", "indices.pgm"):
                with open(os.path.join(d1, fname), "rb") as fh:
                    a = fh.read()
                with open(os.path.join(d2, fname), "rb") as fh:
                    b = fh.read()
                self.assertEqual(a, b, fname)
            r1 = read_report(os.path.join(d1, "report.json"))
            r2 = read_report(os.path.join(d2, "report.json"))
            r1.pop("elapsed_ms")
            r2.pop("elapsed_ms")
            self.assertEqual(r1, r2)

    def test_core_is_pure(self):
        _, _, pixels = read_ppm(os.path.join(IMAGES, "fewcolors.ppm"))
        r1 = quantize(pixels, 16)
        r2 = quantize(pixels, 16)
        self.assertEqual(r1.palette, r2.palette)
        self.assertEqual(r1.indices, r2.indices)


class TestCliExitCodes(unittest.TestCase):
    def test_missing_input(self):
        with tempfile.TemporaryDirectory() as out:
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["quantize", "no-such-file.ppm", "8", "--out", out])
            self.assertEqual(code, 1)
            self.assertEqual(os.listdir(out), [])

    def test_bad_header(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = os.path.join(tmp, "bad.ppm")
            with open(bad, "wb") as fh:
                fh.write(b"P6\n4 4\n255\n" + b"\x00" * 10)
            out = os.path.join(tmp, "out")
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["quantize", bad, "8", "--out", out])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(out))

    def test_usage_error(self):
        with tempfile.TemporaryDirectory() as out:
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    main(["quantize", os.path.join(IMAGES, "flat.ppm"), "0",
                          "--out", out])
            self.assertEqual(cm.exception.code, 2)
            with contextlib.redirect_stderr(io.StringIO()):
                with self.assertRaises(SystemExit) as cm:
                    main(["quantize", os.path.join(IMAGES, "flat.ppm"), "257",
                          "--out", out])
            self.assertEqual(cm.exception.code, 2)
            self.assertEqual(os.listdir(out), [])

    def test_page_missing_outputs(self):
        with tempfile.TemporaryDirectory() as tmp:
            with contextlib.redirect_stderr(io.StringIO()):
                code = main(["page", "--ppm", os.path.join(IMAGES, "flat.ppm"),
                             "--dir", tmp, "--html",
                             os.path.join(tmp, "x.html")])
            self.assertEqual(code, 1)
            self.assertFalse(os.path.exists(os.path.join(tmp, "x.html")))


class TestPage(unittest.TestCase):
    def test_page_contents(self):
        image = os.path.join(IMAGES, "gradient.ppm")
        with tempfile.TemporaryDirectory() as tmp:
            out = os.path.join(tmp, "out")
            self.assertEqual(run_quantize(image, 32, out)[0], 0)
            html_path = os.path.join(tmp, "page.html")
            code = main(["page", "--ppm", image, "--dir", out, "--html", html_path])
            self.assertEqual(code, 0)
            with open(html_path, encoding="utf-8") as fh:
                page = fh.read()
            self.assertIn('id="original"', page)
            self.assertIn('id="quantized"', page)
            report = read_report(os.path.join(out, "report.json"))
            self.assertIn(f'data-metric="colors">{report["colors_used"]}<', page)
            self.assertIn(
                f'data-metric="mean_abs_error">{report["mean_abs_error"]:.3f}<', page
            )
            self.assertIn(
                f'data-metric="max_pixel_error">{report["max_pixel_error"]}<', page
            )
            self.assertIn(
                f'data-metric="elapsed_ms">{report["elapsed_ms"]}<', page
            )
            # 自包含：不引外部资源
            self.assertNotIn("http://", page)
            self.assertNotIn("https://", page)
            self.assertNotIn("src=", page.replace("data:", ""))

    def test_page_deterministic_except_elapsed(self):
        image = os.path.join(IMAGES, "fewcolors.ppm")
        with tempfile.TemporaryDirectory() as tmp:
            pages = []
            for i in (1, 2):
                out = os.path.join(tmp, f"out{i}")
                self.assertEqual(run_quantize(image, 16, out)[0], 0)
                html_path = os.path.join(tmp, f"p{i}.html")
                self.assertEqual(
                    main(["page", "--ppm", image, "--dir", out,
                          "--html", html_path]), 0)
                with open(html_path, encoding="utf-8") as fh:
                    pages.append(fh.read())
            strip = lambda s: re.sub(
                r'data-metric="elapsed_ms">\d+<', 'data-metric="elapsed_ms">X<', s
            )
            self.assertEqual(strip(pages[0]), strip(pages[1]))


class TestPpmReader(unittest.TestCase):
    def test_rejects_non_p6(self):
        with self.assertRaises(InputError):
            parse_ppm(b"P3\n1 1\n255\n0 0 0\n")

    def test_rejects_bad_maxval(self):
        with self.assertRaises(InputError):
            parse_ppm(b"P6\n1 1\n65535\n" + b"\x00" * 3)

    def test_rejects_short_body(self):
        with self.assertRaises(InputError):
            parse_ppm(b"P6\n2 2\n255\n" + b"\x00" * 11)

    def test_accepts_minimal(self):
        w, h, px = parse_ppm(b"P6\n1 1\n255\n\x01\x02\x03")
        self.assertEqual((w, h), (1, 1))
        self.assertEqual(px, b"\x01\x02\x03")


class TestEdgeCases(unittest.TestCase):
    def test_k1(self):
        pixels = bytes([0, 0, 0, 255, 255, 255, 128, 128, 128])
        result = quantize(pixels, 1)
        self.assertEqual(len(result.palette), 1)
        self.assertEqual(result.indices, b"\x00\x00\x00")

    def test_k256_single_color(self):
        pixels = bytes([7, 8, 9]) * 100
        result = quantize(pixels, 256)
        self.assertEqual(result.palette, [(7, 8, 9)])
        self.assertEqual(result.max_pixel_error, 0)

    def test_invalid_k(self):
        with self.assertRaises(ValueError):
            quantize(b"\x00\x00\x00", 0)
        with self.assertRaises(ValueError):
            quantize(b"\x00\x00\x00", 300)


if __name__ == "__main__":
    unittest.main()
