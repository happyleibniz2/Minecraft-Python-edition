"""Pig entity, matching Minecraft's classic 64x32 PigModel.

Box coordinates are relative to each part's pivot, mirroring vanilla
``ModelPart`` layout (the same convention ``Cow`` documents). Vanilla values
(``ModelQuadruped`` quadruped frame + pig's snout):

    head   offset (0, 12, 6)    box (-4, -4, -8) size 8x8x8   uv (0, 0)
    snout                         box (-2,  3, -9) size 4x3x1 uv (16, 16)
    body   offset (0, 11, 2)    box (-5, -10, -7) size 10x16x8 uv (28, 8) (X-rotated)
    legs   offset (+-3, 18, +-6)  box (-2, 0, -2) size 4x6x4   uv (0, 16)
"""

import os

from game.entity.PassiveMob import PassiveMob

HALF_PI = 1.5707964


class Pig(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "pig", "pig.png")
    TEXTURE_SIZE = (64, 32)
    MODEL_OFFSET = 0.0

    # (x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)
    HEAD = (-4, -4, -8, 8, 8, 8, 0, 12, 6, 0, 0)
    SNOUT = (-2, 3, -9, 4, 3, 1, 0, 12, 6, 16, 16)
    BODY = (-5, -10, -7, 10, 16, 8, 0, 11, 2, 28, 8)

    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 6, 4, -3, 18, -6, 0, 16)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 6, 4, 3, 18, -6, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 6, 4, -3, 18, 7, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 6, 4, 3, 18, 7, 0, 16)

    def _draw_parts(self):
        head_pitch = self.head_pitch / 57.295776
        head_yaw = self.head_yaw / 57.295776

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.SNOUT, head_pitch, head_yaw, 0)

        self._draw_cube(self.BODY, HALF_PI, 0, 0)

        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)
        self._draw_cube(self.LEG_FRONT_RIGHT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, swing, 0, 0)
