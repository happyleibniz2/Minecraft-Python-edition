from random import randint
from OpenGL.GL import *
import numpy as np
import math
from functions import roundPos

class droppedBlock:
    def __init__(self, gl):
        self.gl = gl
        self.blocks = {}

    def addBlock(self, coords, name, dr=True, velocity=None, pickup_delay=0.0, count=1):
        velocity = list(velocity or (0.0, 0.0, 0.0))
        self.blocks[len(self.blocks)] = [
            tuple(coords), name, randint(0, 2) / 10, [0, "-"], 0, dr,
            velocity, float(pickup_delay), max(1, int(count)),
        ]

    def update(self, dt):
        for key, entry in tuple(self.blocks.items()):
            entry[7] = max(0.0, entry[7] - dt)
            self._update_physics(entry, dt)
            player = self.gl.player
            feet_y = player.position[1] - player.FEET_OFFSET
            pp = (player.position[0], feet_y, player.position[2])

            dx = pp[0] - entry[0][0]
            dy = pp[1] - entry[0][1]
            dz = pp[2] - entry[0][2]
            if (entry[7] <= 0 and dx * dx + dy * dy + dz * dz <= 2.25
                    and player.hp > 0):
                leftover = self.gl.player.inventory.addBlock(entry[1], entry[8])
                if leftover < entry[8]:
                    self.gl.blockSound.playPickUpSound()
                if leftover <= 0:
                    self.blocks.pop(key, None)
                else:
                    entry[8] = leftover
                continue

            entry[4] += dt * 0.5
            entry[3][0] += (0.003 if entry[3][1] == "+" else -0.003) * dt * 60
            if entry[3][0] < -0.1:
                entry[3][1] = "+"
            if entry[3][0] > 0.1:
                entry[3][1] = "-"
            if entry[0][1] < -90:
                self.blocks.pop(key, None)
                continue
            self._add_to_batch(entry)

    def render(self):
        for entry in self.blocks.values():
            self._add_to_batch(entry)

    def _add_to_batch(self, entry):
        x, y, z = 0, 0, 0
        X, Y, Z = 0.25, 0.25, 0.25
        kx = entry[0][0] - entry[2]
        ky = entry[0][1] + 0.1 + entry[3][0]
        kz = entry[0][2] + entry[2]
        vertexes = [
            (X, y, z, x, y, z, x, Y, z, X, Y, z),
            (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),
            (x, y, z, x, y, Z, x, Y, Z, x, Y, z),
            (X, y, Z, X, y, z, X, Y, z, X, Y, Z),
            (x, y, z, X, y, z, X, y, Z, x, y, Z),
            (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),
        ]
        angle = entry[4]
        rotation = np.array([
            [math.cos(angle), 0, math.sin(angle), 1],
            [0, 1, 0, 1],
            [-math.sin(angle), 0, math.cos(angle), 1],
            [0, 0, 0, 1],
        ])
        for index, vertices in enumerate(vertexes):
            rotated = np.array(vertices).reshape(4, 3)
            rotated = np.column_stack((rotated, np.ones(4))) @ rotation
            vertexes[index] = tuple(
                value
                for point in rotated
                for value in (point[0] + kx, point[1] + ky, point[2] + kz)
            )

        name = entry[1]
        tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
        block = self.gl.block.get(name)
        if block is not None and name != "torch":
            self.gl.stuffBatch.add(4, GL_QUADS, block[4], ('v3f', vertexes[0]), tex_coords)
            if entry[5]:
                for face, texture in zip(vertexes[1:], (block[5], block[0], block[1], block[2], block[3])):
                    self.gl.stuffBatch.add(4, GL_QUADS, texture, ('v3f', face), tex_coords)
            return

        item = self.gl.texture.get(name)
        if item is not None:
            self.gl.stuffBatch.add(4, GL_QUADS, item, ('v3f', vertexes[0]), tex_coords)

    def _update_physics(self, entry, dt):
        x, y, z = entry[0]
        velocity = entry[6]
        velocity[1] -= 9.8 * dt

        drag = 0.98 ** (dt * 20)
        velocity[0] *= drag
        velocity[2] *= drag

        nx = x + velocity[0] * dt
        ny = y + velocity[1] * dt
        nz = z + velocity[2] * dt

        floor = roundPos((nx, ny - 0.05, nz))
        if floor in self.gl.cubes.collidable and velocity[1] <= 0:
            ny = floor[1] + 0.51
            velocity[1] = -velocity[1] * 0.25 if abs(velocity[1]) > 0.8 else 0.0
            velocity[0] *= 0.6
            velocity[2] *= 0.6

        entry[0] = (nx, ny, nz)
