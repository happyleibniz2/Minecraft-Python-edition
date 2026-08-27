import gc
import threading
import pyglet.image
from OpenGL.GLU import *
from pyglet.gl import *
from OpenGL.GL import *
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
import logging


class Scene:
    def __init__(self):
        print("Init Scene class...")
        logging.debug("Init Scene class...")

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
        panorama_path = ""
        panorama_file = os.path.join("assets", "Minecraft", "panorama.txt")
        if os.path.exists(panorama_file):
            with open(panorama_file, "r", encoding="utf-8") as panorama_handle:
                panorama_path = panorama_handle.read().strip().rstrip("/\\")
        if not panorama_path:
            panorama_path = os.path.join("assets", "Minecraft", "textures", "gui", "title", "background", "120x")
        panorama_path = panorama_path if os.path.isabs(panorama_path) else os.path.join(os.getcwd(), panorama_path)

        if not os.path.isdir(panorama_path):
            raise FileNotFoundError(f"Panorama directory not found: {panorama_path}")

        for e, i in enumerate(sorted(os.listdir(panorama_path))):
            image_path = os.path.join(panorama_path, i)
            if not os.path.isfile(image_path):
                continue
            self.panorama[e] = pyglet.graphics.TextureGroup(pyglet.image.load(image_path).get_texture())
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

    def vertexList(self):
        x, y, w, h = self.WIDTH / 2, self.HEIGHT / 2, self.WIDTH, self.HEIGHT
        self.reticle = pyglet.graphics.vertex_list(
            4,
            ('v2f', (x - 10, y, x + 10, y, x, y - 10, x, y + 10)),
            ('c3f', (0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0))
        )

    def initScene(self):
        print("Init OpenGL scene...")
        logging.debug("initializing OpenGL Renderer")
        glClearColor(0.5, 0.7, 1, 1)
        glClearDepth(1.0)
        glEnable(GL_DEPTH_TEST)
        glDepthFunc(GL_LESS)
        glShadeModel(GL_SMOOTH)
        glDepthFunc(GL_LEQUAL)
        glAlphaFunc(GL_GEQUAL, 1)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_FOG)
        glHint(GL_FOG_HINT, GL_DONT_CARE)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glEnable(GL_TEXTURE_2D)

        load_textures(self)
        self.loadPanoramaTextures()
        self.vertexList()

        self.stuffBatch = pyglet.graphics.Batch()

        self.player.inventory = Inventory(self)
        self.cubes = CubeHandler(
            None,
            self.block,
            None,
            ('leaves_taiga', 'leaves_oak', 'tall_grass', 'nocolor', 'sapling'),
            self
        )

        self.zombie = Zombie(self)
        self.zombie.position = [0, 100, 0]
        self.entity.append(self.zombie)

        self.set3d()

    def set2d(self):
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluOrtho2D(0, self.WIDTH, 0, self.HEIGHT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def set3d(self):
        glMatrixMode(GL_PROJECTION)
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
        """Draw the panorama using immediate mode."""
        if len(self.panorama) < 6:
            print("Warning: Not all panorama textures loaded.")
            return

        pp = self.player.position
        sx, sy, sz = 60, 60, 60
        x, y, z = pp[0] - (sx // 2), -(sy // 2), pp[2] - (sz // 2)
        X, Y, Z = x + sx, y + sy, z + sz

        vertexes = [
            (X, y, z, x, y, z, x, Y, z, X, Y, z),
            (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),
            (x, y, z, x, y, Z, x, Y, Z, x, Y, z),
            (X, y, Z, X, y, z, X, Y, z, X, Y, Z),
            (x, y, z, X, y, z, X, y, Z, x, y, Z),
            (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),
        ]

        for i, tex_group in enumerate(self.panorama.values()):
            tex_id = tex_group.texture.id
            glBindTexture(GL_TEXTURE_2D, tex_id)
            glBegin(GL_QUADS)
            v = vertexes[i]
            glTexCoord2f(0, 0); glVertex3f(v[0], v[1], v[2])
            glTexCoord2f(1, 0); glVertex3f(v[3], v[4], v[5])
            glTexCoord2f(1, 1); glVertex3f(v[6], v[7], v[8])
            glTexCoord2f(0, 1); glVertex3f(v[9], v[10], v[11])
            glEnd()

    def genWorld(self):
        self.drawCounter += 1
        if self.drawCounter > self.genTime:
            self.drawCounter = 0
            self.worldGen.genChunk(self.player, max_chunks_per_call=8, max_blocks_per_call=256)

    def updateScene(self, dt):
        self.genWorld()

        self.cubes.rebuild_dirty_chunks(self.player.position)

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

        self.player.update(dt)

        self.clouds.update(dt)
        self.droppedBlock.update(dt)

        for i in self.entity:
            i.update(dt)

        self.particles.drawParticles(dt)
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

        self.set2d()
        self.blockSound.pickUpAlreadyPlayed = False

        for i in self.updateEvents:
            i()

        self.draw(dt)

    def draw(self, dt=0.0):
        self.set3d()
        glLoadIdentity()
        self.player.updateView()

        self.cubes.render(self.player.position)

        for i in self.entity:
            i.render(dt)

        self.particles.drawParticles(dt)

        try:
            self.stuffBatch.draw()
        except pyglet.gl.lib.GLException:
            logging.exception("GL batch draw failed while rendering scene")
        self.stuffBatch = pyglet.graphics.Batch()

        self.set2d()

    def spawn_zombie(self):
        """Spawn a zombie near the player (slightly above)."""
        import random
        from game.entity.Zombie import Zombie

        if self.player is None:
            print("No player to spawn near.")
            return

        px, py, pz = self.player.position
        dx = random.randint(-4, 4)
        dz = random.randint(-4, 4)
        spawn_pos = [px + dx, py + 2, pz + dz]

        zombie = Zombie(self)
        zombie.position = spawn_pos
        zombie.rotation[1] = random.randint(0, 360)
        self.entity.append(zombie)
        print(f"Zombie spawned at {spawn_pos}")