import unittest

from game.world.PerlinNoise import PerlinNoise


class PerlinNoiseTests(unittest.TestCase):
    def test_3d_noise_preserves_fixed_seed_samples(self):
        noise = PerlinNoise(434, mh=8)
        samples = {
            (0.125, -0.75, 1.5): "0x1.286ef10000000p-1",
            (12.25, -31.5, 7.75): "-0x1.cea6200000000p-2",
            (-48.125, 64.25, -9.5): "0x1.1c8e290000000p-3",
            (0.0, 0.0, 0.0): "0x0.0p+0",
        }

        for point, expected in samples.items():
            self.assertEqual(noise.noise(*point).hex(), expected)


if __name__ == "__main__":
    unittest.main()
