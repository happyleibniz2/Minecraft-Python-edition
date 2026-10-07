import unittest
from types import SimpleNamespace

import settings
from game.world.Clouds import Clouds
from settings import (
    CLOUD_QUALITY_LEVELS,
    _normalize_cloud_quality,
    set_cloud_quality,
    save_options,
)


class CloudQualityTests(unittest.TestCase):
    def test_level_names_are_fixed(self):
        self.assertEqual(
            CLOUD_QUALITY_LEVELS, ("POTATO", "LOW", "MEDIUM", "HIGH", "GPU"))

    def test_normalize_rejects_unknown_and_accepts_case(self):
        self.assertEqual(_normalize_cloud_quality("potato"), "POTATO")
        self.assertEqual(_normalize_cloud_quality("gpu"), "GPU")
        self.assertEqual(_normalize_cloud_quality("banana"), "HIGH")
        self.assertEqual(_normalize_cloud_quality(None), "HIGH")

    def test_potato_uses_the_billboard_fallback(self):
        # POTATO must skip the raymarch entirely.
        self.assertIsNone(Clouds.QUALITY_PARAMS["POTATO"])

    def test_tiers_scale_up_monotonically(self):
        params = Clouds.QUALITY_PARAMS
        steps = [params[q]["steps"] for q in ("LOW", "MEDIUM", "HIGH", "GPU")]
        sun_samples = [params[q]["sun_samples"]
                       for q in ("LOW", "MEDIUM", "HIGH", "GPU")]
        self.assertEqual(steps, sorted(steps))
        self.assertEqual(sun_samples, sorted(sun_samples))
        # LOW is the cheap tier: no powder or dual-lobe phase.
        self.assertEqual(params["LOW"]["powder"], 0)
        self.assertEqual(params["LOW"]["dual_lobe"], 0)
        # HIGH and GPU unlock the full lighting model.
        self.assertEqual(params["HIGH"]["powder"], 1)
        self.assertEqual(params["HIGH"]["dual_lobe"], 1)
        self.assertEqual(params["GPU"]["dual_lobe"], 1)
        self.assertGreater(params["GPU"]["steps"], params["HIGH"]["steps"])

    def test_set_quality_is_safe_without_a_gl_context(self):
        clouds = Clouds.__new__(Clouds)
        clouds.set_quality("gpu")
        self.assertEqual(clouds.quality, "GPU")
        self.assertEqual(clouds._params["steps"], 32)
        clouds.set_quality("banana")
        self.assertEqual(clouds.quality, "MEDIUM")
        clouds.set_quality("POTATO")
        self.assertIsNone(clouds._params)

    def test_playable_tiers_render_at_half_resolution(self):
        params = Clouds.QUALITY_PARAMS
        # the affordable tiers raymarch at half res; only the cinematic
        # "I PAID FOR THE WHOLE GPU!" tier runs at full resolution
        self.assertEqual(params["LOW"]["resolution_scale"], 0.5)
        self.assertEqual(params["MEDIUM"]["resolution_scale"], 0.5)
        self.assertEqual(params["HIGH"]["resolution_scale"], 0.5)
        self.assertEqual(params["GPU"]["resolution_scale"], 1.0)

    def test_vsync_setting_loads_as_a_bool(self):
        # vsync off is what uncaps the frame rate above the monitor refresh;
        # it is applied when the window is created.
        self.assertIsInstance(settings.VSYNC, bool)
        self.assertTrue(callable(settings.set_vsync))

    def test_scaled_render_restores_the_full_window_viewport(self):
        """The FBO pass shrinks the viewport; the fullscreen composite must
        run at the full window size (the down-left-quarter bug)."""
        from unittest import mock
        from game.world import Clouds as CloudsModule

        clouds = Clouds.__new__(Clouds)
        clouds.gl = SimpleNamespace(WIDTH=854, HEIGHT=480)
        clouds._params = {"resolution_scale": 0.5}
        clouds._cloud_fbo = 7
        clouds._cloud_texture = 9
        clouds._cloud_fbo_size = (427, 240)
        clouds._ensure_cloud_buffer = lambda w, h: None
        clouds._draw_cloud_quad = lambda player, cycle: None
        player = SimpleNamespace()
        cycle = SimpleNamespace()

        viewport_calls = []

        def fake_viewport(x, y, w, h):
            viewport_calls.append((x, y, w, h))

        with mock.patch.object(CloudsModule, "glViewport", fake_viewport), \
                mock.patch.object(CloudsModule, "glPushAttrib"), \
                mock.patch.object(CloudsModule, "glPopAttrib"), \
                mock.patch.object(CloudsModule, "glPushMatrix"), \
                mock.patch.object(CloudsModule, "glPopMatrix"), \
                mock.patch.object(CloudsModule, "glMatrixMode"), \
                mock.patch.object(CloudsModule, "glLoadIdentity"), \
                mock.patch.object(CloudsModule, "glDisable"), \
                mock.patch.object(CloudsModule, "glEnable"), \
                mock.patch.object(CloudsModule, "glDepthMask"), \
                mock.patch.object(CloudsModule, "glBlendFunc"), \
                mock.patch.object(CloudsModule, "glBindTexture"), \
                mock.patch.object(CloudsModule, "glBindFramebuffer"), \
                mock.patch.object(CloudsModule, "glClearColor"), \
                mock.patch.object(CloudsModule, "glClear"), \
                mock.patch.object(CloudsModule, "glBegin"), \
                mock.patch.object(CloudsModule, "glEnd"), \
                mock.patch.object(CloudsModule, "glTexCoord2f"), \
                mock.patch.object(CloudsModule, "glVertex2f"):
            clouds._render_volume_scaled(player, cycle, 0.5)

        # first call sizes the FBO pass, the LAST call must restore the full
        # window before the composite quad is drawn
        self.assertEqual(viewport_calls[0], (0, 0, 427, 240))
        self.assertEqual(viewport_calls[-1], (0, 0, 854, 480))


if __name__ == "__main__":
    unittest.main()
