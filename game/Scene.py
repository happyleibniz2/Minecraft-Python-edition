import gc
import math
import threading
import pyglet.image
from OpenGL.GLU import *
from pyglet.gl import *
from OpenGL.GL import *
from functions import *
from game.Lighting.Light import Light
from game.Lighting.SkyShader import SkyShader
from game.Particles import Particles
from game.blocks.DestroyBlock import DestroyBlock
from game.blocks.droppedBlock import droppedBlock
from game.entity.Inventory import Inventory
from game.entity.PlayerAvatar import PlayerAvatar
from game.entity.VisibilityWorker import VisibilityWorker
from game.world.Clouds import Clouds
from game.world.DayNightCycle import DayNightCycle
from game.world.worldGenerator import worldGenerator
from game.blocks.CubeHandler import CubeHandler
from game.graphics import DisposableBatch
import logging
import settings as game_settings


class Scene:
    NEAR_PLANE = 0.25

    def __init__(self):
        print("Init Scene class...")
        logging.debug("Init Scene class...")

        self.WIDTH, self.HEIGHT = WIDTH, HEIGHT

        self.gui = None
        self.sound = None
        self.blockSound = None
        self.deathScreen = None
        self.player = None
        self.stuffBatch = None
        self.lookingAt = "Nothing"

        self.texture, self.block, self.texture_dir, self.inventory_textures = {}, {}, {}, {}
        self.fov = FOV
        self.updateEvents = []
        self.entity = []
        self.mod_entity_types = {}
        self.mod_alpha_textures = set()
        self.spawn_egg_items = {}
        self.mod_loader = None
        self.show_hitboxes = False
        self._entity_occlusion = {}
        self._occlusion_cursor = 0
        self.skyColor = [128, 179, 255]
        self.panorama = {}
        self.water_overlay = None
        self.sun_texture = None
        self.moon_texture = None
        self.in_water = False

        self.resetScene()

    def resetScene(self):
        previous_light = getattr(self, "light", None)
        if previous_light is not None:
            previous_light.close()
        previous_sky_shader = getattr(self, "sky_shader", None)
        if previous_sky_shader is not None:
            previous_sky_shader.close()
        previous_clouds = getattr(self, "clouds", None)
        if previous_clouds is not None:
            previous_clouds.close()
        previous_worker = getattr(self, "_vis_worker", None)
        if previous_worker is not None:
            previous_worker.close()
        self.entity.clear()
        self._entity_occlusion.clear()
        self._occlusion_cursor = 0
        self.spawn_egg_items = {}
        self.allowEvents = {
            "movePlayer": True,
            "grabMouse": True,
            "keyboardAndMouse": True,
            "showCrosshair": True,
        }

        # Cached static sky geometry. Rebuilt lazily on first draw after a
        # world reset, because the star field depends on the fresh DayNightCycle.
        self._sky_vertex_list = None
        self._sky_t_values = ()
        self._star_vertex_list = None
        self._galaxy_vertex_list = None
        # Colour uploads are cached until the driving colour actually
        # changes; rebuilding the tuples every frame was pure Python churn.
        self._sky_color_key = None
        self._star_color_key = None
        self._galaxy_color_key = None

        self.clouds = Clouds(self)
        self.clouds.set_quality(game_settings.CLOUD_QUALITY)
        self.droppedBlock = droppedBlock(self)
        self.worldGen = worldGenerator(self, randint(434, 434343454))
        self.particles = Particles(self)
        self.destroy = DestroyBlock(self)
        self.playerAvatar = PlayerAvatar(self)
        self.light = Light(self)
        self.dayNight = DayNightCycle()
        self.sky_shader = SkyShader(self.light)
        self.sky_shader.day_night = self.dayNight

        self.drawCounter = 0
        self.genTime = 1
        self.startPlayerPos = [0, -9000, 0]

        # Asynchronous line-of-sight visibility: entities are path-traced on
        # a background core so the render thread never blocks on occlusion.
        self._vis_worker = VisibilityWorker(self)
        self._vis_worker.start()
        self._vis_tick = 0

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
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.1)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        glEnable(GL_FOG)
        glHint(GL_FOG_HINT, GL_DONT_CARE)
        glFogi(GL_FOG_MODE, GL_LINEAR)
        glEnable(GL_TEXTURE_2D)
        self.setAntialiasing(game_settings.ANTI_ALIASING)

        load_textures(self)
        self.loadPanoramaTextures()
        self.vertexList()

        if self.stuffBatch is not None and hasattr(self.stuffBatch, "dispose"):
            self.stuffBatch.dispose()
        self.stuffBatch = DisposableBatch()

        self.player.inventory = Inventory(self)
        self.cubes = CubeHandler(
            None,
            self.block,
            None,
            tuple({'leaves_taiga', 'leaves_oak', 'tall_grass', 'nocolor', 'sapling', 'torch', 'glass'}
                  | self.mod_alpha_textures),
            self
        )
        self.light.initialize()
        self.sky_shader.initialize()
        self.sky_shader.set_quality(game_settings.BLACKHOLE_QUALITY)

        self.set3d()

    def set2d(self):
        # UI quads and glyphs share Z=0. Keeping GL_LESS active lets the first
        # background pixel reject every later button/text pixel at equal depth.
        glDisable(GL_DEPTH_TEST)
        glDepthMask(GL_FALSE)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluOrtho2D(0, self.WIDTH, 0, self.HEIGHT)
        glMatrixMode(GL_MODELVIEW)
        glLoadIdentity()

    def set3d(self):
        glEnable(GL_DEPTH_TEST)
        glDepthMask(GL_TRUE)
        glDepthFunc(GL_LESS)
        glMatrixMode(GL_PROJECTION)
        glLoadIdentity()
        gluPerspective(self.fov, (self.WIDTH / self.HEIGHT), self.NEAR_PLANE, RENDER_DISTANCE)
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
            result = self.worldGen.genChunk(
                self.player,
                max_chunks_per_call=8 if initial_generation else 1,
                max_blocks_per_call=1024 if initial_generation else 256,
                time_budget=0 if initial_generation else 0.004,
            )
            return bool(result[0] or result[1])
        return False

    def updateScene(self, dt):
        generated_world = self.genWorld()

        self.dayNight.update(dt)
        self.clouds.set_weather(self.dayNight.weather_strength)
        self.light.set_weather(self.dayNight.weather_strength)
        self.light.set_sky_brightness(self.dayNight.sky_brightness)
        self.skyColor = [round(component * 255) for component in self.dayNight.sky_color]

        self.cubes.update_fluids(dt)
        if not generated_world:
            self.cubes.rebuild_dirty_chunks(self.player.position)
        self.in_water = roundPos(self.player.position) in self.cubes.fluids

        if self.in_water:
            fog = self.cubes.get_water_color(roundPos(self.player.position), fog=True)
            fog_color = (fog[0] / 255, fog[1] / 255, fog[2] / 255)
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(*fog_color, 1))
            glFogf(GL_FOG_START, 0)
            glFogf(GL_FOG_END, 24)
            self.light.set_environment(fog_color, 0, 24)
        else:
            fog = self.dayNight.fog_color
            glFogfv(GL_FOG_COLOR, (GLfloat * 4)(fog[0], fog[1], fog[2], 1))
            glFogf(GL_FOG_START, 10)
            glFogf(GL_FOG_END, 64)
            self.light.set_environment(fog, 10, 64)

        self.set3d()
        glClearColor(self.skyColor[0] / 255, self.skyColor[1] / 255, self.skyColor[2] / 255, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()

        self.player.update(dt)

        self.clouds.update(dt)
        self.droppedBlock.update(dt)

        self.update_entities(dt)

        if self.mod_loader is not None:
            self.mod_loader.post("client_tick", scene=self, dt=dt)

        self.light.update(dt)

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
        self.draw(dt)

        # UI must be last: drawing modal windows before the 3D pass allowed
        # the sun, moon and world to overwrite inventory/menu pixels.
        self.blockSound.pickUpAlreadyPlayed = False

        for i in self.updateEvents[:]:
            i()

    def draw(self, dt=0.0):
        self.set3d()
        glLoadIdentity()
        self.player.updateView()

        self.drawAtmosphereSky()
        self.drawCelestialSky(dt)
        self.drawBlackHoleSky(dt)
        self.clouds.render(self.player, self.dayNight)
        self.renderShadowMap()
        self.light.begin_render()
        try:
            self.cubes.render(self.player.position)

            for entity in self._visible_entities():
                entity.render(dt)

            # third-person avatar: the player looks at themselves
            if (self.player.cameraType != 1 and not self.player.is_spectator
                    and not self.player.playerDead):
                self.playerAvatar.render(dt)

            self.cubes.render_water()
            self.particles.drawParticles(dt)

            try:
                self.stuffBatch.draw()
            except pyglet.gl.lib.GLException:
                logging.exception("GL batch draw failed while rendering scene")
            if self.mod_loader is not None:
                self.mod_loader.post("render_world", scene=self, dt=dt)
        finally:
            self.light.end_render()
        # Reset, not dispose: reusing the same batch keeps Pyglet's shared
        # vertex domains (and their GPU buffers) alive between frames.
        self.stuffBatch.reset()

        if self.show_hitboxes:
            self.drawEntityHitboxes()

        self.set2d()
        self.player.renderHeldItem()
        if self.in_water:
            self.drawWaterOverlay()
        if getattr(self.player, "hurt_time", 0) > 0:
            self.drawDamageOverlay()

    def drawPaused(self):
        """Redraw the frozen world behind a menu without ticking simulation."""
        self.set3d()
        glClearColor(self.skyColor[0] / 255, self.skyColor[1] / 255, self.skyColor[2] / 255, 1)
        glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        glLoadIdentity()
        self.droppedBlock.render()
        self.draw(0.0)

    def setAntialiasing(self, enabled):
        """Toggle multisample anti-aliasing on the active framebuffer."""
        samples = int(glGetIntegerv(GL_SAMPLES))
        if enabled and samples > 0:
            glEnable(GL_MULTISAMPLE)
            return True
        glDisable(GL_MULTISAMPLE)
        return False

    def _ensure_sky_geometry(self):
        if self._sky_vertex_list is not None:
            return
        radius = 90.0
        rings, segments = 10, 40
        vertices, t_values = [], []
        for ring in range(rings):
            t0 = ring / rings
            t1 = (ring + 1) / rings
            a0 = t0 * math.pi / 2
            a1 = t1 * math.pi / 2
            y0, y1 = math.sin(a0) * radius, math.sin(a1) * radius
            r0, r1 = math.cos(a0) * radius, math.cos(a1) * radius
            for segment in range(segments):
                s0 = segment / segments * math.tau
                s1 = (segment + 1) / segments * math.tau
                c0, sn0 = math.cos(s0), math.sin(s0)
                c1, sn1 = math.cos(s1), math.sin(s1)
                # Lower triangle
                vertices += (c0 * r0, y0, sn0 * r0,
                             c0 * r1, y1, sn0 * r1,
                             c1 * r1, y1, sn1 * r1)
                t_values += (t0, t1, t1)
                # Upper triangle
                vertices += (c0 * r0, y0, sn0 * r0,
                             c1 * r1, y1, sn1 * r1,
                             c1 * r0, y0, sn1 * r0)
                t_values += (t0, t1, t0)
        count = len(vertices) // 3
        self._sky_t_values = t_values
        self._sky_vertex_list = pyglet.graphics.vertex_list(
            count,
            ('v3f/static', tuple(vertices)),
            ('c3f/dynamic', tuple([0.0] * (count * 3))),
        )

    def _ensure_star_geometry(self):
        if self._star_vertex_list is not None:
            return
        stars = self.dayNight.stars
        galaxy = self.dayNight.galaxy_stars
        radius = 80.0

        star_vs, star_cs = [], []
        for sx, sy, sz in stars:
            star_vs += (sx * radius, sy * radius, sz * radius)
            star_cs += (1.0, 1.0, 1.0, 1.0)
        self._star_vertex_list = pyglet.graphics.vertex_list(
            len(stars),
            ('v3f/static', tuple(star_vs)),
            ('c4f/dynamic', tuple(star_cs)),
        )

        galaxy_vs, galaxy_cs = [], []
        for sx, sy, sz, intensity, blue in galaxy:
            galaxy_vs += (sx * radius, sy * radius, sz * radius)
            galaxy_cs += (0.72 * intensity, 0.78 * intensity,
                          blue * intensity, intensity)
        self._galaxy_vertex_list = pyglet.graphics.vertex_list(
            len(galaxy),
            ('v3f/static', tuple(galaxy_vs)),
            ('c4f/dynamic', tuple(galaxy_cs)),
        )

    def drawCelestialSky(self, dt=0.0):
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
                self._ensure_star_geometry()
                brightness = self.dayNight.star_brightness
                star_count = len(self.dayNight.stars)
                # Rebuild the star/galaxy colour tuples only when the
                # brightness bucket changes, not every frame.
                star_key = round(brightness, 3)
                if star_key != self._star_color_key:
                    self._star_vertex_list.colors = tuple([brightness] * (star_count * 4))
                    self._star_color_key = star_key
                glPointSize(1.6)
                glPushMatrix()
                glTranslatef(px, py, pz)
                self._star_vertex_list.draw(GL_POINTS)

                galaxy_key = star_key
                if galaxy_key != self._galaxy_color_key:
                    galaxy_colors = []
                    for _, _, _, intensity, blue in self.dayNight.galaxy_stars:
                        a = brightness * intensity
                        galaxy_colors.extend((a * 0.72, a * 0.78, a * blue, a))
                    self._galaxy_vertex_list.colors = tuple(galaxy_colors)
                    self._galaxy_color_key = galaxy_key
                glPointSize(1.2)
                self._galaxy_vertex_list.draw(GL_POINTS)
                glPopMatrix()

            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glColor4f(1, 1, 1, 1)
            glPushMatrix()
            glTranslatef(px, py, pz)
            glRotatef(math.degrees(sun_angle) - 90, 1, 0, 0)

            if self.sun_texture is not None:
                self._drawCelestialQuad(self.sun_texture, radius, 8.0, (0, 0, 1, 1))

            if self.moon_texture is not None:
                phase = self.dayNight.moon_phase
                column, row = phase % 4, phase // 4
                u0, u1 = column / 4, (column + 1) / 4
                v1, v0 = 1 - row / 2, 1 - (row + 1) / 2
                self._drawCelestialQuad(self.moon_texture, -radius, 6.0, (u0, v0, u1, v1))

            glPopMatrix()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    def drawBlackHoleSky(self, dt=0.0):
        """Render the night sky with a physically-inspired black hole.

        The GLSL shader draws a fullscreen pass behind the world whenever the
        sky is dark enough for stars to be visible. It renders gravitational
        lensing of background stars, an accretion disk, and a dark event
        horizon region. When the shader is unavailable or the sky is bright
        the existing fixed-function star/moon rendering is used instead.
        """
        if self.dayNight.star_brightness <= 0.01:
            return
        try:
            self.sky_shader.render(self, dt)
        except Exception as error:
            logging.warning("black hole sky shader failed: %s", error)

    @staticmethod
    def _build_sky_colors(horizon, zenith, t_values):
        """Interpolated dome vertex colours (pure, so it can be cached/tested)."""
        hr, hg, hb = horizon
        dr, dg, db = zenith[0] - hr, zenith[1] - hg, zenith[2] - hb
        return tuple(
            component
            for t in t_values
            for component in (hr + dr * t, hg + dg * t, hb + db * t)
        )

    def drawAtmosphereSky(self):
        """Draw a smooth horizon-to-zenith atmospheric gradient dome.

        The geometry is precomputed once into a static vertex list and the
        vertex colours are only re-uploaded when the day/night colours
        change; the old path rebuilt ~2400 floats in Python every frame.
        """
        self._ensure_sky_geometry()
        horizon = self.dayNight.horizon_color
        zenith = self.dayNight.zenith_color
        key = (round(horizon[0], 3), round(horizon[1], 3), round(horizon[2], 3),
               round(zenith[0], 3), round(zenith[1], 3), round(zenith[2], 3))
        if key != self._sky_color_key:
            self._sky_vertex_list.colors = Scene._build_sky_colors(
                horizon, zenith, self._sky_t_values)
            self._sky_color_key = key

        px, py, pz = self.player.position
        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_CURRENT_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_FOG)
            glDisable(GL_DEPTH_TEST)
            glDisable(GL_BLEND)
            glDepthMask(GL_FALSE)
            glPushMatrix()
            glTranslatef(px, py, pz)
            self._sky_vertex_list.draw(GL_TRIANGLES)
            glPopMatrix()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    @staticmethod
    def _drawCelestialQuad(texture_group, height, size, uv):
        u0, v0, u1, v1 = uv
        texture_group.set_state_recursive()
        glBegin(GL_QUADS)
        glTexCoord2f(u0, v0); glVertex3f(-size, height, -size)
        glTexCoord2f(u1, v0); glVertex3f(size, height, -size)
        glTexCoord2f(u1, v1); glVertex3f(size, height, size)
        glTexCoord2f(u0, v1); glVertex3f(-size, height, size)
        glEnd()
        texture_group.unset_state_recursive()

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

    def drawDamageOverlay(self):
        """Brief red vignette-style flash while player hurt immunity is active."""
        alpha = min(0.32, self.player.hurt_time / 0.5 * 0.32)
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glColor4f(0.72, 0.02, 0.02, alpha)
            glBegin(GL_QUADS)
            glVertex2f(0, 0)
            glVertex2f(self.WIDTH, 0)
            glVertex2f(self.WIDTH, self.HEIGHT)
            glVertex2f(0, self.HEIGHT)
            glEnd()
        finally:
            glPopAttrib()

    def drawEntityHitboxes(self):
        """Minecraft F3+B-style entity AABBs and facing vectors."""
        glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_LINE_BIT | GL_DEPTH_BUFFER_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_BLEND)
            glLineWidth(2)
            for entity in self.entity:
                if getattr(entity, "is_dead", False):
                    continue
                x0, y0, z0, x1, y1, z1 = entity.get_hitbox()
                corners = (
                    (x0, y0, z0), (x1, y0, z0), (x1, y0, z1), (x0, y0, z1),
                    (x0, y1, z0), (x1, y1, z0), (x1, y1, z1), (x0, y1, z1),
                )
                edges = (
                    (0, 1), (1, 2), (2, 3), (3, 0),
                    (4, 5), (5, 6), (6, 7), (7, 4),
                    (0, 4), (1, 5), (2, 6), (3, 7),
                )
                glColor3f(1, 1, 1)
                glBegin(GL_LINES)
                for start, end in edges:
                    glVertex3f(*corners[start])
                    glVertex3f(*corners[end])
                glEnd()

                yaw = math.radians(entity.rotation[1])
                center_y = (y0 + y1) / 2
                glColor3f(0.1, 0.4, 1.0)
                glBegin(GL_LINES)
                glVertex3f(entity.position[0], center_y, entity.position[2])
                glVertex3f(entity.position[0] + math.sin(yaw), center_y,
                           entity.position[2] + math.cos(yaw))
                glEnd()
        finally:
            glPopAttrib()

    def renderShadowMap(self):
        """Render terrain, entities and block entities from the moving light."""
        if not self.light.should_update_shadow(self.player.position, self.dayNight.light_direction):
            return
        if not self.light.begin_shadow_pass(self.player.position, self.dayNight.light_direction):
            return
        world_batch = self.stuffBatch
        shadow_entity_batch = DisposableBatch()
        self.stuffBatch = shadow_entity_batch
        try:
            self.cubes.render_shadow(self.player.position, self.light.SHADOW_RADIUS * 2.0)

            entity_shadow_distance = (self.light.SHADOW_RADIUS * 2.0) ** 2
            for entity in self.entity:
                dx = entity.position[0] - self.player.position[0]
                dy = entity.position[1] - self.player.position[1]
                dz = entity.position[2] - self.player.position[2]
                if (not getattr(entity, "is_dead", False)
                        and dx * dx + dy * dy + dz * dz <= entity_shadow_distance):
                    entity.render(0)

            try:
                world_batch.draw()
                shadow_entity_batch.draw()
            except pyglet.gl.lib.GLException:
                logging.exception("Block entity shadow pass failed")

            if game_settings.PLAYER_SHADOWS and not self.player.is_spectator:
                self.drawPlayerShadowCaster()
        finally:
            self.stuffBatch = world_batch
            shadow_entity_batch.dispose()
            self.light.end_shadow_pass()

    def drawPlayerShadowCaster(self):
        """Simple player-sized depth proxy used only by the shadow map."""
        x, y, z = self.player.position
        x0, x1 = x - 0.3, x + 0.3
        y0 = y - getattr(self.player, "FEET_OFFSET", 1.62)
        y1 = y0 + getattr(self.player, "HEIGHT", 1.8)
        z0, z1 = z - 0.3, z + 0.3
        vertices = (
            (x0, y0, z0), (x1, y0, z0), (x1, y1, z0), (x0, y1, z0),
            (x0, y0, z1), (x1, y0, z1), (x1, y1, z1), (x0, y1, z1),
        )
        faces = (
            (0, 1, 2, 3), (5, 4, 7, 6), (4, 0, 3, 7),
            (1, 5, 6, 2), (4, 5, 1, 0), (3, 2, 6, 7),
        )
        glPushAttrib(GL_ENABLE_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_ALPHA_TEST)
            glBegin(GL_QUADS)
            for face in faces:
                for index in face:
                    glVertex3f(*vertices[index])
            glEnd()
        finally:
            glPopAttrib()

    def entity_types(self):
        """All spawnable entity types, keyed by entity id."""
        from game.entity.Chicken import Chicken
        from game.entity.Cow import Cow
        from game.entity.Creeper import Creeper
        from game.entity.Pig import Pig
        from game.entity.Sheep import Sheep
        from game.entity.Zombie import Zombie

        entities = {"chicken": Chicken, "cow": Cow, "creeper": Creeper,
                    "pig": Pig, "sheep": Sheep, "zombie": Zombie}
        entities.update(self.mod_entity_types)
        return entities

    def _prove_entity_occluded(self, camera, bounds):
        """Cull only when one committed opaque voxel covers the whole AABB."""
        center = tuple((bounds[index] + bounds[index + 3]) / 2 for index in range(3))
        blocker, _ = self.cubes.first_committed_solid_on_segment(camera, center)
        if blocker is None:
            return None
        return blocker if Scene._blocker_covers_bounds(camera, bounds, blocker) else None

    @staticmethod
    def _blocker_covers_bounds(camera, bounds, blocker):
        inset = 0.02
        blocker_bounds = (
            blocker[0] - 0.5 + inset, blocker[1] - 0.5 + inset,
            blocker[2] - 0.5 + inset, blocker[0] + 0.5 - inset,
            blocker[1] + 0.5 - inset, blocker[2] + 0.5 - inset,
        )
        corners = tuple(
            (x, y, z)
            for x in (bounds[0], bounds[3])
            for y in (bounds[1], bounds[4])
            for z in (bounds[2], bounds[5])
        )
        if all(Scene._segment_crosses_aabb(camera, corner, blocker_bounds)
               for corner in corners):
            return True
        return False

    # Entity activity tiers by horizontal distance from the player: inside
    # the simulation range mobs run their full AI/physics; beyond it they
    # freeze (saving the per-frame Python cost); past the despawn radius
    # they are removed, which is what lets distant crowds stop costing
    # frames entirely.
    ENTITY_SIMULATION_DISTANCE = 64.0
    ENTITY_DESPAWN_DISTANCE = 128.0

    def update_entities(self, dt):
        """Distance-tiered entity ticking: update, freeze or despawn."""
        px = self.player.position[0]
        pz = self.player.position[2]
        simulation_squared = self.ENTITY_SIMULATION_DISTANCE ** 2
        despawn_squared = self.ENTITY_DESPAWN_DISTANCE ** 2
        for entity in self.entity[:]:
            if getattr(entity, "is_dead", False):
                continue
            dx = entity.position[0] - px
            dz = entity.position[2] - pz
            distance_squared = dx * dx + dz * dz
            if distance_squared > despawn_squared:
                entity.die()  # removes itself from self.entity
            elif distance_squared <= simulation_squared:
                entity.update(dt)
            # else: frozen beyond the simulation range; it still renders
            # within the view distance but costs no per-frame AI work

    def _visible_entities(self):
        max_distance_squared = CHUNKS_RENDER_DISTANCE * CHUNKS_RENDER_DISTANCE
        candidates = []
        for entity in self.entity:
            if getattr(entity, "is_dead", False):
                continue
            dx = entity.position[0] - self.player.position[0]
            dy = entity.position[1] - self.player.position[1]
            dz = entity.position[2] - self.player.position[2]
            if dx * dx + dy * dy + dz * dz > max_distance_squared:
                continue
            bounds_getter = getattr(entity, "get_visibility_bounds", None)
            if bounds_getter is None:
                candidates.append((entity, None))
                continue
            bounds = tuple(bounds_getter())
            if self.cubes.frustum.cube_in_frustum(*bounds):
                candidates.append((entity, bounds))

        active = {id(entity) for entity, _ in candidates}
        self._entity_occlusion = {
            key: value for key, value in self._entity_occlusion.items() if key in active
        }
        if not candidates:
            self._occlusion_cursor = 0
            return []

        camera = (
            self.player.position[0],
            self.player.position[1] - self.player.shift - self.player.cameraShake[0],
            self.player.position[2],
        )

        # --- asynchronous path-traced visibility -------------------------
        # Hand the current view to the background worker and consume its
        # previous result when the camera has barely moved: the render
        # thread then does no occlusion work at all.
        worker = getattr(self, "_vis_worker", None)
        if worker is not None and worker.is_alive():
            items = [(id(entity), bounds) for entity, bounds in candidates
                     if bounds is not None]
            if worker.submit(self._vis_tick, camera, items):
                self._vis_tick += 1
            probed_camera = worker.results_camera
            if probed_camera is not None:
                moved_squared = sum(
                    (camera[index] - probed_camera[index]) ** 2
                    for index in range(3))
                if moved_squared <= 4.0:
                    hidden = worker.results
                    visible = [
                        entity for entity, bounds in candidates
                        if bounds is None or id(entity) not in hidden
                    ]
                    self._entity_occlusion.clear()
                    self._occlusion_cursor = 0
                    return visible

        # --- synchronous fallback (the pre-worker behaviour) ---------------
        check_count = min(4, len(candidates))
        scheduled = {
            (self._occlusion_cursor + offset) % len(candidates)
            for offset in range(check_count)
        }
        self._occlusion_cursor = (self._occlusion_cursor + check_count) % len(candidates)
        now = self.light.elapsed
        visible = []
        for index, (entity, bounds) in enumerate(candidates):
            if bounds is None or self._bounds_distance_squared(camera, bounds) < 64.0:
                self._entity_occlusion.pop(id(entity), None)
                visible.append(entity)
                continue

            key = id(entity)
            cached = self._entity_occlusion.get(key)
            if cached is not None and cached["state"] == "occluded":
                if (self._committed_blocker(cached["blocker"])
                        and self._blocker_covers_bounds(camera, bounds, cached["blocker"])):
                    cached["camera"] = camera
                    cached["bounds"] = bounds
                    continue
                self._entity_occlusion.pop(key, None)
                cached = None

            if index not in scheduled:
                visible.append(entity)
                continue
            if (cached is not None and cached["state"] == "visible"
                    and now < cached["next_check"]):
                visible.append(entity)
                continue

            blocker = self._prove_entity_occluded(camera, bounds)
            if blocker is None:
                self._entity_occlusion[key] = {
                    "state": "visible", "next_check": now + 0.1,
                }
                visible.append(entity)
                continue
            confirmations = 1
            if (cached is not None and cached.get("state") == "pending"
                    and cached.get("blocker") == blocker):
                confirmations = cached["confirmations"] + 1
            if confirmations >= 2:
                self._entity_occlusion[key] = {
                    "state": "occluded", "blocker": blocker,
                    "camera": camera, "bounds": bounds,
                }
                continue
            self._entity_occlusion[key] = {
                "state": "pending", "blocker": blocker,
                "camera": camera, "bounds": bounds,
                "confirmations": confirmations,
            }
            visible.append(entity)
        return visible

    def _committed_blocker(self, position):
        cube = self.cubes.cubes.get(position)
        if cube is None or cube.type != "solid":
            return False
        chunk = self.cubes.render_chunks.get(self.cubes._get_chunk_key(position))
        return chunk is not None and not chunk.dirty

    @staticmethod
    def _bounds_distance_squared(point, bounds):
        dx = max(bounds[0] - point[0], 0.0, point[0] - bounds[3])
        dy = max(bounds[1] - point[1], 0.0, point[1] - bounds[4])
        dz = max(bounds[2] - point[2], 0.0, point[2] - bounds[5])
        return dx * dx + dy * dy + dz * dz

    @staticmethod
    def _segment_crosses_aabb(start, end, bounds, clearance=0.1):
        delta = tuple(end[index] - start[index] for index in range(3))
        length = math.sqrt(sum(value * value for value in delta))
        if length <= 1e-9:
            return False
        entry, leave = 0.0, 1.0
        for axis in range(3):
            low, high = bounds[axis], bounds[axis + 3]
            if abs(delta[axis]) <= 1e-12:
                if start[axis] < low or start[axis] > high:
                    return False
                continue
            first = (low - start[axis]) / delta[axis]
            second = (high - start[axis]) / delta[axis]
            if first > second:
                first, second = second, first
            entry = max(entry, first)
            leave = min(leave, second)
            if entry > leave:
                return False
        return leave >= 0.0 and entry * length < length - clearance

    def hitTestEntity(self, origin, direction, max_distance=3.0):
        """Return the closest visible entity under the crosshair."""
        length = math.sqrt(sum(component * component for component in direction))
        if length <= 1e-9:
            return None
        ray = tuple(component / length for component in direction)

        block, _ = self.cubes.hitTest(origin, ray, dist=math.ceil(max_distance))
        block_distance = max_distance
        if block is not None:
            offset = tuple(block[i] - origin[i] for i in range(3))
            block_distance = max(0.0, sum(offset[i] * ray[i] for i in range(3)) - 0.5)

        closest = None
        closest_distance = block_distance
        for entity in self.entity[:]:
            if getattr(entity, "is_dead", False):
                continue
            bounds = entity.get_hitbox()
            margin = getattr(entity, "pick_radius", 0.0)
            expanded = (
                bounds[0] - margin, bounds[1] - margin, bounds[2] - margin,
                bounds[3] + margin, bounds[4] + margin, bounds[5] + margin,
            )
            distance = self._rayAabbDistance(origin, ray, expanded)
            if distance is not None and distance <= closest_distance:
                closest = entity
                closest_distance = distance
        return closest

    @staticmethod
    def _rayAabbDistance(origin, direction, bounds):
        minimum = bounds[:3]
        maximum = bounds[3:]
        near, far = 0.0, float("inf")
        for axis in range(3):
            if abs(direction[axis]) < 1e-9:
                if origin[axis] < minimum[axis] or origin[axis] > maximum[axis]:
                    return None
                continue
            inverse = 1.0 / direction[axis]
            first = (minimum[axis] - origin[axis]) * inverse
            second = (maximum[axis] - origin[axis]) * inverse
            if first > second:
                first, second = second, first
            near = max(near, first)
            far = min(far, second)
            if near > far:
                return None
        return near

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
        if self.mod_loader is not None:
            self.mod_loader.post("entity_spawned", scene=self, entity=entity,
                                 entity_id=label.lower())
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