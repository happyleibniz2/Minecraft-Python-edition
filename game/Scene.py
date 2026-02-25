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
        self.skyColor = [128, 179, 255]  # [64, 89, 150]
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
        # sort filenames so that face indices are consistent regardless of
        # filesystem ordering.  Panorama expects files 0..5.
        files = sorted(os.listdir("gui/bg/"))
        for e, i in enumerate(files):
            try:
                tex = pyglet.image.load("gui/bg/" + i).get_texture()
                self.panorama[e] = pyglet.graphics.TextureGroup(tex)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                print(f"Loaded panorama texture {e}: {i}")
            except Exception as ex:
                print(f"Failed to load panorama texture {i}: {ex}")

    def vertexList(self):
        # create lightweight reticle coordinate list instead of using pyglet
        # vertex batches; pyglet.graphics.vertex_list is unavailable in
        # pyglet 2.x, and the reticle isn't used anywhere else anyway.
        x = self.WIDTH / 2
        y = self.HEIGHT / 2
        self.reticle = [
            (x - 10, y),
            (x + 10, y),
            (x, y - 10),
            (x, y + 10)
        ]

    def initScene(self):
        print("Init OpenGL scene...")

        glClearColor(0.5, 0.7, 1, 1)
        glClearDepth(1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        glShadeModel(GL_SMOOTH)
        glEnable(GL_CULL_FACE)              # cull back faces by default
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
        self.vertexList()

        # create batches; if pyglet fails (old driver) fall back to no-op objects
        class _DummyBatch:
            def draw(self):
                pass
        try:
            self.transparent = pyglet.graphics.Batch()
            self.opaque = pyglet.graphics.Batch()
            self.stuffBatch = pyglet.graphics.Batch()
        except Exception as e:
            print(f"Warning: failed to create pyglet batches: {e}")
            self.transparent = _DummyBatch()
            self.opaque = _DummyBatch()
            self.stuffBatch = _DummyBatch()
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
        self.vertexList()
        glViewport(0, 0, w, h)

    def drawPanorama(self):
        # render a simple sky cube around the player without using pyglet
        # batches, since the `Batch.add` method was removed in pyglet 2.x.

        # the panorama is just a static skybox; during menus the player may
        # not be positioned sensibly, so we ignore it entirely and always
        # draw the cube centered around the origin.  the small size ensures
        # it is always in front of any scene geometry.
        sx, sy, sz = 60, 60, 60
        x, y, z = - (sx // 2), - (sy // 2), - (sz // 2)
        X, Y, Z = x + sx, y + sy, z + sz

        vertexes = [
            (X, y, z, x, y, z, x, Y, z, X, Y, z),
            (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),
            (x, y, z, x, y, Z, x, Y, Z, x, Y, z),
            (X, y, Z, X, y, z, X, Y, z, X, Y, Z),
            (x, y, z, X, y, z, X, y, Z, x, y, Z),
            (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),
        ]

        tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
        mode = GL_QUADS

        # draw each face immediately, binding the appropriate texture group
        groups = [self.panorama[2], self.panorama[0], self.panorama[3],
                  self.panorama[1], self.panorama[5], self.panorama[4]]
        for verts, grp in zip(vertexes, groups):
            try:
                pyglet.graphics.draw(4, mode,
                                     ('v3f/static', verts),
                                     tex_coords,
                                     group=grp)
            except Exception:
                # if drawing fails for any reason, skip the face but continue
                pass

        # glCopyTexSubImage2D(GL_TEXTURE_2D, 0, 0, 0, 0, 0, 256, 256)
        # self.resizeCGL(self.WIDTH, self.HEIGHT, changeRes=False)

    def genWorld(self):
        # called each frame from updateScene or main menu; drain any ready cubes
        self.drawCounter += 1
        if self.drawCounter > self.genTime:
            self.drawCounter = 0
            # ensure generator thread is running
            self.worldGen.genChunk(self.player)
        # always integrate any finished blocks
        self.worldGen.process_loading()

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
            pyglet.graphics.draw(24, GL_QUADS, ('v3f/static', flatten(cube_vertices(blockByVec[0], 0.51))))
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
        self.stuffBatch = pyglet.graphics.Batch()
