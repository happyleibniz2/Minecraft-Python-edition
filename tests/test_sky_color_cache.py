import unittest

from game.Scene import Scene


class SkyColorCacheTests(unittest.TestCase):
    def test_build_sky_colors_interpolates_horizon_to_zenith(self):
        colors = Scene._build_sky_colors((1.0, 0.5, 0.0), (0.0, 0.0, 1.0),
                                         (0.0, 1.0))
        # t=0 -> horizon, t=1 -> zenith, 3 floats per vertex
        self.assertEqual(len(colors), 6)
        self.assertEqual(colors[0:3], (1.0, 0.5, 0.0))
        self.assertEqual(colors[3:6], (0.0, 0.0, 1.0))

    def test_build_sky_colors_is_deterministic_and_pure(self):
        args = ((0.2, 0.4, 0.6), (0.8, 0.6, 0.4), (0.0, 0.5, 1.0))
        first = Scene._build_sky_colors(*args)
        second = Scene._build_sky_colors(*args)
        self.assertEqual(first, second)
        self.assertEqual(len(first), 9)  # 3 vertices x 3 components


if __name__ == "__main__":
    unittest.main()
