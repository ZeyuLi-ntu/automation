import unittest,struct
import pymupdf
from market_rates.vision_input import png_for_vision

class VisionInputTests(unittest.TestCase):
    def test_thin_strip_preserves_pixels(self):
        source=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,920,26),False);source.clear_with(90)
        original=source.tobytes('png');result=png_for_vision(original)
        self.assertEqual(struct.unpack('>II',result[16:24]),(920,128))
        target=pymupdf.Pixmap(result);self.assertEqual(target.pixel(4,51),source.pixel(4,0));self.assertEqual(target.pixel(4,1),(255,255,255))
        self.assertEqual(original,source.tobytes('png'))

    def test_regular_image_unchanged(self):
        p=pymupdf.Pixmap(pymupdf.csRGB,pymupdf.IRect(0,0,800,1100),False);p.clear_with(255)
        png=p.tobytes('png');self.assertEqual(png_for_vision(png),png)
