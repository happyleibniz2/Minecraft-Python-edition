"""Shared base for passive, wandering mobs (cows and sheep).

Implements Minecraft's ``WaterAvoidingRandomStrollGoal`` behaviour: the mob
idles, occasionally picks a random nearby destination, walks toward it while
turning smoothly, jumps over one-block obstacles, refuses to walk into water or
off ledges, and periodically looks around while idle.
"""

import math
import random

import pyglet
from OpenGL.GL import *

from functions import roundPos
from game.entity.Entity import Entity


class PassiveMob(Entity):
    TEXTURE_PATH = ""
    TEXTURE_SIZE = (64, 32)
    PARTS = ()
    MODEL_SCALE = 0.0625
    MODEL_OFFSET = 0.0

    WANDER_SPEED = 0.7          # blocks/second, Minecraft passive mob speed
    WANDER_CHANCE = 0.02        # per-tick chance to pick a new destination
    WANDER_RANGE = 10           # horizontal search radius
    IDLE_TIME = (1.0, 4.0)      # seconds spent idling between strolls
    TURN_SPEED = 360.0          # degrees/second of smooth turning
    JUMP_VELOCITY = 5.5
    LIMB_SWING_SPEED = 6.0

    def __init__(self, gl):
        super().__init__(gl)
        self.speed = self.WANDER_SPEED
        self.hp = 10

        self.target = None
        self.idle_timer = random.uniform(*self.IDLE_TIME)
        self.jump_cooldown = 0.0
        self.head_yaw = 0.0
        self.head_pitch = 0.0
        self.limb_swing = 0.0
        self.limb_amount = 0.0
        self.rotation[1] = random.uniform(0, 360)

        self.texture = None
        self.tex_id = None
        self.has_texture = False
        self.tex_w, self.tex_h = self.TEXTURE_SIZE
        self._load_textures()

    # ------------------------------------------------------------- textures
    def _load_texture(self, path):
        image = pyglet.image.load(path)
        texture = image.get_texture()
        glBindTexture(GL_TEXTURE_2D, texture.id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return texture, image

    def _load_textures(self):
        if not self.TEXTURE_PATH:
            return
        try:
            self.texture, image = self._load_texture(self.TEXTURE_PATH)
            self.tex_id = self.texture.id
            self.tex_w, self.tex_h = image.width, image.height
            self.has_texture = True
            print(f"{type(self).__name__} texture: {self.tex_w} x {self.tex_h}")
        except Exception as error:
            self.has_texture = False
            print(f"Warning: could not load {self.TEXTURE_PATH} ({error})")

    # ------------------------------------------------------------------- AI
    def update(self, dt):
        if dt <= 0:
            return

        self.jump_cooldown = max(0.0, self.jump_cooldown - dt)
        self._update_ai(dt)

        move_x, move_z = self._desired_movement(dt)
        self._apply_movement(dt, move_x, move_z)
        self._update_animation(dt, move_x, move_z)

    def _update_ai(self, dt):
        if self.target is not None:
            dx = self.target[0] - self.position[0]
            dz = self.target[1] - self.position[2]
            if math.hypot(dx, dz) < 0.35:
                self.target = None
                self.idle_timer = random.uniform(*self.IDLE_TIME)
            return

        self.idle_timer -= dt
        if self.idle_timer > 0:
            # idle mobs occasionally glance around, like Minecraft's LookGoal
            if random.random() < 0.02:
                self.head_yaw = random.uniform(-60, 60)
                self.head_pitch = random.uniform(-20, 20)
            return

        # scaled so the per-second chance matches Minecraft's per-tick chance
        if random.random() < 1.0 - (1.0 - self.WANDER_CHANCE) ** max(1, dt * 20):
            self.target = self._pick_destination()
            self.head_yaw = 0.0
            self.head_pitch = 0.0

    def _pick_destination(self):
        for _ in range(10):
            x = self.position[0] + random.uniform(-self.WANDER_RANGE, self.WANDER_RANGE)
            z = self.position[2] + random.uniform(-self.WANDER_RANGE, self.WANDER_RANGE)
            if self._is_walkable(x, z):
                return (x, z)
        return None

    def _is_walkable(self, x, z):
        """Avoid water and empty space, like WaterAvoidingRandomStrollGoal."""
        cubes = getattr(self.gl, "cubes", None)
        if cubes is None:
            return True

        feet_y = round(self.position[1] - 1.75)
        column = roundPos((x, feet_y, z))

        # reject water the mob would stand in or wade through
        for offset in (0, 1, 2):
            if (column[0], column[1] + offset, column[2]) in cubes.fluids:
                return False

        # require solid ground within a short drop, so ledges are avoided
        for offset in range(0, 3):
            ground = (column[0], column[1] - offset, column[2])
            if ground in cubes.fluids:
                return False
            if ground in cubes.collidable:
                return True
        return False

    def _desired_movement(self, dt):
        if self.target is None:
            return 0.0, 0.0

        dx = self.target[0] - self.position[0]
        dz = self.target[1] - self.position[2]
        distance = math.hypot(dx, dz)
        if distance < 1e-6:
            return 0.0, 0.0

        desired_yaw = math.degrees(math.atan2(dx, dz))
        self._turn_toward(desired_yaw, dt)

        step = min(self.speed * dt, distance)
        yaw = math.radians(self.rotation[1])
        return math.sin(yaw) * step, math.cos(yaw) * step

    def _turn_toward(self, desired_yaw, dt):
        difference = (desired_yaw - self.rotation[1] + 180) % 360 - 180
        limit = self.TURN_SPEED * dt
        self.rotation[1] += max(-limit, min(limit, difference))
        self.rotation[1] %= 360

    def _apply_movement(self, dt, move_x, move_z):
        sub_steps = 10
        sub_dt = dt / sub_steps
        step_x = move_x / sub_steps
        step_z = move_z / sub_steps

        for _ in range(sub_steps):
            grounded = self._is_grounded()
            target_x = self.position[0] + step_x
            target_z = self.position[2] + step_z
            self.move(sub_dt, step_x, 0, step_z)

            blocked = (abs(self.position[0] - target_x) > 1e-5 or
                       abs(self.position[2] - target_z) > 1e-5)
            if blocked and grounded and self.jump_cooldown == 0:
                self.dy = self.JUMP_VELOCITY
                self.jump_cooldown = 0.35
                self.target = None

        self.bInAir = not self._is_grounded()

    def _is_grounded(self):
        if self.dy > 0:
            return False
        x, y, z = self.position
        probe_y = y - 0.05
        return self.collide((x, probe_y, z))[1] > probe_y + 1e-5

    def _update_animation(self, dt, move_x, move_z):
        distance = math.hypot(move_x, move_z)
        speed = distance / dt if dt else 0.0
        target_amount = min(1.0, speed / max(self.speed, 1e-6))
        self.limb_amount += (target_amount - self.limb_amount) * min(1.0, dt * 8)
        self.limb_swing += distance * self.LIMB_SWING_SPEED

    # -------------------------------------------------------------- render
    def render(self, a):
        if not self.has_texture:
            return

        glEnable(GL_TEXTURE_2D)
        glColor3f(1, 1, 1)
        glPushMatrix()
        glTranslatef(self.position[0], self.position[1] + self.MODEL_OFFSET, self.position[2])
        glScalef(1, -1, 1)
        glScalef(self.MODEL_SCALE, self.MODEL_SCALE, self.MODEL_SCALE)
        glRotatef(self.rotation[1] + 180, 0, 1, 0)

        self._draw_model()

        glPopMatrix()
        glDisable(GL_TEXTURE_2D)

    def _limb_angle(self, phase=0.0):
        return math.cos(self.limb_swing + phase) * 1.4 * self.limb_amount

    def _draw_model(self):
        glBindTexture(GL_TEXTURE_2D, self.tex_id)
        self._draw_parts()

    def _draw_parts(self):
        raise NotImplementedError

    def _draw_cube(self, part, xRot=0.0, yRot=0.0, zRot=0.0):
        """Draw a Minecraft model box.

        ``part`` is ``(x, y, z, w, h, d, pivotX, pivotY, pivotZ, texU, texV)``
        where the box coordinates are **relative to the pivot**, exactly like
        ``ModelPart``: the pivot is translated to first, rotation happens about
        it, and the box is then laid out around that origin.
        """
        x, y, z, w, h, d, ox, oy, oz, texU, texV = part

        glPushMatrix()
        glTranslatef(ox, oy, oz)
        glRotatef(math.degrees(zRot), 0, 0, 1)
        glRotatef(math.degrees(yRot), 0, 1, 0)
        glRotatef(math.degrees(xRot), 1, 0, 0)

        x1, y1, z1 = x + w, y + h, z + d
        v = [
            (x, y, z), (x1, y, z), (x1, y1, z), (x, y1, z),
            (x, y, z1), (x1, y, z1), (x1, y1, z1), (x, y1, z1),
        ]

        polygons = [
            (5, 1, 2, 6, texU + d + w,     texV + d,     texU + d + w + d,     texV + d + h),
            (0, 4, 7, 3, texU,             texV + d,     texU + d,             texV + d + h),
            (5, 4, 0, 1, texU + d,         texV,         texU + d + w,         texV + d),
            (2, 3, 7, 6, texU + d + w,     texV,         texU + d + w + w,     texV + d),
            (1, 0, 3, 2, texU + d,         texV + d,     texU + d + w,         texV + d + h),
            (4, 5, 6, 7, texU + d + w + d, texV + d,     texU + d + w + d + w, texV + d + h),
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
