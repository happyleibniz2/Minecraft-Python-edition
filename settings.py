import random
import pygame
from pyglet import font
import json

lang_type_file = open("gui/lang.mclanguage", "r")
lang_type = str(lang_type_file.read())
current_language = lang_type
print(current_language)


def load_language():
    with open(f"assets/Minecraft/languages/{current_language}.json", "r", encoding="utf-8") as file:
        return json.load(file)


translations = load_language()

# ---- Font loading for pyglet 2.x ----
FONT_NAME = "Arial"  # fallback

if current_language == "zh":
    font_file = "gui/MinecraftAE.ttf"
    fallback = "Microsoft YaHei"
else:
    font_file = "gui/main.ttf"
    fallback = "Arial"

try:
    # Register the font file with pyglet
    font.add_file(font_file)
    # The font family name is usually the file name without extension,
    # but we can try to load it directly using the 'file' parameter.
    # In pyglet 2.x, you can pass 'file' to load from a path.
    # If that doesn't work, we fall back to a system font.
    mainFont = font.load(None, 20, file=font_file)   # works in pyglet 2.x
    FONT_NAME = mainFont.name                        # store the actual family name
except Exception:
    # Fallback to a system font
    mainFont = font.load(fallback, 20)
    FONT_NAME = fallback

# For Chinese, we also set the font for the labels.
# If you want to use the same font for both, you can keep as above.

pygame.init()

monitor = pygame.display.Info()
WIDTH = 927
HEIGHT = 566
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