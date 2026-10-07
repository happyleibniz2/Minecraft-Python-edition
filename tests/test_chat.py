import unittest
from types import SimpleNamespace

import pygame

from game.GUI.Chat import Chat
from game.world.DayNightCycle import DayNightCycle


def _scene_stub():
    return SimpleNamespace(
        allowEvents={"movePlayer": True},
        player=SimpleNamespace(is_spectator=False, is_creative=False),
        dayNight=DayNightCycle(1000),
    )


class ChatTests(unittest.TestCase):
    def setUp(self):
        self.scene = _scene_stub()
        self.chat = Chat(self.scene)

    def _last_message(self):
        text, color, _stamp = self.chat.history[-1]
        return text, color

    def test_open_and_close_restore_player_control(self):
        self.chat.open()
        self.assertTrue(self.chat.is_open)
        self.assertFalse(self.scene.allowEvents["movePlayer"])
        self.chat.close()
        self.assertFalse(self.chat.is_open)
        self.assertTrue(self.scene.allowEvents["movePlayer"])

    def test_keydown_types_into_the_input(self):
        self.chat.open()
        for char in "/day set night":
            event = pygame.event.Event(
                pygame.KEYDOWN, key=ord(char), unicode=char)
            self.chat.handle_keydown(event)
        self.assertEqual(self.chat.input, "/day set night")

        backspace = pygame.event.Event(pygame.KEYDOWN, key=pygame.K_BACKSPACE)
        self.chat.handle_keydown(backspace)
        self.assertEqual(self.chat.input, "/day set nigh")

    def test_escape_closes_without_running(self):
        self.chat.open()
        self.chat.handle_keydown(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE))
        self.assertFalse(self.chat.is_open)
        self.assertEqual(self.chat.history, [])

    def test_enter_submits_the_typed_text(self):
        self.chat.open()
        self.chat.input = "hello world"
        self.chat.handle_keydown(
            pygame.event.Event(pygame.KEYDOWN, key=pygame.K_RETURN))
        self.assertFalse(self.chat.is_open)
        self.assertEqual(self._last_message()[0], "<You> hello world")

    def test_help_lists_every_command(self):
        self.chat.run("/help")
        texts = [message[0] for message in self.chat.history]
        self.assertIn("/help - show this help", texts)
        self.assertTrue(any(t.startswith("/gamemode") for t in texts))
        self.assertTrue(any(t.startswith("/day set") for t in texts))

    def test_gamemode_creative_survival_spectator(self):
        self.chat.run("/gamemode creative")
        self.assertTrue(self.scene.player.is_creative)
        self.assertFalse(self.scene.player.is_spectator)
        self.assertEqual(self._last_message(), ("Gamemode set to Creative", (255, 255, 85)))

        self.chat.run("/gamemode s")
        self.assertFalse(self.scene.player.is_creative)
        self.assertEqual(self._last_message()[0], "Gamemode set to Survival")

        self.chat.run("/gamemode spectator")
        self.assertTrue(self.scene.player.is_spectator)
        self.assertFalse(self.scene.player.is_creative)
        self.assertEqual(self._last_message()[0], "Gamemode set to Spectator")

    def test_gamemode_rejects_unknown_and_missing_modes(self):
        self.chat.run("/gamemode")
        self.assertIn("Usage", self._last_message()[0])
        self.chat.run("/gamemode potato")
        self.assertIn("Unknown gamemode", self._last_message()[0])

    def test_day_set_named_and_integer_times(self):
        self.chat.run("/day set night")
        self.assertEqual(self.scene.dayNight.time_ticks, 13000)
        self.assertEqual(self._last_message()[0], "Set the time to 13000")

        self.chat.run("/day set midnight")
        self.assertEqual(self.scene.dayNight.time_ticks, 18000)

        self.chat.run("/day set 6000")
        self.assertEqual(self.scene.dayNight.time_ticks, 6000)

        self.chat.run("/day set 25000")
        self.assertIn("between 0 and 24000", self._last_message()[0])
        self.chat.run("/day set potato")
        self.assertIn("Unknown time", self._last_message()[0])
        self.chat.run("/day night")
        self.assertIn("Usage", self._last_message()[0])

    def test_unknown_command_reports_error(self):
        self.chat.run("/fly")
        self.assertIn("Unknown command", self._last_message()[0])

    def test_clear_empties_the_history(self):
        self.chat.run("hi")
        self.chat.run("/clear")
        self.assertEqual(self.chat.history, [])


if __name__ == "__main__":
    unittest.main()
