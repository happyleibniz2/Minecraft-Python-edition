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
        cpy = self.blocks.copy().items()
        for i in cpy:
            entry = i[1]
            entry[7] = max(0.0, entry[7] - dt)
            self._update_physics(entry, dt)
            pp = list(self.gl.player.position)
            sx, sy, sz = 0.25, 0.25, 0.25

            x, y, z = 0, 0, 0
            X, Y, Z = x + sx, y + sy, z + sz
            kx, ky, kz = i[1][0][0] - i[1][2], i[1][0][1] + 0.1 + i[1][3][0], i[1][0][2] + i[1][2]

            dx = pp[0] - entry[0][0]
            dy = pp[1] - entry[0][1]
            dz = pp[2] - entry[0][2]
            if (entry[7] <= 0 and dx * dx + dy * dy + dz * dz <= 2.25
                    and self.gl.player.hp > 0):
                leftover = self.gl.player.inventory.addBlock(entry[1], entry[8])
                if leftover < entry[8]:
                    self.gl.blockSound.playPickUpSound()
                if leftover <= 0:
                    self.blocks.pop(i[0])
                else:
                    entry[8] = leftover
                continue

            vertexes = [
                (X, y, z, x, y, z, x, Y, z, X, Y, z),
                (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),
                (x, y, z, x, y, Z, x, Y, Z, x, Y, z),
                (X, y, Z, X, y, z, X, Y, z, X, Y, Z),
                (x, y, z, X, y, z, X, y, Z, x, y, Z),
                (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),
            ]

            rot = np.array([
                [math.cos(i[1][4]), 0, math.sin(i[1][4]), 1],
                [0, 1, 0, 1],
                [-math.sin(i[1][4]), 0, math.cos(i[1][4]), 1],
                [0, 0, 0, 1],
            ])
            i[1][4] += dt * 0.5  # radians per second

            for e, j in enumerate(vertexes):
                r1 = ((j[0], j[1], j[2], 1),
                      (j[3], j[4], j[5], 1),
                      (j[6], j[7], j[8], 1),
                      (j[9], j[10], j[11], 1)) @ rot
                vertexes[e] = (r1[0][0] + kx, r1[0][1] + ky, r1[0][2] + kz,
                               r1[1][0] + kx, r1[1][1] + ky, r1[1][2] + kz,
                               r1[2][0] + kx, r1[2][1] + ky, r1[2][2] + kz,
                               r1[3][0] + kx, r1[3][1] + ky, r1[3][2] + kz)

            name = i[1][1]
            tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
            block = self.gl.block.get(name)

            if block is not None and name != "torch":
                self.gl.stuffBatch.add(4, GL_QUADS, block[4], ('v3f', vertexes[0]), tex_coords)
                if i[1][5]:
                    self.gl.stuffBatch.add(4, GL_QUADS, block[5], ('v3f', vertexes[1]), tex_coords)
                    self.gl.stuffBatch.add(4, GL_QUADS, block[0], ('v3f', vertexes[2]), tex_coords)
                    self.gl.stuffBatch.add(4, GL_QUADS, block[1], ('v3f', vertexes[3]), tex_coords)
                    self.gl.stuffBatch.add(4, GL_QUADS, block[2], ('v3f', vertexes[4]), tex_coords)
                    self.gl.stuffBatch.add(4, GL_QUADS, block[3], ('v3f', vertexes[5]), tex_coords)
            else:
                # items (buckets, saplings...) have no block faces; Minecraft
                # renders them as a flat sprite instead of a cube
                item = self.gl.texture.get(name)
                if item is not None:
                    self.gl.stuffBatch.add(4, GL_QUADS, item, ('v3f', vertexes[0]), tex_coords)
                    self.gl.stuffBatch.add(4, GL_QUADS, item, ('v3f', vertexes[1]), tex_coords)

            if i[1][3][1] == "-":
                i[1][3][0] -= 0.003 * dt * 60
            if i[1][3][1] == "+":
                i[1][3][0] += 0.003 * dt * 60

            if i[1][3][0] < -0.1:
                i[1][3][1] = "+"
            if i[1][3][0] > 0.1:
                i[1][3][1] = "-"

            if i[1][0][1] < -90:
                self.blocks.pop(i[0])
                continue
            self.blocks[i[0]][4] = i[1][4]

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
