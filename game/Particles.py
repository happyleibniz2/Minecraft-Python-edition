import math
from random import choice
from OpenGL.GL import *
from functions import *

class Particles:
    MAX_PARTICLES = 512
    RENDER_DISTANCE = 48

    def __init__(self, gl):
        self.particles = []
        self.gl = gl
        self.texture = pyglet.graphics.TextureGroup(pyglet.image.load("particles/particle.png").get_mipmapped_texture())
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    def addParticle(self, p, cubeClass, direction=None, numbers=None, count=30):
        if numbers is None:
            numbers = range(-5, 5)
            if not direction:
                numbers = range(-5, 5)

        count = min(count, self.MAX_PARTICLES - len(self.particles))
        for i in range(max(0, count)):
            dx, dy, dz = choice(numbers), choice(numbers), choice(numbers)
            ps = randint(4, 8) / 1000
            self.particles.append([list(p), cubeClass, randint(1, 4) / 10, [dx, dy, dz], .001, direction, 0.02, ps])

    def drawParticles(self, dt):
        if not self.particles:
            return

        yaw = math.radians(self.gl.player.rotation[1])
        pitch = math.radians(self.gl.player.rotation[0])
        right = (math.cos(yaw), 0.0, math.sin(yaw))
        up = (-math.sin(yaw) * math.sin(pitch),
              math.cos(pitch),
              math.cos(yaw) * math.sin(pitch))
        player = self.gl.player.position
        alive = []

        for particle in self.particles:
            if particle[2] <= 0:
                continue

            if particle[5] != "no":
                if particle[5] == "down":
                    if roundPos((particle[0][0], particle[0][1], particle[0][2])) not in self.gl.cubes.cubes:
                        particle[0][1] += particle[6] * dt * 60
                        particle[0][0] += (particle[3][0] / 100) * dt * 60
                        particle[0][2] += (particle[3][2] / 100) * dt * 60
                        particle[6] -= particle[7] * dt * 60
                elif particle[5] == "up":
                    if roundPos((particle[0][0], particle[0][1], particle[0][2])) not in self.gl.cubes.cubes:
                        particle[0][1] += particle[6] * dt * 60
                        particle[0][0] += (particle[3][0] / 100) * dt * 60
                        particle[0][2] += (particle[3][2] / 100) * dt * 60
                        particle[6] += particle[7] * dt * 60
                elif particle[5] == "left":
                    if roundPos((particle[0][0], particle[0][1], particle[0][2])) not in self.gl.cubes.cubes:
                        particle[0][0] += particle[6] * dt * 60
                        particle[0][1] += (particle[3][1] / 100) * dt * 60
                        particle[0][2] += particle[6] * dt * 60
                        particle[6] -= particle[7] * dt * 60
                elif particle[5] == "right":
                    if roundPos((particle[0][0], particle[0][1], particle[0][2])) not in self.gl.cubes.cubes:
                        particle[0][0] += particle[6] * dt * 60
                        particle[0][1] += (particle[3][1] / 100) * dt * 60
                        particle[0][2] += particle[6] * dt * 60
                        particle[6] += particle[7] * dt * 60
            else:
                particle[0][0] += (particle[3][0] / 50) * dt * 60
                particle[0][2] += (particle[3][2] / 50) * dt * 60

            particle[2] -= 0.009 * dt * 60
            if particle[2] <= 0:
                continue
            alive.append(particle)

            x, y, z = particle[0]
            dx, dy, dz = x - player[0], y - player[1], z - player[2]
            if dx * dx + dy * dy + dz * dz > self.RENDER_DISTANCE ** 2:
                continue

            size = particle[2]
            rx, ry, rz = (component * size for component in right)
            ux, uy, uz = (component * size for component in up)
            vertices = (
                x - rx - ux, y - ry - uy, z - rz - uz,
                x + rx - ux, y + ry - uy, z + rz - uz,
                x + rx + ux, y + ry + uy, z + rz + uz,
                x - rx + ux, y - ry + uy, z - rz + uz,
            )
            tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[4],
                                   ('v3f', vertices), tex_coords)

        self.particles = alive
