"""命令行入口测试：退出码、产物格式、页面节点、跨进程确定性。"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
FLAT = ROOT / "samples" / "images" / "flat.ppm"
GRADIENT = ROOT / "samples" / "images" / "gradient.ppm"


def run_cli(*args, cwd=ROOT):
    return subprocess.run(
        [sys.executable, "-m", "palettecut", *args],
        cwd=cwd, capture_output=True, text=True,
    )


class QuantizeCliTest(unittest.TestCase):
    def test_success_outputs_and_stdout(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "flat"
            proc = run_cli("quantize", str(FLAT), "8", "--out", str(out))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            self.assertRegex(
                proc.stdout.strip(),
                r"^colors_used=6 mean_abs_error=0\.000 max_pixel_error=0 elapsed_ms=\d+$",
            )
            palette = (out / "palette.txt").read_bytes()
            self.assertTrue(palette.endswith(b"\n"))
            lines = palette.decode("ascii").splitlines()
            self.assertEqual(lines[0], "6")
            colors = [tuple(map(int, line.split(" "))) for line in lines[1:]]
            self.assertEqual(len(colors), 6)
            self.assertEqual(colors, sorted(colors))
            for r, g, b in colors:
                self.assertTrue(all(0 <= v <= 255 for v in (r, g, b)))
            indices = (out / "indices.pgm").read_bytes()
            self.assertTrue(indices.startswith(b"P5\n320 240\n255\n"))
            body = indices[len(b"P5\n320 240\n255\n"):]
            self.assertEqual(len(body), 320 * 240)
            self.assertLess(max(body), 6)
            self.assertEqual(set(body), set(range(6)))
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertEqual(
                list(report),
                ["image", "width", "height", "pixels", "colors_limit",
                 "colors_used", "mean_abs_error", "max_pixel_error", "elapsed_ms"],
            )
            self.assertEqual(report["image"], "flat.ppm")
            self.assertEqual(report["pixels"], 76800)
            self.assertEqual(report["colors_limit"], 8)
            self.assertEqual(report["colors_used"], 6)
            self.assertEqual(report["mean_abs_error"], 0.0)
            self.assertEqual(report["max_pixel_error"], 0)
            self.assertIsInstance(report["elapsed_ms"], int)
            self.assertGreaterEqual(report["elapsed_ms"], 0)

    def test_deterministic_across_processes(self):
        with tempfile.TemporaryDirectory() as tmp:
            outs = []
            for i in range(2):
                out = Path(tmp) / f"run{i}"
                proc = run_cli("quantize", str(GRADIENT), "32", "--out", str(out))
                self.assertEqual(proc.returncode, 0, proc.stderr)
                outs.append(out)
            for name in ("palette.txt", "indices.pgm"):
                self.assertEqual(
                    (outs[0] / name).read_bytes(), (outs[1] / name).read_bytes()
                )
            reports = [
                json.loads((out / "report.json").read_text(encoding="utf-8"))
                for out in outs
            ]
            for report in reports:
                report.pop("elapsed_ms")
            self.assertEqual(reports[0], reports[1])

    def test_missing_input_exit_1_no_partial_output(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            proc = run_cli("quantize", str(Path(tmp) / "nope.ppm"), "8", "--out", str(out))
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(out.exists())

    def test_bad_header_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.ppm"
            bad.write_bytes(b"P6\n2 2\n255\n" + bytes(11))
            out = Path(tmp) / "out"
            proc = run_cli("quantize", str(bad), "8", "--out", str(out))
            self.assertEqual(proc.returncode, 1)
            self.assertFalse(out.exists())

    def test_usage_errors_exit_2(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "out"
            for limit in ("0", "257", "abc"):
                proc = run_cli("quantize", str(FLAT), limit, "--out", str(out))
                self.assertEqual(proc.returncode, 2, limit)
            self.assertEqual(run_cli("quantize").returncode, 2)
            self.assertEqual(run_cli("nonsense").returncode, 2)


class PageCliTest(unittest.TestCase):
    def test_page_contains_canvases_and_metrics(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "flat"
            html = Path(tmp) / "flat.html"
            self.assertEqual(
                run_cli("quantize", str(FLAT), "8", "--out", str(out)).returncode, 0
            )
            proc = run_cli("page", "--ppm", str(FLAT), "--dir", str(out),
                           "--html", str(html))
            self.assertEqual(proc.returncode, 0, proc.stderr)
            text = html.read_text(encoding="utf-8")
            self.assertIn('id="original"', text)
            self.assertIn('id="quantized"', text)
            report = json.loads((out / "report.json").read_text(encoding="utf-8"))
            self.assertIn(f'data-metric="colors">{report["colors_used"]}<', text)
            self.assertIn('data-metric="mean_abs_error">0.000<', text)
            self.assertIn(f'data-metric="max_pixel_error">{report["max_pixel_error"]}<', text)
            self.assertRegex(text, r'data-metric="elapsed_ms">\d+<')
            self.assertNotIn("http://", text)
            self.assertNotIn("https://", text)

    def test_page_deterministic_except_elapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            pages = []
            for i in range(2):
                out = Path(tmp) / f"out{i}"
                html = Path(tmp) / f"p{i}.html"
                run_cli("quantize", str(FLAT), "8", "--out", str(out))
                run_cli("page", "--ppm", str(FLAT), "--dir", str(out),
                        "--html", str(html))
                pages.append(html.read_text(encoding="utf-8"))
            strip = lambda s: re.sub(r'data-metric="elapsed_ms">\d+<',
                                     'data-metric="elapsed_ms">X<', s)
            self.assertEqual(strip(pages[0]), strip(pages[1]))

    def test_page_missing_outputs_exit_1(self):
        with tempfile.TemporaryDirectory() as tmp:
            proc = run_cli("page", "--ppm", str(FLAT), "--dir", str(Path(tmp) / "nope"),
                           "--html", str(Path(tmp) / "x.html"))
            self.assertEqual(proc.returncode, 1)
            self.assertFalse((Path(tmp) / "x.html").exists())


if __name__ == "__main__":
    unittest.main()
