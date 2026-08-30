"""Layered procedural clouds with long draw distance and shared shadow wind."""

import math
import random

import pyglet
from OpenGL.GL import *


class Clouds:
    CLOUD_HEIGHT = 96.0
    DRAW_DISTANCE = 280.0
    GRID_RADIUS = 7
    GRID_SPACING = 40.0
    WIND_SPEED = 1.5

    def __init__(self, gl):
        self.gl = gl
        self.wind_x = 0.0
        self.wind_z = 0.0
        self.coverage = 0.56
        self.clusters = self._build_clusters()
        self.texture = self._build_puff_texture()

    @property
    def shadow_offset(self):
        return self.wind_x, self.wind_z

    def update(self, dt):
        self.wind_x += self.WIND_SPEED * max(0.0, dt)
        self.wind_z += self.WIND_SPEED * 0.28 * max(0.0, dt)
        light = getattr(self.gl, "light", None)
        if light is not None:
            light.set_clouds(self.shadow_offset, self.coverage)

    def render(self, player, cycle):
        if self.texture is None:
            return

        px, _, pz = player.position
        yaw = math.radians(player.rotation[1])
        pitch = math.radians(player.rotation[0])
        right = (math.cos(yaw), 0.0, math.sin(yaw))
        up = (-math.sin(yaw) * math.sin(pitch),
              math.cos(pitch),
              math.cos(yaw) * math.sin(pitch))

        puffs = []
        wrap = (self.GRID_RADIUS * 2 + 1) * self.GRID_SPACING
        for base_x, base_z, height, cluster in self.clusters:
            x = base_x + self.wind_x
            z = base_z + self.wind_z
            x += round((px - x) / wrap) * wrap
            z += round((pz - z) / wrap) * wrap
            dx, dz = x - px, z - pz
            if dx * dx + dz * dz > self.DRAW_DISTANCE * self.DRAW_DISTANCE:
                continue
            for ox, oy, oz, size, opacity in cluster:
                cx, cy, cz = x + ox, height + oy, z + oz
                distance = (cx - px) ** 2 + (cz - pz) ** 2
                puffs.append((distance, cx, cy, cz, size, opacity))

        puffs.sort(reverse=True)
        daylight = cycle.sky_brightness
        color = (
            0.20 + daylight * 0.80,
            0.23 + daylight * 0.75,
            0.31 + daylight * 0.69,
        )

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
        try:
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDisable(GL_CULL_FACE)
            glDepthMask(GL_FALSE)
            self.texture.set_state_recursive()

            glBegin(GL_QUADS)
            for _, cx, cy, cz, size, opacity in puffs:
                rx, ry, rz = (component * size for component in right)
                ux, uy, uz = (component * size * 0.62 for component in up)
                glColor4f(*color, opacity)
                glTexCoord2f(0, 0); glVertex3f(cx - rx - ux, cy - ry - uy, cz - rz - uz)
                glTexCoord2f(1, 0); glVertex3f(cx + rx - ux, cy + ry - uy, cz + rz - uz)
                glTexCoord2f(1, 1); glVertex3f(cx + rx + ux, cy + ry + uy, cz + rz + uz)
                glTexCoord2f(0, 1); glVertex3f(cx - rx + ux, cy - ry + uy, cz - rz + uz)
            glEnd()

            self.texture.unset_state_recursive()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    def _build_clusters(self):
        rng = random.Random(32917)
        clusters = []
        for gx in range(-self.GRID_RADIUS, self.GRID_RADIUS + 1):
            for gz in range(-self.GRID_RADIUS, self.GRID_RADIUS + 1):
                if rng.random() > self.coverage:
                    continue
                base_x = gx * self.GRID_SPACING + rng.uniform(-11, 11)
                base_z = gz * self.GRID_SPACING + rng.uniform(-11, 11)
                height = self.CLOUD_HEIGHT + rng.uniform(-3, 4)
                puffs = []
                count = rng.randint(5, 9)
                for _ in range(count):
                    angle = rng.uniform(0, math.tau)
                    radius = rng.uniform(0, 13)
                    puffs.append((
                        math.cos(angle) * radius,
                        rng.uniform(-2.5, 3.5),
                        math.sin(angle) * radius,
                        rng.uniform(8, 15),
                        rng.uniform(0.22, 0.42),
                    ))
                clusters.append((base_x, base_z, height, tuple(puffs)))
        return tuple(clusters)

    @staticmethod
    def _build_puff_texture(size=64):
        pixels = bytearray(size * size * 4)
        for y in range(size):
            for x in range(size):
                nx = (x + 0.5) / size * 2 - 1
                ny = (y + 0.5) / size * 2 - 1
                radius = math.sqrt(nx * nx + ny * ny)
                edge = max(0.0, min(1.0, (1.0 - radius) * 3.0))
                noise = (math.sin(x * 0.73 + y * 0.31)
                         + math.sin(x * 0.19 - y * 0.57)) * 0.035
                alpha = max(0.0, min(1.0, edge + noise))
                offset = (y * size + x) * 4
                pixels[offset:offset + 4] = bytes((255, 255, 255, round(alpha * 255)))

        image = pyglet.image.ImageData(size, size, "RGBA", bytes(pixels), pitch=size * 4)
        texture = image.get_texture()
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return pyglet.graphics.TextureGroup(texture)
