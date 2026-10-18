import os
import struct
import unittest
from types import SimpleNamespace

from game.entity.Chicken import Chicken
from game.entity.Cow import Cow
from game.entity.Creeper import Creeper
from game.entity.Pig import Pig
from game.entity.Player import Player
from game.entity.PlayerAvatar import PlayerAvatar
from game.entity.SpawnEggs import SPAWN_EGGS
from game.entity.Zombie import Zombie
from game.Scene import Scene


def _png_size(path):
    with open(path, "rb") as f:
        f.seek(16)
        return struct.unpack(">II", f.read(8))


class NewEntityTests(unittest.TestCase):
    def test_mob_textures_exist_with_the_classic_64x32_layout(self):
        for entity, expected in (
            (Pig, (64, 32)),
            (Chicken, (64, 32)),
            (Creeper, (64, 32)),
            (Cow, (64, 32)),
        ):
            self.assertTrue(os.path.isfile(entity.TEXTURE_PATH),
                            f"missing texture: {entity.TEXTURE_PATH}")
            self.assertEqual(_png_size(entity.TEXTURE_PATH), expected)
            self.assertEqual(entity.TEXTURE_SIZE, expected)

    def test_entity_registry_knows_every_spawn_egg_id(self):
        scene = SimpleNamespace(mod_entity_types={})
        types = Scene.entity_types(scene)
        for entity_id in SPAWN_EGGS:
            self.assertIn(entity_id, types,
                          f"spawn egg target missing from the registry: {entity_id}")
        self.assertIs(types["pig"], Pig)
        self.assertIs(types["creeper"], Creeper)
        self.assertIs(types["chicken"], Chicken)

    def test_new_spawn_eggs_use_the_official_minecraft_colours(self):
        self.assertEqual(SPAWN_EGGS["pig"], (0xF0A5A2, 0xDB635F))
        self.assertEqual(SPAWN_EGGS["creeper"], (0x0DA70B, 0x000000))
        self.assertEqual(SPAWN_EGGS["chicken"], (0xA1A1A1, 0xFF0000))


class ThirdPersonCameraTests(unittest.TestCase):
    def test_first_person_is_untouched(self):
        self.assertEqual(Player.third_person_angles((30.0, 90.0), 1),
                         (30.0, 90.0, 0.0))

    def test_rear_view_keeps_orientation_and_pulls_back(self):
        pitch, yaw, back = Player.third_person_angles((30.0, 90.0), 2)
        self.assertEqual((pitch, yaw), (30.0, 90.0))
        self.assertGreater(back, 0.0)

    def test_front_view_mirrors_yaw_and_pitch(self):
        pitch, yaw, back = Player.third_person_angles((30.0, 90.0), 3)
        self.assertEqual(pitch, -30.0)
        self.assertEqual(yaw % 360, (90.0 + 180.0) % 360)
        self.assertGreater(back, 0.0)


class PlayerAvatarTests(unittest.TestCase):
    def test_skin_exists_and_uses_the_wide_steve_layout(self):
        self.assertTrue(os.path.isfile(PlayerAvatar.SKIN_PATH))
        self.assertEqual(_png_size(PlayerAvatar.SKIN_PATH), (64, 64))

    def test_construction_is_gl_free(self):
        avatar = PlayerAvatar(SimpleNamespace())
        self.assertFalse(avatar._texture_loaded)
        self.assertEqual(avatar.limb_amount, 0.0)

    def test_walk_cycle_advances_with_movement(self):
        avatar = PlayerAvatar(SimpleNamespace())
        avatar.update_limb_state(0.05, 0.2)   # walking at 4 blocks/second
        self.assertGreater(avatar.limb_swing, 0.0)
        self.assertGreater(avatar.limb_amount, 0.0)
        # idling calms the animation down
        before = avatar.limb_amount
        avatar.update_limb_state(0.05, 0.0)
        self.assertLess(avatar.limb_amount, before)


if __name__ == "__main__":
    unittest.main()
