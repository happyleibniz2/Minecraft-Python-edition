import gc
import threading

from OpenGL.GLU import *
from pyglet.gl import *

from functions import *
from game.Lighting.Light import Light
from game.Particles import Particles
from game.blocks.DestroyBlock import DestroyBlock
from game.blocks.droppedBlock import droppedBlock
from game.entity.Inventory import Inventory
from game.entity.Zombie import Zombie
from game.world.Clouds import Clouds
from game.world.worldGenerator import worldGenerator
from game.blocks.CubeHandler import CubeHandler


class CompatVertexList:
    def __init__(self, count, mode, texture, *attributes):
        self.count = count
        self.mode = mode
        self.texture = texture
        self.attributes = {}
        for name, values in attributes:
            self.attributes[name] = values

    def draw(self):
        if self.texture is not None:
            texture = self.texture
            if hasattr(texture, 'bind'):
                texture.bind()
            elif hasattr(texture, 'get_texture'):
                texture = texture.get_texture()
                texture.bind()
            else:
                glBindTexture(GL_TEXTURE_2D, int(texture))

        glBegin(self.mode)
        vertices = self.attributes.get('v3f', ())
        tex_coords = self.attributes.get('t2f', ())
        colors = self.attributes.get('c3f', ())

        for i in range(0, len(vertices), 3):
            vertex_index = i // 3
            if tex_coords:
                uv_index = vertex_index * 2
                glTexCoord2f(tex_coords[uv_index], tex_coords[uv_index + 1])
            if colors:
                color_index = vertex_index * 3
                glColor3f(colors[color_index], colors[color_index + 1], colors[color_index + 2])
            glVertex3f(vertices[i], vertices[i + 1], vertices[i + 2])
        glEnd()

        glColor3f(1.0, 1.0, 1.0)
        glBindTexture(GL_TEXTURE_2D, 0)

    def delete(self):
        pass


class CompatBatch:
    def __init__(self):
        self._items = []

    def add(self, count, mode, texture, *attributes):
        item = CompatVertexList(count, mode, texture, *attributes)
        self._items.append(item)
        return item

    def draw(self):
        for item in self._items:
            item.draw()

    def __iter__(self):
        return iter(self._items)


def compat_draw(vertices, mode=GL_QUADS, texture=None, texcoords=None, colors=None):
    if texture is not None:
        if hasattr(texture, 'bind'):
            texture.bind()
        elif hasattr(texture, 'get_texture'):
            texture = texture.get_texture()
            texture.bind()
        else:
            glBindTexture(GL_TEXTURE_2D, int(texture))

    glBegin(mode)
    for i in range(0, len(vertices), 3):
        if texcoords:
            glTexCoord2f(texcoords[i * 2], texcoords[i * 2 + 1])
        if colors:
            glColor3f(colors[i], colors[i + 1], colors[i + 2])
        glVertex3f(vertices[i], vertices[i + 1], vertices[i + 2])
    glEnd()

    glColor3f(1.0, 1.0, 1.0)
    glBindTexture(GL_TEXTURE_2D, 0)


class Scene:
    def __init__(self):
        print("Init Scene class...")

        self.WIDTH, self.HEIGHT = WIDTH, HEIGHT

        self.gui = None
        self.sound = None
        self.blockSound = None
        self.deathScreen = None
        self.player = None

        self.lookingAt = "Nothing"

        self.texture, self.block, self.texture_dir, self.inventory_textures = {}, {}, {}, {}
        self.fov = FOV
        self.updateEvents = []
        self.entity = []
        self.skyColor = [128, 179, 255]
        self.panorama = {}
        self.in_water = False

        self.resetScene()

    def resetScene(self):
        self.allowEvents = {
            "movePlayer": True,
            "grabMouse": True,
            "keyboardAndMouse": True,
            "showCrosshair": True,
        }

        self.clouds = Clouds(self)
        self.droppedBlock = droppedBlock(self)
        self.worldGen = worldGenerator(self, randint(434, 434343454))
        self.particles = Particles(self)
        self.destroy = DestroyBlock(self)
        self.light = Light(self)

        self.drawCounter = 0
        self.genTime = 1
        self.startPlayerPos = [0, -9000, 0]

    def loadPanoramaTextures(self):
        print("Loading panorama textures...")
        for e, i in enumerate(os.listdir("gui/bg/")):
            image = pyglet.image.load("gui/bg/" + i)
            try:
                tex = image.get_texture(rectangle=True)
            except TypeError:
                tex = image.get_texture()
            self.panorama[e] = tex
            if hasattr(tex, 'mag_filter'):
                tex.mag_filter = GL_LINEAR
                tex.min_filter = GL_LINEAR
                tex.wrap_s = GL_CLAMP_TO_EDGE
                tex.wrap_t = GL_CLAMP_TO_EDGE
            else:
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    def initScene(self):
        print("Init OpenGL scene...")

        glClearColor(0.5, 0.7, 1, 1)
        glClearDepth(1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        glShadeModel(GL_SMOOTH)
        glMatrixMode(GL_PROJECTION)
        glDepthFunc(GL_LEQUAL)
        glAlphaFunc(GL_GEQUAL, 1)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_FOG)
        glHint(GL_FOG_HINT, GL_DONT_CARE)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glEnable(GL_TEXTURE_2D)

        glLoadIdentity()
        load_textures(self)
        self.loadPanoramaTextures()

        self.transparent = CompatBatch()
        self.opaque = CompatBatch()
        self.stuffBatch = CompatBatch()
        self.player.inventory = Inventory(self)
        self.cubes = CubeHandler(self.opaque, self.block, self.opaque,
                                 ('leaves_taiga', 'leaves_oak', 'tall_grass', 'nocolor'), self)

        self.zombie = Zombie(self)
        self.zombie.position = [0, 53, 0]
        self.entity.append(self.zombie)

        self.set3d()

    def set2d(self):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluOrtho2D(0, self.WIDTH, 0, self.HEIGHT)

    def set3d(self):
        glLoadIdentity()
        gluPerspective(self.fov, (self.WIDTH / self.HEIGHT), 0.1, RENDER_DISTANCE)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def resizeCGL(self, w, h, changeRes=True):
        if changeRes:
            self.WIDTH = w
            self.HEIGHT = h
        glViewport(0, 0, w, h)

    def drawPanorama(self):
        # Use immediate mode OpenGL for the panorama
        pp = self.player.position
        sx, sy, sz = 60, 60, 60

        x, y, z = pp[0] - (sx // 2), -(sy // 2), pp[2] - (sz // 2)
        X, Y, Z = x + sx, y + sy, z + sz

        # Define faces: (texture, vertices)
        faces = [
            (self.panorama[2], X, y, z, x, y, z, x, Y, z, X, Y, z),  # back
            (self.panorama[0], x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),  # front
            (self.panorama[3], x, y, z, x, y, Z, x, Y, Z, x, Y, z),  # left
            (self.panorama[1], X, y, Z, X, y, z, X, Y, z, X, Y, Z),  # right
            (self.panorama[5], x, y, z, X, y, z, X, y, Z, x, y, Z),  # bottom
            (self.panorama[4], x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),  # top
        ]

        for tex, v0, v1, v2, v3, v4, v5, v6, v7, v8, v9, v10, v11 in faces:
            glBindTexture(GL_TEXTURE_2D, tex.id)
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex3f(v0, v1, v2)
            glTexCoord2f(1, 0); glVertex3f(v3, v4, v5)
            glTexCoord2f(1, 1); glVertex3f(v6, v7, v8)
            glTexCoord2f(0, 1); glVertex3f(v9, v10, v11)
            glEnd()
        glBindTexture(GL_TEXTURE_2D, 0)

    def genWorld(self):
        self.drawCounter += 1
        if self.drawCounter > self.genTime:
            self.drawCounter = 0
            self.worldGen.genChunk(self.player)

    def updateScene(self):

        self.genWorld()
        if self.in_water:
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(0, 0, 0, 1))
            glFogf(GL_FOG_START, 10)
            glFogf(GL_FOG_END, 35)
        else:
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(0.5, 0.7, 1, 1))
            glFogf(GL_FOG_START, 10)
            glFogf(GL_FOG_END, 80)

        self.set3d()
        glClearColor(self.skyColor[0] / 255, self.skyColor[1] / 255, self.skyColor[2] / 255, 1)

        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        self.player.update()
        self.draw()

        self.clouds.update()
        self.droppedBlock.update()

        for i in self.entity:
            i.update()

        self.particles.drawParticles()
        self.light.update()

        blockByVec = self.cubes.hitTest(self.player.position, self.player.get_sight_vector())
        if blockByVec[0]:
            self.destroy.drawDestroy(*blockByVec[0])

            glPolygonMode(GL_FRONT_AND_BACK, GL_LINE)
            glColor3d(0, 0, 0)
            compat_draw(flatten(cube_vertices(blockByVec[0], 0.51)), mode=GL_QUADS)
            glPolygonMode(GL_FRONT_AND_BACK, GL_FILL)
            glColor3d(1, 1, 1)

            self.lookingAt = f"{blockByVec[0][0]} {blockByVec[0][1]} {blockByVec[0][2]} " \
                             f"({self.cubes.cubes[blockByVec[0]].name})"
        else:
            self.lookingAt = "Nothing"

        glColor3d(1, 1, 1)
        glPopMatrix()
        self.set2d()

        self.blockSound.pickUpAlreadyPlayed = False

        for i in self.updateEvents:
            i()

    def draw(self):
        glEnable(GL_ALPHA_TEST)
        self.opaque.draw()
        glDisable(GL_ALPHA_TEST)
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
        self.transparent.draw()
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
        self.transparent.draw()

        self.stuffBatch.draw()
        self.stuffBatch = CompatBatch()