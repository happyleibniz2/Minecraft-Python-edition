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
            "shadow_quality": SHADOW_QUALITY,
            "blackhole_quality": BLACKHOLE_QUALITY,
            "cloud_quality": CLOUD_QUALITY,
            "vsync": VSYNC,
            "anti_aliasing": ANTI_ALIASING,
            "dynamic_lighting": DYNAMIC_LIGHTING,
            "difficulty": DIFFICULTY,
            "sound_volume": SOUND_VOLUME,
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


def set_shadow_quality(quality):
    global SHADOW_QUALITY
    quality = str(quality).upper()
    SHADOW_QUALITY = quality if quality in ("LOW", "MEDIUM", "HIGH") else "MEDIUM"
    save_options()


def _normalize_blackhole_quality(quality):
    quality = str(quality).upper()
    return quality if quality in ("OFF", "LOW", "HIGH") else "HIGH"


def set_blackhole_quality(quality):
    global BLACKHOLE_QUALITY
    BLACKHOLE_QUALITY = _normalize_blackhole_quality(quality)
    save_options()


CLOUD_QUALITY_LEVELS = ("POTATO", "LOW", "MEDIUM", "HIGH", "GPU")


def _normalize_cloud_quality(quality):
    quality = str(quality).upper()
    return quality if quality in CLOUD_QUALITY_LEVELS else "HIGH"


def set_cloud_quality(quality):
    global CLOUD_QUALITY
    CLOUD_QUALITY = _normalize_cloud_quality(quality)
    save_options()


def set_vsync(enabled):
    global VSYNC
    VSYNC = bool(enabled)
    save_options()


def set_anti_aliasing(enabled):
    global ANTI_ALIASING
    ANTI_ALIASING = bool(enabled)
    save_options()


def set_dynamic_lighting(enabled):
    global DYNAMIC_LIGHTING
    DYNAMIC_LIGHTING = bool(enabled)
    save_options()


def set_difficulty(difficulty):
    global DIFFICULTY
    difficulty = str(difficulty).upper()
    DIFFICULTY = difficulty if difficulty in ("PEACEFUL", "EASY", "NORMAL", "HARD") else "NORMAL"
    save_options()


def set_sound_volume(volume):
    global SOUND_VOLUME
    try:
        volume = float(volume)
    except (TypeError, ValueError):
        volume = 1.0
    SOUND_VOLUME = max(0.0, min(1.0, volume))
    save_options()


_options = load_options()
SHADERS = bool(_options.get("shaders", True))
PLAYER_SHADOWS = bool(_options.get("player_shadows", True))
LEAVES_SWAY = bool(_options.get("leaves_sway", True))
SHADOW_QUALITY = str(_options.get("shadow_quality", "MEDIUM")).upper()
if SHADOW_QUALITY not in ("LOW", "MEDIUM", "HIGH"):
    SHADOW_QUALITY = "MEDIUM"
BLACKHOLE_QUALITY = _normalize_blackhole_quality(_options.get("blackhole_quality", "HIGH"))
# MEDIUM keeps the full Unreal-style lighting model while the raymarch runs
# at half resolution - the balanced default for high, stable frame rates.
CLOUD_QUALITY = _normalize_cloud_quality(_options.get("cloud_quality", "MEDIUM"))
# vsync caps the frame rate at the monitor refresh rate; it must be off to
# reach high-FPS targets. Applied when the window is created.
VSYNC = bool(_options.get("vsync", False))
ANTI_ALIASING = bool(_options.get("anti_aliasing", True))
DYNAMIC_LIGHTING = bool(_options.get("dynamic_lighting", True))
DIFFICULTY = str(_options.get("difficulty", "NORMAL")).upper()
if DIFFICULTY not in ("PEACEFUL", "EASY", "NORMAL", "HARD"):
    DIFFICULTY = "NORMAL"
try:
    SOUND_VOLUME = max(0.0, min(1.0, float(_options.get("sound_volume", 1.0))))
except (TypeError, ValueError):
    SOUND_VOLUME = 1.0

monitor = pygame.display.Info()
#WIDTH = monitor.current_w
#HEIGHT = monitor.current_h
WIDTH = 854
HEIGHT = 480
MAX_FPS = 2000
PAUSE = True
IN_MENU = True
MC_VERSION = "1"
clock = pygame.time.Clock()
DEBUG = True
FOV = 100
MOUSE_SENSITIVITY = 0.5
RENDER_DISTANCE = 192
DISTANCE_CULLING = True
CHUNKS_RENDER_DISTANCE = 96
WORLD_MIN_Y = -64
WORLD_MAX_Y = 319
SEA_LEVEL = 63
PLAYER_EYE_HEIGHT = 1.62
CHUNK_SIZE = (4, WORLD_MAX_Y - WORLD_MIN_Y + 1, 4)
