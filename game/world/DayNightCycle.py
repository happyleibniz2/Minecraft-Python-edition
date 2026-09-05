"""Minecraft-like 24,000-tick day/night cycle."""

import math
import os
import random

import pyglet
from OpenGL.GL import *


def _clamp(value, low=0.0, high=1.0):
    return max(low, min(high, value))


def _smoothstep(edge0, edge1, value):
    value = _clamp((value - edge0) / (edge1 - edge0))
    return value * value * (3.0 - 2.0 * value)


def _mix(a, b, amount):
    return tuple(a[i] + (b[i] - a[i]) * amount for i in range(3))


class DayNightCycle:
    TICKS_PER_DAY = 24000.0
    TICKS_PER_SECOND = 20.0

    DAY_SKY = (0.50, 0.70, 1.00)
    NIGHT_SKY = (0.015, 0.020, 0.070)
    TWILIGHT_SKY = (0.82, 0.32, 0.16)

    def __init__(self, time_ticks=1000.0):
        self.total_ticks = float(time_ticks)
        self.time_ticks = self.total_ticks % self.TICKS_PER_DAY
        self._stars = self._build_stars()
        self._galaxy_stars = self._build_galaxy()
        self.weather_strength = 0.0
        self._recalculate()

    def set_time(self, ticks):
        self.time_ticks = float(ticks) % self.TICKS_PER_DAY
        day = math.floor(self.total_ticks / self.TICKS_PER_DAY)
        self.total_ticks = day * self.TICKS_PER_DAY + self.time_ticks
        self._recalculate()

    def update(self, dt):
        self.total_ticks += max(0.0, dt) * self.TICKS_PER_SECOND
        self.time_ticks = self.total_ticks % self.TICKS_PER_DAY
        self._recalculate()

    def _recalculate(self):
        phase = self.time_ticks / self.TICKS_PER_DAY
        self.sun_angle = phase * math.tau
        self.moon_angle = self.sun_angle + math.pi
        sun_height = math.sin(self.sun_angle)

        daylight = _smoothstep(-0.12, 0.18, sun_height)
        self.sky_brightness = 0.12 + daylight * 0.88
        self.star_brightness = _clamp((0.28 - daylight) / 0.28)

        sky = _mix(self.NIGHT_SKY, self.DAY_SKY, daylight)
        twilight = _clamp(1.0 - abs(sun_height) / 0.28) * (1.0 - abs(daylight - 0.5) * 1.35)
        twilight = _clamp(twilight)
        self.sky_color = _mix(sky, self.TWILIGHT_SKY, twilight * 0.55)
        self.fog_color = _mix(self.sky_color, (0.72, 0.76, 0.82), daylight * 0.18)
        self.horizon_color = _mix(self.fog_color, self.TWILIGHT_SKY, twilight * 0.35)
        night_zenith = (0.006, 0.009, 0.035)
        day_zenith = (0.22, 0.48, 0.92)
        self.zenith_color = _mix(night_zenith, day_zenith, daylight)

        # This is the exact orbit used by Scene.drawCelestialSky after its
        # X-axis rotation: local +Y becomes (0, sin(a), -cos(a)).
        x = 0.0
        y = math.sin(self.sun_angle)
        z = -math.cos(self.sun_angle)
        if y < 0:
            x, y, z = -x, -y, -z
        length = math.sqrt(x * x + y * y + z * z)
        self.light_direction = (x / length, y / length, z / length)

    @staticmethod
    def _build_stars(count=180):
        rng = random.Random(10842)
        stars = []
        while len(stars) < count:
            x = rng.uniform(-1, 1)
            y = rng.uniform(-1, 1)
            z = rng.uniform(-1, 1)
            length = math.sqrt(x * x + y * y + z * z)
            if 0.15 < length <= 1 and y > -0.25:
                stars.append((x / length, y / length, z / length))
        return tuple(stars)

    @staticmethod
    def _build_galaxy(count=420):
        """A dense, tilted Milky Way band with deterministic colors/sizes."""
        rng = random.Random(91723)
        stars = []
        tilt = math.radians(28)
        for _ in range(count):
            longitude = rng.uniform(0, math.tau)
            latitude = max(-0.22, min(0.22, rng.gauss(0, 0.075)))
            radius = math.cos(latitude)
            x = math.cos(longitude) * radius
            y = math.sin(latitude)
            z = math.sin(longitude) * radius
            rotated_y = y * math.cos(tilt) - z * math.sin(tilt)
            rotated_z = y * math.sin(tilt) + z * math.cos(tilt)
            intensity = rng.uniform(0.25, 0.85)
            blue = rng.uniform(0.82, 1.0)
            stars.append((x, rotated_y, rotated_z, intensity, blue))
        return tuple(stars)

    @property
    def stars(self):
        return self._stars

    @property
    def galaxy_stars(self):
        return self._galaxy_stars

    def set_weather(self, strength):
        self.weather_strength = _clamp(strength)

    @property
    def moon_phase(self):
        return int(self.total_ticks // self.TICKS_PER_DAY) % 8


def configure_celestial_textures(scene):
    """Load RGB Minecraft celestial textures with black made transparent."""
    environment = os.path.join("textures", "environment")
    scene.sun_texture = _load_transparent_texture(os.path.join(environment, "sun.png"))
    scene.moon_texture = _load_transparent_texture(os.path.join(environment, "moon_phases.png"))


def _load_transparent_texture(path):
    if not os.path.isfile(path):
        return None
    image = pyglet.image.load(path)
    width, height = image.width, image.height
    raw = image.get_image_data().get_data("RGB", width * 3)
    rgba = bytearray(width * height * 4)
    for source in range(0, len(raw), 3):
        target = source // 3 * 4
        red, green, blue = raw[source:source + 3]
        # The supplied vanilla images lost their alpha channel. Treat RGB as
        # premultiplied over black: brightness becomes alpha, then un-premultiply
        # color so standard alpha blending reconstructs the original glow.
        alpha = max(red, green, blue)
        if alpha:
            red = min(255, red * 255 // alpha)
            green = min(255, green * 255 // alpha)
            blue = min(255, blue * 255 // alpha)
        rgba[target:target + 4] = bytes((red, green, blue, alpha))
    texture = pyglet.image.ImageData(width, height, "RGBA", bytes(rgba), pitch=width * 4).get_texture()
    glBindTexture(texture.target, texture.id)
    glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
    glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
    glTexParameteri(texture.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
    glTexParameteri(texture.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
    return pyglet.graphics.TextureGroup(texture)
