"""Chicken entity, matching Minecraft's classic 64x32 ChickenModel.

Box coordinates are relative to each part's pivot, mirroring vanilla
``ModelPart`` layout (the same convention ``Cow`` documents). Vanilla values
(``ChickenModel.createBodyLayer``):

    head        offset (0, 15, -4)   box (-2, -6, -2) size 4x6x3   uv (0, 0)
    beak                           box (-2, -4, -4) size 4x2x2   uv (14, 0)
    wattle                         box (-1, -2, -3) size 2x2x2   uv (14, 4)
    body        offset (0, 16, 0)    box (-3,  0, -3) size 6x8x6   uv (0, 9)  (X-rotated)
    right wing  offset (-4, 13, 0)   box (-1,  0, -3) size 4x6x1   uv (24, 13)
    left wing   offset ( 4, 13, 0)   box (-3,  0, -3) size 4x6x1   uv (24, 13)
    legs        offset (+-1, 19, -1) box (-1.5, 0, -1.5) size 3x5x3 uv (26, 0)
"""

import os

from game.entity.PassiveMob import PassiveMob

HALF_PI = 1.5707964


class Chicken(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "chicken", "chicken.png")
    TEXTURE_SIZE = (64, 32)
    MODEL_OFFSET = 0.0
    WANDER_SPEED = 0.6

    # (x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)
    HEAD = (-2, -6, -2, 4, 6, 3, 0, 15, -4, 0, 0)
    BEAK = (-2, -4, -4, 4, 2, 2, 0, 15, -4, 14, 0)
    WATTLE = (-1, -2, -3, 2, 2, 2, 0, 15, -4, 14, 4)
    BODY = (-3, 0, -3, 6, 8, 6, 0, 16, 0, 0, 9)
    WING_RIGHT = (-1, 0, -3, 4, 6, 1, -4, 13, 0, 24, 13)
    WING_LEFT = (-3, 0, -3, 4, 6, 1, 4, 13, 0, 24, 13)
    LEG_RIGHT = (-1.5, 0, -1.5, 3, 5, 3, -1, 19, -1, 26, 0)
    LEG_LEFT = (-1.5, 0, -1.5, 3, 5, 3, 1, 19, -1, 26, 0)

    def _draw_parts(self):
        head_pitch = self.head_pitch / 57.295776
        head_yaw = self.head_yaw / 57.295776

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.BEAK, head_pitch, head_yaw, 0)
        self._draw_cube(self.WATTLE, head_pitch, head_yaw, 0)

        self._draw_cube(self.BODY, HALF_PI, 0, 0)

        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)
        # wings flap slowly while walking
        self._draw_cube(self.WING_RIGHT, 0, 0, opposite * 0.35)
        self._draw_cube(self.WING_LEFT, 0, 0, swing * 0.35)
        self._draw_cube(self.LEG_RIGHT, swing, 0, 0)
        self._draw_cube(self.LEG_LEFT, opposite, 0, 0)
