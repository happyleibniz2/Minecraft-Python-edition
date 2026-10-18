import unittest
from types import SimpleNamespace

import settings
from game.entity.Player import Player


class RecordingLight:
    def __init__(self):
        self.calls = []

    def addLightSource(self, x, y, z):
        self.calls.append(("add", (x, y, z)))

    def removeLightSource(self, x, y, z):
        self.calls.append(("remove", (x, y, z)))


def make_player(light, held=("torch", 5)):
    gl = SimpleNamespace(
        light=light,
        allowEvents={"collisions": True},
        fov=100,
    )
    player = Player.__new__(Player)
    player.position = [1.4, 70.2, -3.6]
    player.rotation = [0, 0]
    player.playerDead = False
    player.gl = gl
    player._hand_light_cell = None
    player.inventory = SimpleNamespace(
        activeInventory=0,
        inventory={0: list(held)},
    )
    return player


class HandLightTests(unittest.TestCase):
    def setUp(self):
        self.original = settings.DYNAMIC_LIGHTING
        settings.DYNAMIC_LIGHTING = True

    def tearDown(self):
        settings.DYNAMIC_LIGHTING = self.original

    def test_holding_a_torch_lights_the_players_block(self):
        light = RecordingLight()
        player = make_player(light)
        player.update_hand_light()
        self.assertEqual(light.calls, [("add", (1, 70, -4))])
        self.assertEqual(player._hand_light_cell, (1, 70, -4))

        # staying in the same block must not thrash the light source
        light.calls.clear()
        player.update_hand_light()
        self.assertEqual(light.calls, [])

    def test_moving_relocates_the_light(self):
        light = RecordingLight()
        player = make_player(light)
        player.update_hand_light()
        player.position = [3.9, 70.0, -3.4]
        player.update_hand_light()
        self.assertEqual(light.calls,
                         [("add", (1, 70, -4)), ("remove", (1, 70, -4)),
                          ("add", (4, 70, -3))])

    def test_switching_items_or_dying_removes_the_light(self):
        light = RecordingLight()
        player = make_player(light)
        player.update_hand_light()

        player.inventory.inventory[0] = ["stone", 5]
        player.update_hand_light()
        self.assertEqual(light.calls[-1], ("remove", (1, 70, -4)))
        self.assertIsNone(player._hand_light_cell)

        light.calls.clear()
        player.inventory.inventory[0] = ["torch", 5]
        player.update_hand_light()
        self.assertEqual(light.calls, [("add", (1, 70, -4))])

        player.playerDead = True
        player.update_hand_light()
        self.assertEqual(light.calls[-1], ("remove", (1, 70, -4)))

    def test_setting_toggle_gates_the_light(self):
        light = RecordingLight()
        player = make_player(light)
        settings.DYNAMIC_LIGHTING = False
        player.update_hand_light()
        self.assertEqual(light.calls, [])
        self.assertIsNone(player._hand_light_cell)

        settings.DYNAMIC_LIGHTING = True
        player.update_hand_light()
        self.assertEqual(light.calls, [("add", (1, 70, -4))])

        settings.DYNAMIC_LIGHTING = False
        player.update_hand_light()
        self.assertEqual(light.calls[-1], ("remove", (1, 70, -4)))


if __name__ == "__main__":
    unittest.main()
