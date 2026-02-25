from random import randint
import os

import pygame


class Sound:
    def __init__(self):
        # initialise pygame mixer early so sounds can be loaded at startup
        try:
            pygame.mixer.init()
        except Exception:
            pass
        print("Init Sound class...")
        self.BLOCKS_SOUND = {}
        self.SOUNDS = {}
        self.MUSIC = []
        self.MENU_MUSIC = []
        self.music_already_playing = False

        self.musicPlayer = pygame.mixer.music

        self.volume = 1

        # load all files from the `sounds` folder into the dictionaries
        self.load_sounds()

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

    def playSound(self, name, volume):
        try:
            channel = self.SOUNDS[name].play()
            channel.set_volume(volume)
        except Exception:
            pass

    def playGuiSound(self, st):
        # older code referenced uppercase "GUI" key; loader uses lowercase,
        # so try both keys and warn if missing.
        key = "GUI" if "GUI" in self.SOUNDS else "gui"
        if key not in self.SOUNDS:
            # nothing to play
            return
        if st == "click":
            try:
                channel = self.SOUNDS[key]["click_stereo"][0].play()
                channel.set_volume(self.volume)
            except Exception:
                pass

    def playMusic(self):
        if self.music_already_playing:
            return
        if randint(0, 5000) == 746:
            self.music_already_playing = True
            self.musicPlayer.play()
            self.musicPlayer.set_volume(self.volume)

    def load_sounds(self):
        """Scan the `sounds` directory and populate both SOUNDS and
        BLOCKS_SOUND dictionaries.

        - Top-level files (e.g. pick.mp3) are stored in BLOCKS_SOUND as
          simple Sounds (pickUp in earlier code).
        - Subdirectories become categories in SOUNDS.  For some categories
          (dig/step) we build a nested dict keyed by material name; for
          others (damage, gui, explode, etc.) we keep a flat list of
          sounds or a dict if there are multiple named prefixes.
        """
        base = "sounds"
        if not os.path.isdir(base):
            return
        for root, dirs, files in os.walk(base):
            for fname in files:
                if not fname.lower().endswith((".ogg", ".wav", ".mp3")):
                    continue
                path = os.path.join(root, fname)
                rel = os.path.relpath(path, base)
                parts = rel.split(os.sep)
                if len(parts) == 1:
                    # file at root level
                    key = os.path.splitext(parts[0])[0]
                    if key == "pick":
                        # legacy naming
                        key = "pickUp"
                    try:
                        snd = pygame.mixer.Sound(path)
                    except Exception:
                        continue
                    self.BLOCKS_SOUND[key] = snd
                    continue
                category = parts[0].lower()
                name = os.path.splitext(parts[-1])[0]
                # strip digits at end (click1 -> click)
                base_name = ''.join(ch for ch in name if not ch.isdigit())
                base_name = base_name.rstrip('_')
                # ensure category exists
                # always treat each top‑level directory as a dictionary of
                # prefix‑grouped lists.  This handles "damage", "gui",
                # "dig", "step", etc.  The only time a plain list is used is
                # when the category itself is the prefix (e.g. explode1.ogg);
                # in that case the dict will have a single key equal to the
                # category name.
                if category not in self.SOUNDS:
                    self.SOUNDS[category] = {}

                bucket = self.SOUNDS[category]
                if base_name not in bucket:
                    bucket[base_name] = []
                try:
                    bucket[base_name].append(pygame.mixer.Sound(path))
                except Exception:
                    pass
        # make sure GUI is available under uppercase key as well
        if "gui" in self.SOUNDS and "GUI" not in self.SOUNDS:
            self.SOUNDS["GUI"] = self.SOUNDS["gui"]
        # copy relevant entries for backwards compatibility.  BLOCKS_SOUND
        # mirrors the structure expected by BlockSound; explode is special-
        # cased to be a flat list rather than a dict since the original code
        # treated it that way.
        for cat in ("step", "dig"):
            if cat in self.SOUNDS:
                self.BLOCKS_SOUND[cat] = self.SOUNDS[cat]
        if "explode" in self.SOUNDS:
            # flatten all groups under explode into a single list
            sounds = []
            for lst in self.SOUNDS["explode"].values():
                sounds.extend(lst)
            self.BLOCKS_SOUND["explode"] = sounds
        # pickUp may have been stored at top level
        if "pickUp" in self.BLOCKS_SOUND:
            pass
        elif "pickUp" in self.SOUNDS:
            # some users might have placed a pickup file in a folder
            # drop the first element if it's a dict
            val = self.SOUNDS["pickUp"]
            if isinstance(val, dict):
                # flatten
                sounds = []
                for lst in val.values():
                    sounds.extend(lst)
                self.BLOCKS_SOUND["pickUp"] = sounds[0] if sounds else None
            else:
                self.BLOCKS_SOUND["pickUp"] = val
