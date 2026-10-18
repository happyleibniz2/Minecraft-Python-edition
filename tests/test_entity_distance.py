"""Entity distance tiers: update, freeze, despawn (Scene.update_entities)."""

import unittest
from types import SimpleNamespace

from game.Scene import Scene


def make_entity(position):
    """A fake entity whose update/die calls are recorded on the entity."""
    entity = SimpleNamespace(position=list(position), is_dead=False,
                             calls=[])
    entity.update = lambda dt: entity.calls.append("update")
    entity.die = lambda: entity.calls.append("die")
    return entity


class EntityDistanceTierTests(unittest.TestCase):
    def make_scene(self, entities, player_position=(0.0, 70.0, 0.0)):
        scene = Scene.__new__(Scene)
        scene.entity = list(entities)
        scene.player = SimpleNamespace(position=list(player_position))
        return scene

    def test_nearby_entities_update(self):
        near = make_entity((30.0, 70, 30.0))
        scene = self.make_scene([near])
        scene.update_entities(0.016)
        self.assertEqual(near.calls, ["update"])

    def test_far_entities_freeze_without_despawning(self):
        far = make_entity((100.0, 70, 0.0))
        scene = self.make_scene([far])
        scene.update_entities(0.016)
        # beyond the simulation radius (64) but inside despawn (128):
        # neither updated nor removed - it just stops costing AI time
        self.assertEqual(far.calls, [])
        self.assertEqual(len(scene.entity), 1)

    def test_distant_entities_despawn(self):
        distant = make_entity((200.0, 70, 0.0))
        distant.die = (lambda: (distant.calls.append("die"),
                                scene.entity.remove(distant)))
        scene = self.make_scene([distant])
        scene.update_entities(0.016)
        self.assertEqual(distant.calls, ["die"])
        self.assertEqual(scene.entity, [])

    def test_boundary_distances(self):
        edge_sim = make_entity((Scene.ENTITY_SIMULATION_DISTANCE, 70, 0.0))
        edge_despawn = make_entity(
            (Scene.ENTITY_DESPAWN_DISTANCE + 0.5, 70, 0.0))
        scene = self.make_scene([edge_sim, edge_despawn])
        scene.update_entities(0.016)
        # exactly at the simulation radius still ticks; just past the
        # despawn radius is removed
        self.assertEqual(edge_sim.calls, ["update"])
        self.assertEqual(edge_despawn.calls, ["die"])

    def test_vertical_distance_alone_does_not_freeze(self):
        """Tiers are horizontal, like vanilla: a mob directly below the
        player keeps simulating even dozens of blocks down."""
        below = make_entity((0.0, 0.0, 0.0))
        scene = self.make_scene([below], player_position=(0.0, 100.0, 0.0))
        scene.update_entities(0.016)
        self.assertEqual(below.calls, ["update"])


if __name__ == "__main__":
    unittest.main()
