"""Third-person player avatar rendered from the classic wide Steve skin.

The model follows the vanilla ``HumanoidModel`` layout on the 64x64 skin
(same y-down model space as ``PassiveMob``: the root is flipped with
``glScalef(1, -1, 1)`` and the feet sit at model y=24):

    head       offset (0, 0, 0)      box (-4, -8, -4)     size 8x8x8    uv (0, 0)
    hat layer                        box (-4.5,-8.5,-4.5) size 9x9x9    uv (32, 0)
    body       offset (0, 0, 0)      box (-4,  0, -2)     size 8x12x4   uv (16, 16)
    right arm  offset (-5, 2, 0)     box (-3, -2, -2)     size 4x12x4    uv (40, 16)
    left arm   offset ( 5, 2, 0)     box (-1, -2, -2)     size 4x12x4    uv (32, 48)
    right leg  offset (-1.9, 12, 0)  box (-2, 0, -2)      size 4x12x4    uv (0, 16)
    left leg   offset ( 1.9, 12, 0)  box (-2, 0, -2)      size 4x12x4    uv (16, 48)

The avatar is created without touching GL; the skin loads on the first
third-person draw. ``hand_swing`` raises the right arm like vanilla's attack
animation; the head tracks the player pitch/yaw.
"""

import math
import os

import pyglet
from OpenGL.GL import *

SKIN_PATH = os.path.join("textures", "mobs", "player", "wide", "steve.png")


class PlayerAvatar:
    MODEL_SCALE = 0.0625
    FEET_MODEL_DEPTH = 24 * MODEL_SCALE  # model space: feet at y=24
    SKIN_PATH = SKIN_PATH

    # (x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)
    HEAD = (-4, -8, -4, 8, 8, 8, 0, 0, 0, 0, 0)
    HAT = (-4.5, -8.5, -4.5, 9, 9, 9, 0, 0, 0, 32, 0)
    BODY = (-4, 0, -2, 8, 12, 4, 0, 0, 0, 16, 16)
    ARM_RIGHT = (-3, -2, -2, 4, 12, 4, -5, 2, 0, 40, 16)
    ARM_LEFT = (-1, -2, -2, 4, 12, 4, 5, 2, 0, 32, 48)
    LEG_RIGHT = (-2, 0, -2, 4, 12, 4, -1.9, 12, 0, 0, 16)
    LEG_LEFT = (-2, 0, -2, 4, 12, 4, 1.9, 12, 0, 16, 48)

    def __init__(self, gl):
        self.gl = gl
        self.tex_id = 0
        self.tex_w, self.tex_h = 64, 64
        self._texture_loaded = False
        self.limb_swing = 0.0
        self.limb_amount = 0.0
        self._last_position = None

    # ------------------------------------------------------------- texture
    def _load_texture(self):
        self._texture_loaded = True
        if not os.path.isfile(SKIN_PATH):
            print(f"Warning: player skin not found: {SKIN_PATH}")
            return
        image = pyglet.image.load(SKIN_PATH)
        texture = image.get_texture()
        self.tex_id = texture.id
        self.tex_w, self.tex_h = image.width, image.height
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    # ------------------------------------------------------------ animation
    def update_limb_state(self, dt, travelled):
        """Advance the walk cycle; mirrored from PassiveMob._update_animation."""
        speed = travelled / dt if dt > 0 else 0.0
        target = min(1.0, speed / 4.0)
        self.limb_amount += (target - self.limb_amount) * min(1.0, dt * 8)
        self.limb_swing += travelled * 6.0

    def _limb_angle(self, phase=0.0):
        return math.cos(self.limb_swing + phase) * 1.4 * self.limb_amount

    # -------------------------------------------------------------- render
    def render(self, dt=0.0):
        player = self.gl.player
        if player is None or player.playerDead:
            return
        if not self._texture_loaded:
            self._load_texture()

        travelled = 0.0
        if self._last_position is not None:
            travelled = math.dist(self._last_position, player.position)
        self._last_position = tuple(player.position)
        self.update_limb_state(max(dt, 1e-6), travelled)

        feet_y = player.position[1] - player.FEET_OFFSET + self.FEET_MODEL_DEPTH

        glEnable(GL_TEXTURE_2D)
        if self.tex_id:
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
        else:
            glDisable(GL_TEXTURE_2D)
        glColor3f(1, 1, 1)
        glPushMatrix()
        glTranslatef(player.position[0], feet_y, player.position[2])
        glScalef(1, -1, 1)
        glScalef(self.MODEL_SCALE, self.MODEL_SCALE, self.MODEL_SCALE)
        glRotatef(player.rotation[1] + 180, 0, 1, 0)

        head_x = math.radians(player.rotation[0])
        swing = self._limb_angle()
        opposite = self._limb_angle(math.pi)
        arm_swing = math.sin((1.0 - player.hand_swing) * math.pi) \
            if player.hand_swing > 0 else 0.0

        self._draw_cube(self.HEAD, head_x, 0.0, 0.0)
        self._draw_cube(self.HAT, head_x, 0.0, 0.0)
        self._draw_cube(self.BODY, 0, 0, 0)
        self._draw_cube(self.ARM_RIGHT, swing - arm_swing * 1.2, 0, 0)
        self._draw_cube(self.ARM_LEFT, opposite, 0, 0)
        self._draw_cube(self.LEG_RIGHT, opposite, 0, 0)
        self._draw_cube(self.LEG_LEFT, swing, 0, 0)

        glPopMatrix()
        glDisable(GL_TEXTURE_2D)

    # ------------------------------------------------------------ boxes
    def _draw_cube(self, part, xRot=0.0, yRot=0.0, zRot=0.0):
        """Draw a humanoid box; identical layout to PassiveMob._draw_cube."""
        x, y, z, width, height, depth, ox, oy, oz, tex_u, tex_v = part

        glPushMatrix()
        glTranslatef(ox, oy, oz)
        glRotatef(math.degrees(zRot), 0, 0, 1)
        glRotatef(math.degrees(yRot), 0, 1, 0)
        glRotatef(math.degrees(xRot), 1, 0, 0)

        x1, y1, z1 = x + width, y + height, z + depth
        v = [
            (x, y, z), (x1, y, z), (x1, y1, z), (x, y1, z),
            (x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1),
        ]

        polygons = [
            (5, 1, 2, 6, tex_u + depth + width, tex_v + depth,
             tex_u + depth + width + depth, tex_v + depth + height),
            (0, 4, 7, 3, tex_u, tex_v + depth,
             tex_u + depth, tex_v + depth + height),
            (5, 4, 0, 1, tex_u + depth, tex_v,
             tex_u + depth + width, tex_v + depth),
            (2, 3, 7, 6, tex_u + depth + width, tex_v,
             tex_u + depth + width + width, tex_v + depth),
            (1, 0, 3, 2, tex_u + depth, tex_v + depth,
             tex_u + depth + width, tex_v + depth + height),
            (4, 5, 6, 7, tex_u + depth + width + depth, tex_v + depth,
             tex_u + depth + width + depth + width, tex_v + depth + height),
        ]

        glBegin(GL_QUADS)
        for i0, i1, i2, i3, u0, v0, u1, v1 in polygons:
            u0n, u1n = u0 / self.tex_w, u1 / self.tex_w
            v0n, v1n = 1 - v0 / self.tex_h, 1 - v1 / self.tex_h
            glTexCoord2f(u0n, v0n); glVertex3f(*v[i0])
            glTexCoord2f(u1n, v0n); glVertex3f(*v[i1])
            glTexCoord2f(u1n, v1n); glVertex3f(*v[i2])
            glTexCoord2f(u0n, v1n); glVertex3f(*v[i3])
        glEnd()

        glPopMatrix()
