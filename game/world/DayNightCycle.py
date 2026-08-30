"""Minecraft-like 24,000-tick day/night cycle."""

import math
import random


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
        self.time_ticks = float(time_ticks) % self.TICKS_PER_DAY
        self._stars = self._build_stars()
        self._recalculate()

    def set_time(self, ticks):
        self.time_ticks = float(ticks) % self.TICKS_PER_DAY
        self._recalculate()

    def update(self, dt):
        self.time_ticks = (self.time_ticks + max(0.0, dt) * self.TICKS_PER_SECOND) % self.TICKS_PER_DAY
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

    @property
    def stars(self):
        return self._stars
