"""Locks in the two hard constraints of this build.

1. **No audio.**  ``pyglet.media`` is never imported anywhere in the project and
   every audio call is a silent no-op.
2. **No shadow contexts.**  Every file that imports pyglet sets
   ``pyglet.options['shadow_window'] = False`` *before* that import, so pyglet
   2.x cannot create a hidden window or a second GL context.

These are source-level invariants, so they are checked by scanning the tree.
"""

import os
import re
import sys
import unittest

from game.sound import audio
from game.sound.Sound import Sound

# Assembled at runtime so this very file cannot match its own scan.
MEDIA_MODULE = "pyglet" + ".media"
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_IMPORT_RE = re.compile(r"^\s*(?:import\s+pyglet(?:\.|$)|from\s+pyglet)")
_BARE_IMPORT_RE = re.compile(r"^\s*import\s+pyglet\s*$")
_MEDIA_RE = re.compile(
    r"import\s+{0}\b|from\s+{0}\b|{0}\.".format(re.escape(MEDIA_MODULE))
)
_GUARD_RE = re.compile(r"pyglet\.options\['shadow_window'\]\s*=\s*False")


def _python_files():
    for root, dirs, files in os.walk(PROJECT_ROOT):
        dirs[:] = [
            d for d in dirs
            if d not in ("__pycache__", "sounds", "textures", "gui", "assets",
                         "logs", "saves")
        ]
        for name in sorted(files):
            if name.endswith(".py"):
                yield os.path.join(root, name)


class NoAudioTests(unittest.TestCase):
    def test_audio_module_never_imports_pyglet_media(self):
        self.assertNotIn(MEDIA_MODULE, sys.modules)
        self.assertFalse(hasattr(audio, "pyglet"))

    def test_no_source_file_references_pyglet_media(self):
        offenders = []
        for path in _python_files():
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                for number, line in enumerate(handle, 1):
                    if _MEDIA_RE.search(line):
                        offenders.append(f"{path}:{number}")
        self.assertEqual(offenders, [])

    def test_load_sound_is_silent_and_non_blocking(self):
        effect = audio.load_sound("sounds/step/grass1.ogg")
        self.assertTrue(effect.loaded)
        self.assertIsNone(effect.source)
        self.assertIsNone(effect.load())
        self.assertIsNone(effect.play())
        self.assertIsNone(audio.load_sound("sounds/x.ogg", deferred=True).play())

    def test_preload_sounds_is_disabled(self):
        self.assertIsNone(audio.preload_sounds([audio.load_sound("a.ogg")]))
        self.assertIsNone(audio.preload_sounds([]))

    def test_music_player_is_a_noop(self):
        player = audio.MusicPlayer()
        self.assertIsNone(player.load("sounds/music/menu/menu1.ogg"))
        self.assertIsNone(player.queue("sounds/music/menu/menu1.ogg"))
        self.assertIsNone(player.play())
        self.assertIsNone(player.stop())
        player.set_volume(0.5)
        self.assertIsNone(player.close())
        self.assertIsNone(audio.shutdown_audio())

    def test_mixer_channel_is_inert(self):
        mixer = audio._MIXER
        self.assertIsNone(mixer.play(None))
        self.assertIsNone(mixer.stop_all())
        channel = audio.SoundChannel()
        self.assertFalse(channel.busy)
        self.assertIsNone(channel.start(None))
        self.assertIsNone(channel.set_volume(1.0))
        self.assertIsNone(channel.stop())

    def test_sound_play_helpers_return_none(self):
        sound = Sound()
        sound.SOUNDS["GUI"] = {"click_stereo": [audio.load_sound("click.ogg")]}
        self.assertIsNone(sound.playGuiSound("click"))
        sound.BLOCKS_SOUND["pickUp"] = audio.load_sound("pick.mp3")
        self.assertIsNone(sound.playSound("damage", 1.0))
        self.assertIsNone(sound.playMusic())
        self.assertIsNone(sound.shutdown())


class ShadowWindowGuardTests(unittest.TestCase):
    def test_every_pyglet_importer_sets_the_guard_first(self):
        offenders = []
        for path in _python_files():
            with open(path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
            guard_lines = [
                number for number, line in enumerate(lines, 1)
                if _GUARD_RE.search(line)
            ]
            bare_imports = [
                number for number, line in enumerate(lines, 1)
                if _BARE_IMPORT_RE.match(line)
            ]
            submodule_imports = [
                number for number, line in enumerate(lines, 1)
                if _IMPORT_RE.match(line) and not _BARE_IMPORT_RE.match(line)
            ]
            if not bare_imports and not submodule_imports:
                continue
            if not bare_imports:
                offenders.append(f"{path}: no bare 'import pyglet' at the top")
                continue
            if not guard_lines:
                offenders.append(f"{path}: no shadow_window guard")
                continue
            if min(bare_imports) > min(guard_lines):
                offenders.append(f"{path}: guard before 'import pyglet'")
                continue
            if submodule_imports and min(guard_lines) > min(submodule_imports):
                offenders.append(
                    f"{path}: guard after a pyglet submodule import"
                )
                continue
            if submodule_imports and min(bare_imports) > min(submodule_imports):
                offenders.append(
                    f"{path}: 'import pyglet' after a pyglet submodule import"
                )
        self.assertEqual(offenders, [])


if __name__ == "__main__":
    unittest.main()