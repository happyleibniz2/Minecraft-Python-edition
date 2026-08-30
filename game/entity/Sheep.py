"""Sheep entity, matching Minecraft's SheepModel and SheepFurModel exactly.

Vanilla body layer (``SheepModel.createBodyLayer``):
    head offset (0, 6, -8)  box (-3, -4, -6) size 6x6x8  uv (0, 0)
    body offset (0, 5, 2)   box (-4, -10, -7) size 8x16x6 uv (28, 8)
    legs offset (+-3, 12, +-7) box (-2, 0, -2) size 4x12x4 uv (0, 16)

Vanilla fur layer (``SheepFurModel.createFurLayer``), which is a slightly
inflated copy drawn over the body:
    head box (-3, -4, -4) size 6x6x6 uv (0, 0)
    body box (-4, -10, -7) size 8x16x6 grow 1.75 uv (28, 8)
    legs box (-2, 0, -2) size 4x6x4 grow 0.5 uv (0, 16)

The renderer flips vanilla's Y-down model space once at the root, so vanilla
pivot values are used unchanged.
"""

import os
import random

from OpenGL.GL import *

from game.entity.PassiveMob import PassiveMob

HALF_PI = 1.5707964

# Minecraft's sheep wool dye colours
WOOL_COLORS = {
    "white": (0.9019608, 0.9019608, 0.9019608),
    "light_gray": (0.6, 0.6, 0.6),
    "gray": (0.3, 0.3, 0.3),
    "black": (0.1, 0.1, 0.1),
    "brown": (0.4, 0.3, 0.2),
    "pink": (0.95, 0.7, 0.8),
}
# natural spawn weights: mostly white, pink is rare
NATURAL_WOOL = (
    ["white"] * 82 + ["light_gray"] * 5 + ["gray"] * 5 +
    ["black"] * 5 + ["brown"] * 3
)


class Sheep(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "sheep", "sheep.png")
    FUR_TEXTURE_PATH = os.path.join("textures", "mobs", "sheep", "sheep_fur.png")
    TEXTURE_SIZE = (64, 32)

    HEAD = (-3, -4, -6, 6, 6, 8, 0, 6, -8, 0, 0)
    BODY = (-4, -10, -7, 8, 16, 6, 0, 5, 2, 28, 8)
    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 12, 4, -3, 12, -5, 0, 16)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 12, 4, 3, 12, -5, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 12, 4, -3, 12, 7, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 12, 4, 3, 12, 7, 0, 16)

    # fur layer: same pivots, inflated boxes
    FUR_HEAD = (-3.6, -4.6, -4.6, 7.2, 7.2, 7.2, 0, 6, -8, 0, 0)
    FUR_BODY = (-5.75, -11.75, -8.75, 11.5, 19.5, 9.5, 0, 5, 2, 28, 8)
    FUR_LEG_FRONT_RIGHT = (-2.5, -0.5, -2.5, 5, 7, 5, -3, 12, -5, 0, 16)
    FUR_LEG_FRONT_LEFT = (-2.5, -0.5, -2.5, 5, 7, 5, 3, 12, -5, 0, 16)
    FUR_LEG_BACK_RIGHT = (-2.5, -0.5, -2.5, 5, 7, 5, -3, 12, 7, 0, 16)
    FUR_LEG_BACK_LEFT = (-2.5, -0.5, -2.5, 5, 7, 5, 3, 12, 7, 0, 16)

    def __init__(self, gl, wool_color=None):
        super().__init__(gl)
        self.hp = 8
        self.sheared = False
        self.wool_color = wool_color or random.choice(NATURAL_WOOL)
        self.fur_texture = None
        self.fur_tex_id = None
        self._load_fur_texture()

    def _load_fur_texture(self):
        try:
            self.fur_texture, _ = self._load_texture(self.FUR_TEXTURE_PATH)
            self.fur_tex_id = self.fur_texture.id
        except Exception as error:
            self.fur_tex_id = None
            print(f"Warning: could not load {self.FUR_TEXTURE_PATH} ({error})")

    @property
    def wool_rgb(self):
        return WOOL_COLORS.get(self.wool_color, WOOL_COLORS["white"])

    def _draw_parts(self):
        head_pitch = self.head_pitch / 57.295776
        head_yaw = self.head_yaw / 57.295776
        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.BODY, HALF_PI, 0, 0)
        self._draw_cube(self.LEG_FRONT_RIGHT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, swing, 0, 0)

        if self.sheared or self.fur_tex_id is None:
            return

        # wool layer, tinted by dye colour exactly like Minecraft
        glBindTexture(GL_TEXTURE_2D, self.fur_tex_id)
        glColor3f(*self.wool_rgb)
        self._draw_cube(self.FUR_HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.FUR_BODY, HALF_PI, 0, 0)
        self._draw_cube(self.FUR_LEG_FRONT_RIGHT, swing, 0, 0)
        self._draw_cube(self.FUR_LEG_FRONT_LEFT, opposite, 0, 0)
        self._draw_cube(self.FUR_LEG_BACK_RIGHT, opposite, 0, 0)
        self._draw_cube(self.FUR_LEG_BACK_LEFT, swing, 0, 0)
        glColor3f(1, 1, 1)
