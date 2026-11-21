from random import randint

import settings
from game.sound.audio import MusicPlayer


class Sound:
    def __init__(self):
        print("Init Sound class...")
        self.BLOCKS_SOUND = {}
        self.SOUNDS = {}
        self.MUSIC = []
        self.MENU_MUSIC = []
        self.music_already_playing = False
        # Audio is disabled in this build: MusicPlayer is a no-op stub that
        # creates no pyglet.media player and never touches a decoder.
        self.musicPlayer = MusicPlayer()
        self.volume = settings.SOUND_VOLUME

    def initMusic(self, t):
        """Disabled.  No track is loaded or queued (no audio in this build)."""
        return

    def shutdown(self):
        self.musicPlayer.close()

    @staticmethod
    def _play(sound, volume):
        """Play a sound, tolerating the mixer returning no free channel."""
        if sound is None:
            return None
        return sound.play()

    def playSound(self, name, volume):
        return self._play(self.SOUNDS.get(name), volume)

    def playGuiSound(self, st):
        if st == "click":
            sounds = self.SOUNDS.get("GUI", {}).get("click_stereo")
            if sounds:
                return self._play(sounds[0], self.volume)
        return None

    def playMusic(self):
        """Disabled.  Menu/game music is never played in this build."""
        return None