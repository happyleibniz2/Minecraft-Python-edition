"""Creeper entity, matching Minecraft's classic 64x32 CreeperModel.

Box coordinates are relative to each part's pivot, mirroring vanilla
``ModelPart`` layout (the same convention ``Cow`` documents). Vanilla values
(``CreeperModel.createBodyLayer``):

    head  offset (0, 6, 0)        box (-4, -8, -4) size 8x8x8   uv (0, 0)
    body  offset (0, 6, 0)        box (-4,  0, -2) size 8x12x4  uv (16, 16)
    legs  offset (+-2, 18, -+4)   box (-2,  0, -2) size 4x6x4   uv (0, 16)
"""

import os

from game.entity.PassiveMob import PassiveMob


class Creeper(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "creeper", "creeper.png")
    TEXTURE_SIZE = (64, 32)
    MODEL_OFFSET = 0.0

    # (x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)
    HEAD = (-4, -8, -4, 8, 8, 8, 0, 6, 0, 0, 0)
    BODY = (-4, 0, -2, 8, 12, 4, 0, 6, 0, 16, 16)

    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 6, 4, -2, 18, -4, 0, 16)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 6, 4, 2, 18, -4, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 6, 4, -2, 18, 4, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 6, 4, 2, 18, 4, 0, 16)

    def _draw_parts(self):
        head_pitch = self.head_pitch / 57.295776
        head_yaw = self.head_yaw / 57.295776

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.BODY, 0, 0, 0)

        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)
        self._draw_cube(self.LEG_FRONT_RIGHT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, swing, 0, 0)
