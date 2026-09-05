from random import randint

import pygame
import settings


class Sound:
    def __init__(self):
        print("Init Sound class...")
        self.BLOCKS_SOUND = {}
        self.SOUNDS = {}
        self.MUSIC = []
        self.MENU_MUSIC = []
        self.music_already_playing = False

        self.musicPlayer = pygame.mixer.music

        self.volume = settings.SOUND_VOLUME

    def initMusic(self, t):
        self.musicPlayer.stop()
        del self.musicPlayer
        self.musicPlayer = pygame.mixer.music

        if t:
            musicNum = randint(0, len(self.MUSIC) - 1)
            self.musicPlayer.load(self.MUSIC[musicNum])
            for i in range(len(self.MUSIC)):
                if i == musicNum:
                    continue
                self.musicPlayer.queue(self.MUSIC[i])
        else:
            musicNum = randint(0, len(self.MENU_MUSIC) - 1)
            self.musicPlayer.load(self.MENU_MUSIC[musicNum])
            for i in range(len(self.MENU_MUSIC)):
                if i == musicNum:
                    continue
                self.musicPlayer.queue(self.MENU_MUSIC[i])

    @staticmethod
    def _play(sound, volume):
        """Play a sound, tolerating pygame returning no free channel."""
        if sound is None:
            return None
        channel = sound.play()
        if channel is not None:
            channel.set_volume(volume)
        return channel

    def playSound(self, name, volume):
        return self._play(self.SOUNDS.get(name), volume)

    def playGuiSound(self, st):
        if st == "click":
            sounds = self.SOUNDS.get("GUI", {}).get("click_stereo")
            if sounds:
                return self._play(sounds[0], self.volume)
        return None

    def playMusic(self):
        if self.music_already_playing:
            return
        if randint(0, 5000) == 746:
            self.music_already_playing = True
            self.musicPlayer.play()
            self.musicPlayer.set_volume(self.volume)
