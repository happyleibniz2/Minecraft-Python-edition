import math
import unittest
from types import SimpleNamespace

from game.Lighting.SkyShader import SkyShader
from game.world.DayNightCycle import DayNightCycle
from settings import _normalize_blackhole_quality


def _lensed_source(tx, ty, theta_e=1.0):
    """Python mirror of the GLSL point-lens map in the tangent plane.

    ``beta = theta * (1 - thetaE^2 / |theta|^2)``.  Keep this in sync with
    the fragment shader; these tests guard the mathematical properties.
    """
    r2 = tx * tx + ty * ty
    factor = 1.0 - (theta_e * theta_e) / max(r2, 1e-4)
    return tx * factor, ty * factor


class SkyShaderTests(unittest.TestCase):
    def test_initialize_fails_gracefully_without_light(self):
        sky = SkyShader(None)
        self.assertFalse(sky.initialize())
        self.assertFalse(sky.render(SimpleNamespace()))

    def test_initialize_skipped_when_shaders_disabled(self):
        light = SimpleNamespace(enabled=False, elapsed=0.0)
        sky = SkyShader(light)
        self.assertFalse(sky.initialize())
        scene = SimpleNamespace(WIDTH=854, HEIGHT=480,
                                player=SimpleNamespace(position=(0, 0, 0)))
        self.assertFalse(sky.render(scene))

    def test_day_night_binding_validates_cycle_type(self):
        sky = SkyShader(None)
        sky.day_night = DayNightCycle(13000)
        self.assertIsNotNone(sky.day_night)
        sky.day_night = SimpleNamespace()
        self.assertIsNotNone(sky.day_night)  # ignored, keeps the valid cycle
        sky.day_night = None
        self.assertIsNone(sky.day_night)

    def test_bh_direction_is_the_anti_solar_point(self):
        # At midnight (sun_angle = 3*pi/2) the sun is at the nadir, so the
        # black hole must sit at the zenith.
        x, y, z = SkyShader._bh_direction(3 * math.pi / 2)
        self.assertAlmostEqual(y, 1.0, places=6)
        self.assertAlmostEqual(x, 0.0, places=6)
        self.assertAlmostEqual(z, 0.0, places=6)

        # The hole is always exactly opposite the sun on the orbit, and it
        # is a unit vector on the celestial sphere.
        for angle in (math.pi, 3.6, 5.5, 2 * math.pi):
            direction = SkyShader._bh_direction(angle)
            self.assertAlmostEqual(sum(c * c for c in direction), 1.0,
                                   places=6)
            sun = (0.0, math.sin(angle), -math.cos(angle))
            dot = sum(a * b for a, b in zip(direction, sun))
            self.assertAlmostEqual(dot, -1.0, places=6)

    def test_camera_basis_is_orthonormal(self):
        for rotation in ([0, 0], [25, 90], [-40, 210], [80, 305]):
            forward, right, up = SkyShader._camera_basis(rotation)
            for vector in (forward, right, up):
                self.assertAlmostEqual(sum(c * c for c in vector), 1.0,
                                       places=6)
            dot_fr = sum(a * b for a, b in zip(forward, right))
            dot_fu = sum(a * b for a, b in zip(forward, up))
            dot_ru = sum(a * b for a, b in zip(right, up))
            self.assertAlmostEqual(dot_fr, 0.0, places=6)
            self.assertAlmostEqual(dot_fu, 0.0, places=6)
            self.assertAlmostEqual(dot_ru, 0.0, places=6)
            # the right vector stays level with the horizon
            self.assertAlmostEqual(right[1], 0.0, places=6)

    def test_off_quality_skips_rendering_entirely(self):
        light = SimpleNamespace(enabled=False, elapsed=0.0)
        sky = SkyShader(light)
        sky.day_night = DayNightCycle(18000)  # midnight: stars fully visible
        sky.set_quality("OFF")
        scene = SimpleNamespace(WIDTH=854, HEIGHT=480, fov=100,
                                player=SimpleNamespace(rotation=[0, 0]))
        # OFF must return before touching any GL state, even uninitialised.
        self.assertFalse(sky.render(scene))

    def test_set_quality_rejects_unknown_values(self):
        sky = SkyShader(None)
        sky.set_quality("banana")
        self.assertEqual(sky.quality, "HIGH")
        sky.set_quality("low")
        self.assertEqual(sky.quality, "LOW")
        sky.set_quality("OFF")
        self.assertEqual(sky.quality, "OFF")

    def test_blackhole_quality_setting_normalises(self):
        self.assertEqual(_normalize_blackhole_quality("off"), "OFF")
        self.assertEqual(_normalize_blackhole_quality("Low"), "LOW")
        self.assertEqual(_normalize_blackhole_quality("HIGH"), "HIGH")
        self.assertEqual(_normalize_blackhole_quality("banana"), "HIGH")
        self.assertEqual(_normalize_blackhole_quality(None), "HIGH")

    def test_point_lens_is_identity_in_the_far_field(self):
        # The point-lens map deviates from identity by exactly thetaE^2/r^2,
        # so it must approach the identity as r grows.  Compare against the
        # closed form rather than a fixed tolerance.
        for tx, ty in ((10.0, 0.0), (0.0, 20.0), (30.0, -40.0)):
            r = math.hypot(tx, ty)
            expected = 1.0 - 1.0 / (r * r)
            sx, sy = _lensed_source(tx, ty)
            self.assertAlmostEqual(sx, tx * expected, places=6)
            self.assertAlmostEqual(sy, ty * expected, places=6)
        # and the residual is small in the far field
        sx, sy = _lensed_source(20.0, 0.0)
        self.assertLess(abs(sx - 20.0) / 20.0, 0.01)

    def test_point_lens_vanishes_at_einstein_radius(self):
        # beta = 0 at |theta| = thetaE -> the Einstein ring / caustic.
        for direction in ((1.0, 0.0), (0.0, 1.0), (0.6, 0.8)):
            sx, sy = _lensed_source(*direction)
            self.assertAlmostEqual(math.hypot(sx, sy), 0.0, places=4)

    def test_point_lens_source_radius_is_monotonic_outside_shadow(self):
        # As the image radius grows, the source radius must also grow
        # (no folding back like the previous spiral remap).
        radii = [1.0, 1.2, 1.5, 2.0, 3.0, 6.0, 10.0]
        sources = [math.hypot(*_lensed_source(r, 0.0)) for r in radii]
        self.assertEqual(sources, sorted(sources))
        for r, s in zip(radii, sources):
            self.assertLess(s, r)  # every image is pulled inward


if __name__ == "__main__":
    unittest.main()
