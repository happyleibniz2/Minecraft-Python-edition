from random import choice
from OpenGL.GL import *
from functions import *

class Particles:
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

        for i in range(count):
            dx, dy, dz = choice(numbers), choice(numbers), choice(numbers)
            ps = randint(4, 8) / 1000
            self.particles.append([list(p), cubeClass, randint(1, 4) / 10, [dx, dy, dz], .001, direction, 0.02, ps])

    def drawParticles(self, dt):
        if not self.particles:
            return

        for particle in self.particles[:]:
            if particle[2] <= 0:
                self.particles.remove(particle)
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

            x, y, z = tuple(particle[0])
            X, Y, Z = x + particle[2], y + particle[2], z + particle[2]

            tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[4], ('v3f', (X, y, z, x, y, z, x, Y, z, X, Y, z)), tex_coords)
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[5], ('v3f', (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z)), tex_coords)
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[0], ('v3f', (x, y, z, x, y, Z, x, Y, Z, x, Y, z)), tex_coords)
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[1], ('v3f', (X, y, Z, X, y, z, X, Y, z, X, Y, Z)), tex_coords)
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[2], ('v3f', (x, y, z, X, y, z, X, y, Z, x, y, Z)), tex_coords)
            self.gl.stuffBatch.add(4, GL_QUADS, particle[1].t[3], ('v3f', (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z)), tex_coords)

            particle[2] -= 0.009 * dt * 60