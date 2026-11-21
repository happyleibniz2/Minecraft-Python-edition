import unittest
from types import SimpleNamespace
from unittest import mock

import numpy as np

from game.Frustum import Frustum
from game.Scene import Scene
from game.blocks.CubeHandler import CubeHandler
from game.world.worldGenerator import worldGenerator


def _make_render_handler(chunks):
    """A CubeHandler whose only job is exercising ``render``'s pipeline."""
    handler = CubeHandler.__new__(CubeHandler)
    handler.RENDER_CHUNK_SIZE = (16, 8, 16)
    handler.frustum = Frustum()
    # Plane normals of zero keep every AABB on the visible side.
    handler.frustum.planes = np.tile(
        np.array((0, 0, 0, 100), dtype=np.float32), (6, 1)
    )
    # ``extract`` would read the live GL matrices; the test controls the
    # planes directly instead.
    handler.frustum.extract = lambda: None
    handler.visible_water_chunks = []
    render_order = []
    for chunk in chunks:
        chunk.render_opaque = (
            lambda chunk=chunk: render_order.append(("opaque", chunk)))
        chunk.render_cutout = lambda chunk=chunk: None
        chunk.render_overlay = lambda chunk=chunk: None
    handler._render_order = render_order
    handler._iter_chunks_near = lambda center, radius: iter(chunks)
    return handler


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
            self.assertTrue(scene._in_3d)
            Scene.set2d(scene)
            self.assertFalse(scene._in_3d)

    def test_batch_frustum_matches_scalar_test(self):
        rng = np.random.default_rng(2024)
        frustum = Frustum()
        planes = rng.normal(size=(6, 4)).astype(np.float32)
        planes[:, :3] /= np.linalg.norm(planes[:, :3], axis=1, keepdims=True)
        frustum.planes = planes

        boxes = rng.uniform(-40, 40, size=(400, 6)).astype(np.float32)
        low = np.minimum(boxes[:, :3], boxes[:, 3:])
        high = np.maximum(boxes[:, :3], boxes[:, 3:])
        boxes = np.concatenate((low, high), axis=1)

        batch = frustum.cube_in_frustum_batch(boxes)
        scalar = np.array(
            [frustum.cube_in_frustum(*box) for box in boxes]
        )
        np.testing.assert_array_equal(batch, scalar)

    def test_render_draws_visible_chunks_front_to_back(self):
        near = SimpleNamespace(cx=0, cy=0, cz=0)
        middle = SimpleNamespace(cx=2, cy=0, cz=0)
        far = SimpleNamespace(cx=5, cy=0, cz=0)
        handler = _make_render_handler([far, near, middle])

        patches = (
            mock.patch("game.blocks.CubeHandler.glDisable"),
            mock.patch("game.blocks.CubeHandler.glEnable"),
            mock.patch("game.blocks.CubeHandler.glDepthMask"),
            mock.patch("game.blocks.CubeHandler.glAlphaFunc"),
            mock.patch("game.blocks.CubeHandler.glBlendFunc"),
            mock.patch("game.blocks.CubeHandler.glPolygonOffset"),
            mock.patch(
                "game.blocks.CubeHandler.settings.DISTANCE_CULLING", False
            ),
        )
        with patches[0], patches[1], patches[2], patches[3], \
                patches[4], patches[5], patches[6]:
            handler.render((0.0, 0.0, 0.0))

        order = [chunk for _, chunk in handler._render_order]
        self.assertEqual(order, [near, middle, far])
        self.assertEqual(
            handler.visible_water_chunks, [far, middle, near]
        )

    def test_render_skips_when_frustum_rejects_every_chunk(self):
        handler = _make_render_handler([SimpleNamespace(cx=0, cy=0, cz=0)])
        handler.frustum.planes = np.tile(
            np.array((0, 0, 0, -100), dtype=np.float32), (6, 1)
        )
        with mock.patch(
                "game.blocks.CubeHandler.settings.DISTANCE_CULLING", False
        ):
            handler.render((0.0, 0.0, 0.0))
        self.assertEqual(handler._render_order, [])
        self.assertEqual(handler.visible_water_chunks, [])

    def test_flat_worker_payload_is_reshaped_before_ingest(self):
        generator = worldGenerator(None, seed=99)
        height = generator.MAX_Y - generator.MIN_Y + 1
        shape = (height, 4, 4)
        volume = np.zeros(shape, dtype=np.uint8)
        # One grass block at the bottom of the volume.
        volume[128, 1, 2] = 3

        added = generator._ingest_payload(((0, 0), volume.reshape(-1)))
        self.assertEqual(added, 1)
        self.assertEqual(
            generator.blocks[(0 + 1, generator.MIN_Y + 128, 0 + 2)], "grass"
        )


if __name__ == "__main__":
    unittest.main()
