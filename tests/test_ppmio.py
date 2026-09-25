"""PPM/PGM 读写的单元测试（只用内存里的合成数据）。"""

import os
import tempfile
import unittest

from palettecut.ppmio import ImageFormatError, pgm_bytes, read_ppm, write_pgm


def make_ppm(width, height, raw):
    return f"P6\n{width} {height}\n255\n".encode("ascii") + raw


class ReadPpmTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.path = os.path.join(self.tmp.name, "x.ppm")

    def tearDown(self):
        self.tmp.cleanup()

    def write(self, data):
        with open(self.path, "wb") as fh:
            fh.write(data)

    def test_roundtrip(self):
        raw = bytes([255, 0, 0, 0, 255, 0, 0, 0, 255, 1, 2, 3])
        self.write(make_ppm(2, 2, raw))
        width, height, got = read_ppm(self.path)
        self.assertEqual((width, height), (2, 2))
        self.assertEqual(got, raw)

    def test_missing_file(self):
        with self.assertRaises(ImageFormatError):
            read_ppm(os.path.join(self.tmp.name, "nope.ppm"))

    def test_bad_magic(self):
        self.write(b"P3\n2 2\n255\n" + bytes(12))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)

    def test_bad_maxval(self):
        self.write(b"P6\n2 2\n127\n" + bytes(12))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)

    def test_bad_dims(self):
        self.write(b"P6\n2 x\n255\n" + bytes(12))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)
        self.write(b"P6\n0 2\n255\n" + bytes(12))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)

    def test_short_and_long_data(self):
        self.write(make_ppm(2, 2, bytes(11)))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)
        self.write(make_ppm(2, 2, bytes(13)))
        with self.assertRaises(ImageFormatError):
            read_ppm(self.path)


class WritePgmTest(unittest.TestCase):
    def test_header_and_body(self):
        data = pgm_bytes(3, 2, bytes([0, 1, 2, 3, 4, 5]))
        self.assertEqual(data, b"P5\n3 2\n255\n" + bytes([0, 1, 2, 3, 4, 5]))

    def test_length_mismatch(self):
        with self.assertRaises(ValueError):
            pgm_bytes(3, 2, bytes(5))

    def test_write_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = os.path.join(tmp, "x.pgm")
            write_pgm(path, 1, 1, bytes([7]))
            with open(path, "rb") as fh:
                self.assertEqual(fh.read(), b"P5\n1 1\n255\n\x07")


if __name__ == "__main__":
    unittest.main()
