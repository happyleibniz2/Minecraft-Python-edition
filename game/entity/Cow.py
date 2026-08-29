"""Cow entity, using Minecraft's CowModel box layout."""

import os

from game.entity.PassiveMob import PassiveMob


class Cow(PassiveMob):
    TEXTURE_PATH = os.path.join("textures", "mobs", "cow", "cow.png")
    TEXTURE_SIZE = (64, 32)
    MODEL_OFFSET = 0.0

    # (x, y, z, w, h, d, offsetX, offsetY, offsetZ, texU, texV)
    HEAD = (-4, -4, -6, 8, 8, 6, 0, -21, -8, 0, 0)
    HORN_LEFT = (-5, -5, -5, 1, 3, 1, 0, -21, -8, 22, 0)
    HORN_RIGHT = (4, -5, -5, 1, 3, 1, 0, -21, -8, 22, 0)
    BODY = (-6, -10, -7, 12, 18, 10, 0, -8, 2, 18, 4)
    UDDER = (-2, 2, -8, 4, 6, 1, 0, -8, 2, 52, 0)
    LEG_FRONT_LEFT = (-2, 0, -2, 4, 12, 4, -3, -12, -5, 0, 16)
    LEG_FRONT_RIGHT = (-2, 0, -2, 4, 12, 4, 3, -12, -5, 0, 16)
    LEG_BACK_LEFT = (-2, 0, -2, 4, 12, 4, -3, -12, 7, 0, 16)
    LEG_BACK_RIGHT = (-2, 0, -2, 4, 12, 4, 3, -12, 7, 0, 16)

    def _draw_parts(self):
        head_pitch = self.head_pitch / 90.0
        head_yaw = self.head_yaw / 90.0

        self._draw_cube(self.HEAD, head_pitch, head_yaw, 0)
        self._draw_cube(self.HORN_LEFT, head_pitch, head_yaw, 0)
        self._draw_cube(self.HORN_RIGHT, head_pitch, head_yaw, 0)

        # Minecraft rotates the cow body upright by 90 degrees
        self._draw_cube(self.BODY, 1.5707963, 0, 0)
        self._draw_cube(self.UDDER, 1.5707963, 0, 0)

        swing = self._limb_angle()
        opposite = self._limb_angle(3.1415927)
        self._draw_cube(self.LEG_FRONT_LEFT, swing, 0, 0)
        self._draw_cube(self.LEG_FRONT_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_BACK_RIGHT, swing, 0, 0)
