import gc
import math
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
from game.world.DayNightCycle import DayNightCycle
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
        self.water_overlay = None
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
        self.dayNight = DayNightCycle()

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

        image_files = [
            i for i in sorted(os.listdir(panorama_path))
            if os.path.isfile(os.path.join(panorama_path, i)) and i.lower().endswith((".png", ".jpg", ".jpeg"))
        ]
        if len(image_files) < 6:
            raise ValueError(f"Panorama requires six images: {panorama_path}")

        panorama = {}
        for e, i in enumerate(image_files[:6]):
            image_path = os.path.join(panorama_path, i)
            panorama[e] = pyglet.graphics.TextureGroup(pyglet.image.load(image_path).get_texture())
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        self.panorama = panorama

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
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.1)
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
            ('leaves_taiga', 'leaves_oak', 'tall_grass', 'nocolor', 'sapling', 'torch'),
            self
        )
        self.light.initialize()

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
        """Draw a Minecraft-style cubemap centered on the camera."""
        if len(self.panorama) < 6:
            print("Warning: Not all panorama textures loaded.")
            return

        size = 1
        faces = (
            ((-size, -size, -size), ( size, -size, -size), ( size,  size, -size), (-size,  size, -size)),
            (( size, -size, -size), ( size, -size,  size), ( size,  size,  size), ( size,  size, -size)),
            (( size, -size,  size), (-size, -size,  size), (-size,  size,  size), ( size,  size,  size)),
            ((-size, -size,  size), (-size, -size, -size), (-size,  size, -size), (-size,  size,  size)),
            ((-size,  size, -size), ( size,  size, -size), ( size,  size,  size), (-size,  size,  size)),
            ((-size, -size,  size), ( size, -size,  size), ( size, -size, -size), (-size, -size, -size)),
        )
        tex_coords = ((0, 0), (1, 0), (1, 1), (0, 1))

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_TEXTURE_BIT | GL_CURRENT_BIT)
        try:
            glDisable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glDisable(GL_FOG)
            glDisable(GL_BLEND)
            glDisable(GL_CULL_FACE)
            glEnable(GL_TEXTURE_2D)
            glColor4f(1, 1, 1, 1)

            for i, vertices in enumerate(faces):
                glBindTexture(GL_TEXTURE_2D, self.panorama[i].texture.id)
                glBegin(GL_QUADS)
                for (u, v), (x, y, z) in zip(tex_coords, vertices):
                    glTexCoord2f(u, v)
                    glVertex3f(x, y, z)
                glEnd()
        finally:
            glPopAttrib()

    def genWorld(self):
        self.drawCounter += 1
        if self.drawCounter > self.genTime:
            self.drawCounter = 0
            initial_generation = self.genTime <= 1
            self.worldGen.genChunk(
                self.player,
                max_chunks_per_call=8 if initial_generation else 1,
                max_blocks_per_call=1024 if initial_generation else 256,
            )

    def updateScene(self, dt):
        self.genWorld()

        self.dayNight.update(dt)
        self.light.set_sky_brightness(self.dayNight.sky_brightness)
        self.skyColor = [round(component * 255) for component in self.dayNight.sky_color]

        self.cubes.update_fluids(dt)
        self.cubes.rebuild_dirty_chunks(self.player.position)
        self.in_water = roundPos(self.player.position) in self.cubes.fluids

        if self.in_water:
            fog = self.cubes.get_water_color(roundPos(self.player.position), fog=True)
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(fog[0] / 255, fog[1] / 255, fog[2] / 255, 1))
            glFogf(GL_FOG_START, 0)
            glFogf(GL_FOG_END, 24)
        else:
            fog = self.dayNight.fog_color
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(fog[0], fog[1], fog[2], 1))
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

        self.drawCelestialSky()
        self.light.begin_render()
        try:
            self.cubes.render(self.player.position)

            for i in self.entity:
                i.render(dt)

            self.cubes.render_water()
            self.particles.drawParticles(dt)

            try:
                self.stuffBatch.draw()
            except pyglet.gl.lib.GLException:
                logging.exception("GL batch draw failed while rendering scene")
        finally:
            self.light.end_render()
        self.stuffBatch = pyglet.graphics.Batch()

        self.set2d()
        if self.in_water:
            self.drawWaterOverlay()

    def drawCelestialSky(self):
        """Draw the moving sun, moon and night stars behind the world."""
        px, py, pz = self.player.position
        radius = 80
        sun_angle = self.dayNight.sun_angle

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_CURRENT_BIT | GL_POINT_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_FOG)
            glDisable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glEnable(GL_POINT_SMOOTH)

            if self.dayNight.star_brightness > 0:
                glPointSize(1.6)
                brightness = self.dayNight.star_brightness
                glColor4f(brightness, brightness, brightness, brightness)
                glBegin(GL_POINTS)
                for sx, sy, sz in self.dayNight.stars:
                    glVertex3f(px + sx * radius, py + sy * radius, pz + sz * radius)
                glEnd()

            sun_x = math.cos(sun_angle) * radius
            sun_y = math.sin(sun_angle) * radius
            glPointSize(30)
            glColor4f(1.0, 0.88, 0.42, 1.0)
            glBegin(GL_POINTS)
            glVertex3f(px + sun_x, py + sun_y, pz - radius * 0.25)
            glEnd()

            glPointSize(22)
            glColor4f(0.72, 0.78, 0.92, 1.0)
            glBegin(GL_POINTS)
            glVertex3f(px - sun_x, py - sun_y, pz + radius * 0.25)
            glEnd()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    def drawWaterOverlay(self):
        texture_group = getattr(self, "water_overlay", None)
        if texture_group is None:
            return
        color = self.cubes.get_water_color(roundPos(self.player.position))
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT | GL_DEPTH_BUFFER_BIT)
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            glColor4f(color[0] / 255, color[1] / 255, color[2] / 255, 0.45)
            texture_group.set_state_recursive()
            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(0, 0)
            glTexCoord2f(4, 0); glVertex2f(self.WIDTH, 0)
            glTexCoord2f(4, 3); glVertex2f(self.WIDTH, self.HEIGHT)
            glTexCoord2f(0, 3); glVertex2f(0, self.HEIGHT)
            glEnd()
            texture_group.unset_state_recursive()
        finally:
            glPopAttrib()

    def entity_types(self):
        """All spawnable entity types, keyed by entity id."""
        from game.entity.Cow import Cow
        from game.entity.Sheep import Sheep
        from game.entity.Zombie import Zombie

        return {"cow": Cow, "sheep": Sheep, "zombie": Zombie}

    def spawn_entity(self, factory, label, position=None):
        """Spawn an entity near the player, like Minecraft's spawn eggs."""
        import random

        if position is None:
            if self.player is None:
                print("No player to spawn near.")
                return None
            px, py, pz = self.player.position
            dx = random.randint(-4, 4)
            dz = random.randint(-4, 4)
            position = [px + dx, py + 2, pz + dz]

        entity = factory(self)
        entity.position = list(position)
        entity.rotation[1] = random.randint(0, 360)
        self.entity.append(entity)
        print(f"{label} spawned at {position}")
        return entity

    def spawn_entity_by_id(self, entity_id, position=None):
        """Spawn by entity id, used by spawn eggs."""
        factory = self.entity_types().get(entity_id)
        if factory is None:
            print(f"Unknown entity id: {entity_id}")
            return None
        return self.spawn_entity(factory, entity_id.capitalize(), position)

    def spawn_random_entity(self):
        """Spawn one random entity out of every loaded entity type."""
        import random

        types = self.entity_types()
        if not types:
            print("No entity types are loaded.")
            return None
        entity_id = random.choice(sorted(types))
        return self.spawn_entity_by_id(entity_id)

    def spawn_cow(self):
        from game.entity.Cow import Cow
        return self.spawn_entity(Cow, "Cow")

    def spawn_sheep(self):
        from game.entity.Sheep import Sheep
        return self.spawn_entity(Sheep, "Sheep")

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
