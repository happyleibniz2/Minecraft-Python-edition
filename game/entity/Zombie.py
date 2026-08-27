import math
import pyglet
from OpenGL.GL import *
from game.entity.Entity import Entity

class Zombie(Entity):
    def __init__(self, gl):
        super().__init__(gl)

        # Load texture
        try:
            image = pyglet.image.load("textures/mobs/zombie.png")
            self.texture = image.get_texture()
            self.tex_id = self.texture.id
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
            self.has_texture = True
            self.tex_w = image.width
            self.tex_h = image.height
            print(f"Zombie texture: {self.tex_w} x {self.tex_h}")
        except:
            self.has_texture = False
            self.tex_w, self.tex_h = 64, 32
            print("Warning: zombie.png not found – using blank texture")

        # Model parts (RubyDung exact offsets)
        self.parts = [
            (-4, -8, -4, 8, 8, 8,  0,  0,  0,  0,  0),   # head
            (-4,  0, -2, 8, 12, 4,  0,  0,  0, 16, 16),  # body
            (-3, -2, -2, 4, 12, 4, -5,  2,  0, 40, 16),  # left arm
            (-1, -2, -2, 4, 12, 4,  5,  2,  0, 40, 16),  # right arm
            (-2,  0, -2, 4, 12, 4, -2, 12,  0,  0, 16),  # left leg
            (-2,  0, -2, 4, 12, 4,  2, 12,  0,  0, 16),  # right leg
        ]

        self.time = 0

    def update(self, dt):
        self.time += dt * 10

        # Chase player
        if hasattr(self.gl, 'player'):
            dx = self.gl.player.position[0] - self.position[0]
            dz = self.gl.player.position[2] - self.position[2]
            dist = math.hypot(dx, dz)
            if dist > 0.1:
                step = min(self.speed * dt * 60, dist)
                self.position[0] += (dx / dist) * step
                self.position[2] += (dz / dist) * step
                self.rotation[1] = math.degrees(math.atan2(dx, dz))

        super().update(dt)

    def render(self, a):
        glEnable(GL_TEXTURE_2D)
        if self.has_texture:
            glBindTexture(GL_TEXTURE_2D, self.tex_id)
        else:
            # Fallback: use a simple white texture (if we had one)
            # For now, we just skip texture binding
            pass

        scale = 0.058333334
        yy = -abs(math.sin(self.time * 0.6662)) * 5 - 23

        glPushMatrix()
        glTranslatef(self.position[0], self.position[1], self.position[2])
        glScalef(1, -1, 1)
        glScalef(scale, scale, scale)
        glTranslatef(0, yy, 0)
        glRotatef(self.rotation[1] + 180, 0, 1, 0)

        # Rotations
        head_x = math.sin(self.time) * 0.8
        head_y = math.sin(self.time * 0.83) * 1.0
        arm0_x = math.sin(self.time * 0.6662 + math.pi) * 2.0
        arm0_z = (math.sin(self.time * 0.2312) + 1.0) * 1.0
        arm1_x = math.sin(self.time * 0.6662) * 2.0
        arm1_z = (math.sin(self.time * 0.2812) - 1.0) * 1.0
        leg0_x = math.sin(self.time * 0.6662) * 1.4
        leg1_x = math.sin(self.time * 0.6662 + math.pi) * 1.4

        self._draw_cube(self.parts[0], head_x, head_y, 0)
        self._draw_cube(self.parts[1], 0, 0, 0)
        self._draw_cube(self.parts[2], arm0_x, 0, arm0_z)
        self._draw_cube(self.parts[3], arm1_x, 0, arm1_z)
        self._draw_cube(self.parts[4], leg0_x, 0, 0)
        self._draw_cube(self.parts[5], leg1_x, 0, 0)

        glPopMatrix()
        glDisable(GL_TEXTURE_2D)

    def _draw_cube(self, part, xRot=0, yRot=0, zRot=0):
        x, y, z, w, h, d, ox, oy, oz, texU, texV = part

        glPushMatrix()
        glTranslatef(ox, oy, oz)
        glRotatef(math.degrees(zRot), 0, 0, 1)
        glRotatef(math.degrees(yRot), 0, 1, 0)
        glRotatef(math.degrees(xRot), 1, 0, 0)

        x0, y0, z0 = x, y, z
        x1, y1, z1 = x + w, y + h, z + d

        v = [
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        ]

        polygons = [
            (5, 1, 2, 6, texU + d + w,     texV + d,     texU + d + w + d, texV + d + h),
            (0, 4, 7, 3, texU,             texV + d,     texU + d,         texV + d + h),
            (5, 4, 0, 1, texU + d,         texV,         texU + d + w,     texV + d),
            (2, 3, 7, 6, texU + d + w,     texV,         texU + d + w + w, texV + d),
            (1, 0, 3, 2, texU + d,         texV + d,     texU + d + w,     texV + d + h),
            (4, 5, 6, 7, texU + d + w + d, texV + d,     texU + d + w + d + w, texV + d + h),
        ]

        glBegin(GL_QUADS)
        for p in polygons:
            i0, i1, i2, i3, u0, v0, u1, v1 = p
            u0_n = u0 / self.tex_w if self.has_texture else 0
            v0_n = 1 - v0 / self.tex_h if self.has_texture else 0
            u1_n = u1 / self.tex_w if self.has_texture else 1
            v1_n = 1 - v1 / self.tex_h if self.has_texture else 1

            if not self.has_texture:
                glColor3f(0.5, 0.5, 0.5)  # grey fallback

            glTexCoord2f(u0_n, v0_n); glVertex3f(v[i0][0], v[i0][1], v[i0][2])
            glTexCoord2f(u1_n, v0_n); glVertex3f(v[i1][0], v[i1][1], v[i1][2])
            glTexCoord2f(u1_n, v1_n); glVertex3f(v[i2][0], v[i2][1], v[i2][2])
            glTexCoord2f(u0_n, v1_n); glVertex3f(v[i3][0], v[i3][1], v[i3][2])

            if not self.has_texture:
                glColor3f(1, 1, 1)  # reset
        glEnd()

        glPopMatrix()
