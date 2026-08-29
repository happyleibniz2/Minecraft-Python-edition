"""Sheep entity: body model plus a separate tinted wool fur layer."""

import os
import random

from OpenGL.GL import *

from game.entity.PassiveMob import PassiveMob

# Minecraft's sheep wool dye colours
WOOL_COLORS = {
    "white": (0.9019608, 0.9019608, 0.9019608),
    "light_gray": (0.6, 0.6, 0.6),
    "gray": (0.3, 0.3, 0.3),
    "black": (0.1, 0.1, 0.1),
    "brown": (0.4, 0.3, 0.2),
    "pink": (0.95, 0.7, 0.8),
}
# natural spawn weights: mostly white, rarely pink
NATURAL_WOOL = (
    ["white"] * 82 + ["light_gray"] * 5 + ["gray"] * 5 +
    ["black"] * 5 + ["brown"] * 3
)


class Sheep(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "sheep", "sheep.png")
    FUR_TEXTURE_PATH = os.path.join("textures", "mobs", "sheep", "sheep_fur.png")
    TEXTURE_SIZE = (64, 32)

    HEAD = (-3, -6, -8, 6, 6, 8, 0, -18, -6, 0, 0)
    BODY = (-4, -10, -7, 8, 16, 6, 0, -9, 2, 28, 8)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 12, 4, -3, -12, -5, 0, 16)
    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 12, 4, 3, -12, -5, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 12, 4, -3, -12, 7, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 12, 4, 3, -12, 7, 0, 16)

    FUR_HEAD = (-3, -6.5, -8.5, 6, 6, 6, 0, -18, -6, 0, 0)
    FUR_BODY = (-4.5, -10.5, -7.5, 9, 17, 7, 0, -9, 2, 28, 8)
    FUR_LEG_FRONT_LEFT = (-2.5, 0, -2.5, 5, 8, 5, -3, -12, -5, 0, 16)
    FUR_LEG_FRONT_RIGHT = (-2.5, 0, -2.5, 5, 8, 5, 3, -12, -5, 0, 16)
    FUR_LEG_BACK_LEFT = (-2.5, 0, -2.5, 5, 8, 5, -3, -12, 7, 0, 16)
    FUR_LEG_BACK_RIGHT = (-2.5, 0, -2.5, 5, 8, 5, 3, -12, 7, 0, 16)

    def __init__(self, gl, wool_color=None):
        super().__init__(gl)
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
        head_pitch = self.head_pitch / 90.0
        head_yaw = self.head_yaw / 90.0
        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.BODY, 1.5707963, 0, 0)
        self._draw_cube(self.LEG_FRONT_LEFT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, swing, 0, 0)

        if self.sheared or self.fur_tex_id is None:
            return

        # wool layer, tinted by dye colour exactly like Minecraft
        glBindTexture(GL_TEXTURE_2D, self.fur_tex_id)
        glColor3f(*self.wool_rgb)
        self._draw_cube(self.FUR_HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.FUR_BODY, 1.5707963, 0, 0)
        self._draw_cube(self.FUR_LEG_FRONT_LEFT, swing, 0, 0)
        self._draw_cube(self.FUR_LEG_FRONT_RIGHT, opposite, 0, 0)
        self._draw_cube(self.FUR_LEG_BACK_LEFT, opposite, 0, 0)
        self._draw_cube(self.FUR_LEG_BACK_RIGHT, swing, 0, 0)
        glColor3f(1, 1, 1)
