"""Lightweight positional sound physics for Pygame's stereo mixer."""

import math


class SoundPhysics:
    MAX_DISTANCE = 32.0

    def __init__(self, gl):
        self.gl = gl

    def apply(self, channel, source=None, volume=1.0, max_distance=None):
        if channel is None:
            return None
        player = getattr(self.gl, "player", None)
        if source is None or player is None:
            channel.set_volume(volume)
            return channel

        max_distance = float(max_distance or self.MAX_DISTANCE)
        dx = source[0] - player.position[0]
        dy = source[1] - player.position[1]
        dz = source[2] - player.position[2]
        distance = math.sqrt(dx * dx + dy * dy + dz * dz)
        if distance >= max_distance:
            channel.set_volume(0.0, 0.0)
            return channel

        gain = (1.0 - distance / max_distance) ** 2
        horizontal = math.hypot(dx, dz)
        if horizontal > 1e-6:
            yaw = math.radians(player.rotation[1])
            right_x, right_z = math.cos(yaw), math.sin(yaw)
            pan = max(-1.0, min(1.0, (dx * right_x + dz * right_z) / horizontal))
        else:
            pan = 0.0

        if self._is_occluded(player.position, source, distance):
            gain *= 0.35

        gain *= volume
        left = gain * (1.0 - max(0.0, pan) * 0.72)
        right = gain * (1.0 + min(0.0, pan) * 0.72)
        channel.set_volume(max(0.0, left), max(0.0, right))
        return channel

    def _is_occluded(self, listener, source, distance):
        cubes = getattr(self.gl, "cubes", None)
        if cubes is None or distance <= 1e-6:
            return False
        direction = tuple((source[i] - listener[i]) / distance for i in range(3))
        block, _ = cubes.hitTest(listener, direction, dist=math.ceil(distance))
        if block is None:
            return False
        hit_distance = math.sqrt(sum((block[i] - listener[i]) ** 2 for i in range(3)))
        return hit_distance < distance - 0.75
