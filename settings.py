import random
# import timeit
import pygame
from pyglet import font
import json
import os

lang_type_file = open("gui/lang.mclanguage", "r")
lang_type = str(lang_type_file.read())
current_language = lang_type
print(current_language)


def load_language():
    with open(f"assets/Minecraft/languages/{current_language}.json", "r", encoding="utf-8") as file:
        return json.load(file)


translations = load_language()
if current_language == "zh":
    font.add_file('gui/MinecraftAE.ttf')
    mainFont = font.load('gui/MinecraftAE.ttf', 15)
elif current_language == "en":
    font.add_file('gui/main.ttf')
    mainFont = font.load('gui/main.ttf', 20)

pygame.init()

OPTIONS_FILE = os.path.join("gui", "options.json")


def load_options():
    try:
        with open(OPTIONS_FILE, "r", encoding="utf-8") as options_file:
            return json.load(options_file)
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_options():
    with open(OPTIONS_FILE, "w", encoding="utf-8") as options_file:
        json.dump({
            "shaders": SHADERS,
            "player_shadows": PLAYER_SHADOWS,
            "leaves_sway": LEAVES_SWAY,
        }, options_file, indent=2)


def set_shaders(enabled):
    global SHADERS
    SHADERS = bool(enabled)
    save_options()


def set_player_shadows(enabled):
    global PLAYER_SHADOWS
    PLAYER_SHADOWS = bool(enabled)
    save_options()


def set_leaves_sway(enabled):
    global LEAVES_SWAY
    LEAVES_SWAY = bool(enabled)
    save_options()


_options = load_options()
SHADERS = bool(_options.get("shaders", True))
PLAYER_SHADOWS = bool(_options.get("player_shadows", True))
LEAVES_SWAY = bool(_options.get("leaves_sway", True))

monitor = pygame.display.Info()
#WIDTH = monitor.current_w
#HEIGHT = monitor.current_h
WIDTH = 854
HEIGHT = 480
MAX_FPS = 2000
PAUSE = True
IN_MENU = True
MC_VERSION = "Pre Classic 0.67"
clock = pygame.time.Clock()
DEBUG = True
FOV = 100
MOUSE_SENSITIVITY = 0.5
RENDER_DISTANCE = 192
DISTANCE_CULLING = True
CHUNKS_RENDER_DISTANCE = 96
CHUNK_SIZE = (4, 60, 4)
