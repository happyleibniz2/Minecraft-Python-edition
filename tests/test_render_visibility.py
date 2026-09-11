import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from game.Frustum import Frustum
from game.Scene import Scene
from game.blocks.CubeHandler import CubeHandler


class RenderVisibilityTests(unittest.TestCase):
    def test_frustum_keeps_aabb_inside_boundary_margin(self):
        frustum = Frustum()
        frustum.planes = np.array([
            (1, 0, 0, 0),
            (0, 0, 0, 100),
            (0, 0, 0, 100),
            (0, 0, 0, 100),
            (0, 0, 0, 100),
            (0, 0, 0, 100),
        ], dtype=np.float32)
        self.assertTrue(frustum.cube_in_frustum(-1, -1, -1, -0.25, 1, 1))
        self.assertFalse(frustum.cube_in_frustum(-2, -1, -1, -1.0, 1, 1))

    def test_chunk_range_uses_nearest_aabb_point_not_center(self):
        handler = CubeHandler.__new__(CubeHandler)
        handler.RENDER_CHUNK_SIZE = (16, 8, 16)
        chunk = SimpleNamespace(cx=6, cy=0, cz=0)
        distance = handler.chunk_distance_squared(chunk, (7.99, 4, 8))
        self.assertAlmostEqual(distance, 87.51 ** 2, places=3)
        self.assertLess(distance, 96 ** 2)

    def test_binary_glass_uses_cutout_render_type(self):
        self.assertEqual(
            CubeHandler.block_render_type("glass", ("glass", "leaves_oak")),
            "alpha",
        )
        self.assertEqual(CubeHandler.block_render_type("water", ()), "blend")
        self.assertEqual(CubeHandler.block_render_type("stone", ()), "solid")

    def test_projection_uses_depth_safe_near_plane(self):
        self.assertGreaterEqual(Scene.NEAR_PLANE, 0.25)

    def test_2d_and_3d_projection_switch_depth_state(self):
        scene = SimpleNamespace(WIDTH=854, HEIGHT=480, fov=100,
                                NEAR_PLANE=Scene.NEAR_PLANE)
        common = (
            mock.patch("game.Scene.glMatrixMode"),
            mock.patch("game.Scene.glLoadIdentity"),
            mock.patch("game.Scene.gluOrtho2D"),
            mock.patch("game.Scene.gluPerspective"),
        )
        with common[0], common[1], common[2], common[3], \
                mock.patch("game.Scene.glDisable") as disable, \
                mock.patch("game.Scene.glEnable") as enable, \
                mock.patch("game.Scene.glDepthMask") as depth_mask, \
                mock.patch("game.Scene.glDepthFunc") as depth_func:
            Scene.set2d(scene)
            disable.assert_called_with(0x0B71)  # GL_DEPTH_TEST
            depth_mask.assert_called_with(0)

            depth_mask.reset_mock()
            Scene.set3d(scene)
            enable.assert_called_with(0x0B71)
            depth_mask.assert_called_with(1)
            depth_func.assert_called_with(0x0201)  # GL_LESS


if __name__ == "__main__":
    unittest.main()
