import re
import unittest

from tools.app_icons import PIXELS, banner, cells, legacy, path_data, vector


class AppIconTests(unittest.TestCase):
    def test_logo_has_one_pixel_per_mark(self):
        self.assertEqual(len(cells()), "".join(PIXELS).count("#"))
        self.assertEqual(path_data(1, 0, 0).count("M"), len(cells()))

    def test_vector_logo_stays_in_the_adaptive_safe_zone(self):
        numbers = re.findall(r"M([\d.]+),([\d.]+)", vector(108, 108, 44, ""))
        for x, y in numbers:
            # Every pixel starts within the 66dp circle centred on the 108dp canvas.
            self.assertLess((float(x) - 54) ** 2 + (float(y) - 54) ** 2, 33**2)

    def test_sizes_follow_android_densities(self):
        self.assertEqual(legacy(1.5).size, (72, 72))
        self.assertEqual(banner(2).size, (320, 180))

    def test_legacy_icon_has_rounded_transparent_corners(self):
        icon = legacy(1)
        self.assertEqual(icon.getpixel((0, 0))[3], 0)
        self.assertEqual(icon.getpixel((24, 24))[3], 255)


if __name__ == "__main__":
    unittest.main()
