"""Cow entity, matching Minecraft's CowModel exactly.

Box coordinates are relative to each part's pivot, mirroring vanilla
``ModelPart`` layout. Vanilla values (``CowModel.createBodyLayer``):

    head  offset (0, 4, -8)   box (-4, -4, -6) size 8x8x6   uv (0, 0)
    horns                     box (-5, -5, -4) size 1x3x1   uv (22, 0)
                              box ( 4, -5, -4) size 1x3x1   uv (22, 0)
    body  offset (0, 5, 2)    box (-6, -10, -7) size 12x18x10 uv (18, 4)
          udder               box (-2, 2, -8) size 4x6x1    uv (52, 0)
    legs  offset (+-4, 12, +-6) box (-2, 0, -2) size 4x12x4 uv (0, 16)

The renderer flips the vanilla Y-down model space once at the root, so vanilla pivot values are used unchanged.
"""

import os

from game.entity.PassiveMob import PassiveMob

HALF_PI = 1.5707964


class Cow(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "cow", "cow.png")
    TEXTURE_SIZE = (64, 32)
    MODEL_OFFSET = 0.0

    # (x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)
    HEAD = (-4, -4, -6, 8, 8, 6, 0, 4, -8, 0, 0)
    HORN_LEFT = (-5, -5, -4, 1, 3, 1, 0, 4, -8, 22, 0)
    HORN_RIGHT = (4, -5, -4, 1, 3, 1, 0, 4, -8, 22, 0)

    # body is rotated upright by 90 degrees, like vanilla
    BODY = (-6, -10, -7, 12, 18, 10, 0, 5, 2, 18, 4)
    UDDER = (-2, 2, -8, 4, 6, 1, 0, 5, 2, 52, 0)

    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 12, 4, -4, 12, -6, 0, 16)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 12, 4, 4, 12, -6, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 12, 4, -4, 12, 7, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 12, 4, 4, 12, 7, 0, 16)

    def _draw_parts(self):
        head_pitch = self.head_pitch / 57.295776
        head_yaw = self.head_yaw / 57.295776

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.HORN_LEFT, head_pitch, head_yaw, 0)
        self._draw_cube(self.HORN_RIGHT, head_pitch, head_yaw, 0)

        self._draw_cube(self.BODY, HALF_PI, 0, 0)
        self._draw_cube(self.UDDER, HALF_PI, 0, 0)

        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)
        self._draw_cube(self.LEG_FRONT_RIGHT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, swing, 0, 0)
