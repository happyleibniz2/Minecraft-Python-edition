"""Distance attenuation for positional sounds (the step-sound bug).

pygame 2.6.1's two-argument ``set_volume(left, right)`` resets the channel
master volume to 1.0, which made every positional sound play at full volume
no matter the distance. SoundPhysics now uses the reliable one-argument
form; these tests lock the attenuation curve on a real mixer (silently -
the probe sound is a zero buffer).
"""

import math
import unittest
from types import SimpleNamespace

try:
    import pygame
except ImportError:  # pragma: no cover
    pygame = None

if pygame is not None:
    try:
        pygame.mixer.init(frequency=22050, size=-16, channels=2, buffer=512)
    except pygame.error:
        pygame = None  # no audio device; whole module skips

if pygame is not None:
    from game.sound.SoundPhysics import SoundPhysics


@unittest.skipIf(pygame is None, "no audio mixer available")
class SoundPhysicsAttenuationTests(unittest.TestCase):
    SILENCE = b"\x00\x00" * 512  # 512 silent stereo samples

    @classmethod
    def setUpClass(cls):
        cls.silence = pygame.mixer.Sound(buffer=cls.SILENCE)

    def make_physics(self, player_position=(0.0, 70.0, 0.0)):
        gl = SimpleNamespace(
            player=SimpleNamespace(position=list(player_position),
                                   rotation=[0.0, 0.0]),
            cubes=None,  # no world -> no occlusion
        )
        return SoundPhysics(gl)

    def play(self):
        channel = self.silence.play()
        self.assertIsNotNone(channel, "mixer returned no channel")
        return channel

    def test_nearby_source_is_full_volume(self):
        physics = self.make_physics()
        channel = self.play()
        physics.apply(channel, (0.0, 70.0, 0.0), 1.0)
        self.assertAlmostEqual(channel.get_volume(), 1.0, places=2)

    def test_mid_distance_quarter_volume(self):
        physics = self.make_physics()
        channel = self.play()
        physics.apply(channel, (16.0, 70.0, 0.0), 1.0)
        # (1 - 16/32)^2 = 0.25
        self.assertAlmostEqual(channel.get_volume(), 0.25, places=2)

    def test_beyond_max_distance_is_silent(self):
        physics = self.make_physics()
        for position in ((40.0, 70.0, 0.0), (200.0, 70.0, -300.0)):
            channel = self.play()
            physics.apply(channel, position, 1.0)
            self.assertEqual(channel.get_volume(), 0.0,
                             f"{position} should be inaudible")

    def test_master_volume_scales_the_gain(self):
        physics = self.make_physics()
        channel = self.play()
        physics.apply(channel, (0.0, 70.0, 0.0), 0.4)
        self.assertAlmostEqual(channel.get_volume(), 0.4, places=2)

    def test_none_channel_is_ignored(self):
        physics = self.make_physics()
        self.assertIsNone(physics.apply(None, (0, 0, 0), 1.0))

    def test_source_without_position_uses_plain_volume(self):
        physics = self.make_physics()
        channel = self.play()
        physics.apply(channel, None, 0.7)
        self.assertAlmostEqual(channel.get_volume(), 0.7, places=2)


if __name__ == "__main__":
    unittest.main()
