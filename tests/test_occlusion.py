import unittest
from types import SimpleNamespace
from unittest import mock

from game.Scene import Scene
from game.blocks.CubeHandler import CubeHandler
from game.entity.Entity import Entity


class OcclusionTests(unittest.TestCase):
    def make_handler(self):
        handler = CubeHandler.__new__(CubeHandler)
        handler.RENDER_CHUNK_SIZE = (16, 8, 16)
        handler.cubes = {}
        handler.render_chunks = {}
        return handler

    def add_cube(self, handler, position, render_type="solid", dirty=False):
        handler.cubes[position] = SimpleNamespace(type=render_type)
        handler.render_chunks[handler._get_chunk_key(position)] = SimpleNamespace(dirty=dirty)

    def test_segment_dda_skips_transparency_and_requires_committed_mesh(self):
        handler = self.make_handler()
        self.add_cube(handler, (0, 2, -2), "alpha")
        self.add_cube(handler, (0, 2, -4), "solid")

        block, distance = handler.first_committed_solid_on_segment(
            (0, 2, 0), (0, 2, -10)
        )
        self.assertEqual(block, (0, 2, -4))
        self.assertAlmostEqual(distance, 3.5)

        handler.render_chunks[handler._get_chunk_key(block)].dirty = True
        self.assertEqual(
            handler.first_committed_solid_on_segment((0, 2, 0), (0, 2, -10)),
            (None, None),
        )

    def test_entity_is_hidden_only_when_one_block_covers_all_visual_corners(self):
        handler = self.make_handler()
        self.add_cube(handler, (0, 2, -5), "solid")
        scene = SimpleNamespace(cubes=handler)
        camera = (0, 2, 0)

        covered = (-0.3, 1.7, -10.3, 0.3, 2.3, -9.7)
        exposed = (-2.0, 1.7, -10.3, 2.0, 2.3, -9.7)
        self.assertEqual(
            Scene._prove_entity_occluded(scene, camera, covered),
            (0, 2, -5),
        )
        self.assertIsNone(Scene._prove_entity_occluded(scene, camera, exposed))

    def test_entity_cache_requires_confirmation_and_reveals_on_dirty_blocker(self):
        handler = self.make_handler()
        self.add_cube(handler, (0, 2, -5), "solid")
        handler.frustum = SimpleNamespace(cube_in_frustum=lambda *bounds: True)
        entity = SimpleNamespace(
            position=[0, 2, -10], is_dead=False,
            get_visibility_bounds=lambda: (-0.3, 1.7, -10.3, 0.3, 2.3, -9.7),
        )
        scene = Scene.__new__(Scene)
        scene.cubes = handler
        scene.entity = [entity]
        scene.player = SimpleNamespace(
            position=[0, 2, 0], shift=0, cameraShake=[0, False],
        )
        scene.light = SimpleNamespace(elapsed=1.0)
        scene._entity_occlusion = {}
        scene._occlusion_cursor = 0

        self.assertEqual(scene._visible_entities(), [entity])
        scene.player.position[0] += 0.001
        self.assertEqual(scene._visible_entities(), [])
        handler.render_chunks[handler._get_chunk_key((0, 2, -5))].dirty = True
        self.assertEqual(scene._visible_entities(), [entity])

    def test_default_visibility_bounds_cover_tall_animated_models(self):
        entity = Entity.__new__(Entity)
        entity.position = [0, 0.25, -10]
        entity.width = 0.6
        entity.height = 1.95
        entity.get_hitbox = Entity.get_hitbox.__get__(entity, Entity)
        bounds = Entity.get_visibility_bounds(entity)
        self.assertGreaterEqual(bounds[4], entity.position[1] + 1.81)

    def test_shadow_pass_does_not_leak_batched_entity_into_world_batch(self):
        created = []

        class Batch:
            def __init__(self):
                self.entries = []
                self.disposed = False
                created.append(self)

            def draw(self):
                pass

            def dispose(self):
                self.disposed = True

        world_batch = Batch()
        scene = SimpleNamespace()
        scene.stuffBatch = world_batch
        scene.player = SimpleNamespace(position=[0, 2, 0], is_spectator=True)
        scene.dayNight = SimpleNamespace(light_direction=(0, 1, 0))
        scene.light = SimpleNamespace(
            SHADOW_RADIUS=48,
            should_update_shadow=lambda *args: True,
            begin_shadow_pass=lambda *args: True,
            end_shadow_pass=lambda: None,
        )
        scene.cubes = SimpleNamespace(render_shadow=lambda *args: None)
        scene.drawPlayerShadowCaster = lambda: None
        scene.entity = [SimpleNamespace(
            position=[0, 2, -10], is_dead=False,
            render=lambda dt: scene.stuffBatch.entries.append("entity"),
        )]

        with mock.patch("game.Scene.DisposableBatch", Batch):
            Scene.renderShadowMap(scene)
        self.assertEqual(world_batch.entries, [])
        self.assertIs(scene.stuffBatch, world_batch)
        self.assertTrue(created[-1].disposed)


if __name__ == "__main__":
    unittest.main()
