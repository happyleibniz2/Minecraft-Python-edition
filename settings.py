import random
# import timeit
import pygame
from pyglet import font
import json

lang_type_file = open("gui/lang.mclanguage", "r")
lang_type = str(lang_type_file.read())
current_language = lang_type
print(current_language)


class Translations(dict):
    """Dict subclass that returns the key when a translation is missing.

    This prevents KeyError crashes when code requests a string that hasn't
    been added to the language file. It also logs the missing key so you can
    add it later.
    """
    def __getitem__(self, key):
        if key in self:
            return super().__getitem__(key)
        else:
            # log once per missing key to avoid spamming
            print(f"[translation] missing key: '{key}'")
            return key


def load_language():
    path = f"assets/Minecraft/languages/{current_language}.json"
    try:
        with open(path, "r", encoding="utf-8") as file:
            data = json.load(file)
    except Exception as e:
        print(f"Failed to load language file {path}: {e}")
        data = {}
    # wrap in Translations so access is safe
    return Translations(data)


translations = load_language()

# Initialize pygame first
pygame.init()

# Use pygame fonts instead of pyglet fonts to avoid compatibility issues
if current_language == "zh":
    try:
        mainFont = pygame.font.Font('gui/MinecraftAE.ttf', 15)
    except:
        mainFont = pygame.font.SysFont('arial', 15)
elif current_language == "en":
    try:
        mainFont = pygame.font.Font('gui/main.ttf', 20)
    except:
        mainFont = pygame.font.SysFont('arial', 20)

monitor = pygame.display.Info()
WIDTH = 927  # monitor.current_w
HEIGHT = 566  # monitor.current_h
MAX_FPS = 120
PAUSE = True
IN_MENU = True
MC_VERSION = "1.0"
clock = pygame.time.Clock()
DEBUG = True
FOV = 100
RENDER_DISTANCE = 999

CHUNKS_RENDER_DISTANCE = 900
CHUNK_SIZE = (4, 60, 4)
