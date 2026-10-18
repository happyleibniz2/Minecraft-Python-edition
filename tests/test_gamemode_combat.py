"""Gamemode/combat consistency, locked by the creative-survival audit.

The audit behind these tests: ``Player.attackEntity`` has no creative gate
(vanilla creative players attack), so switching creative -> survival must
never disable attacking. The bugs that COULD lock the player out of combat
were (a) the legacy P spectator toggle leaving ``is_creative`` set alongside
``is_spectator`` (spectator blocks attacks) and (b) a modal window left open
at the moment of death re-grabbing ``allowEvents`` after respawn. Both are
fixed; these tests pin the contracts.
"""

import unittest
from types import SimpleNamespace

from game.GUI.ModalWindow import ModalWindow
from game.entity.Player import Player


def make_player(**flags):
    player = Player.__new__(Player)
    player.is_spectator = False
    player.is_creative = False
    player.playerDead = False
    player.attack_cooldown = 1.0  # fully charged swing
    player.inventory = SimpleNamespace(
        inventory={0: ["", 0]},   # bare hands
        activeInventory=0,
    )
    for key, value in flags.items():
        setattr(player, key, value)
    return player


class RecordingMob:
    def __init__(self):
        self.hits = []

    def hurt(self, damage, attacker=None):
        self.hits.append(damage)
        return True


class GamemodeCombatTests(unittest.TestCase):
    def test_creative_player_can_attack(self):
        """Vanilla parity: creative mode does not disable attacking."""
        player = make_player(is_creative=True)
        mob = RecordingMob()
        self.assertTrue(player.attackEntity(mob))
        self.assertEqual(mob.hits, [1.0])  # fists deal one damage

    def test_creative_then_survival_still_deals_damage(self):
        """The reported repro: switching back must not lose the attack."""
        player = make_player()

        # /gamemode creative
        player.is_creative = True
        player.is_spectator = False
        # /gamemode survival
        player.is_creative = False
        player.is_spectator = False

        mob = RecordingMob()
        self.assertTrue(player.attackEntity(mob))
        self.assertEqual(mob.hits, [1.0])

    def test_spectator_blocks_attacks_even_flagged_creative(self):
        """The mixed state the legacy P key used to produce.

        With ``is_spectator`` set the attack is blocked no matter what
        ``is_creative`` says - which is why the P toggle now clears the
        creative flag when it enters spectator.
        """
        player = make_player(is_spectator=True, is_creative=True)
        mob = RecordingMob()
        self.assertFalse(player.attackEntity(mob))
        self.assertEqual(mob.hits, [])

    def test_dead_player_cannot_attack(self):
        player = make_player(playerDead=True)
        mob = RecordingMob()
        self.assertFalse(player.attackEntity(mob))

    def test_attack_consumes_the_cooldown(self):
        player = make_player()
        mob = RecordingMob()
        self.assertTrue(player.attackEntity(mob))
        self.assertEqual(player.attack_cooldown, 0.0)
        # an immediate second swing is rejected until the cooldown refills
        self.assertFalse(player.attackEntity(mob))
        self.assertEqual(len(mob.hits), 1)


class GhostWindowTests(unittest.TestCase):
    """A modal window open at death must be destroyable without its ESC."""

    def make_scene(self):
        return SimpleNamespace(
            updateEvents=[],
            allowEvents={"keyboardAndMouse": False, "grabMouse": False,
                         "movePlayer": False, "showCrosshair": False},
        )

    def test_destroy_removes_the_frame_hook_and_restores_input(self):
        scene = self.make_scene()
        closed = []
        window = ModalWindow(scene)
        window.closeEvent = lambda: closed.append(True)
        window.setWindow(None)

        window.show()
        self.assertIn(window.drawWindow, scene.updateEvents)
        self.assertTrue(window.visible)

        window.destroyWindow()
        self.assertNotIn(window.drawWindow, scene.updateEvents)
        self.assertFalse(window.visible)
        # every input channel the per-frame drawWindow grabbed is released
        for event in scene.allowEvents.values():
            self.assertTrue(event)
        self.assertEqual(closed, [True])

    def test_destroy_without_show_is_harmless(self):
        scene = self.make_scene()
        window = ModalWindow(scene)
        window.destroyWindow()
        self.assertFalse(window.visible)
        for event in scene.allowEvents.values():
            self.assertTrue(event)


if __name__ == "__main__":
    unittest.main()
