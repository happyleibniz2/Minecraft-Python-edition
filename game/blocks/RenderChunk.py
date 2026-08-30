import pyglet
from OpenGL.GL import *
from functions import cube_vertices

class RenderChunk:
    FACE_DIRECTIONS = (
        (-1, 0, 0, 0), (1, 0, 0, 1),
        (0, -1, 0, 2), (0, 1, 0, 3),
        (0, 0, -1, 4), (0, 0, 1, 5),
    )

    def __init__(self, cx, cy, cz, size, gl):
        self.cx, self.cy, self.cz = cx, cy, cz
        self.size = size  # (wx, wy, wz) in blocks
        self.gl = gl
        self.cubes = {}          # world pos -> Cube
        self.batch = pyglet.graphics.Batch()
        self.cutout_batch = pyglet.graphics.Batch()
        self.water_batch = pyglet.graphics.Batch()
        self.overlay_batch = pyglet.graphics.Batch()
        self.dirty = True
        self.vertex_count = 0

    def add_cube(self, pos, cube):
        self.cubes[pos] = cube
        self.dirty = True

    def remove_cube(self, pos):
        if pos in self.cubes:
            del self.cubes[pos]
            self.dirty = True

    def rebuild(self):
        """Rebuild chunk batch from cubes."""
        self.batch = pyglet.graphics.Batch()
        self.cutout_batch = pyglet.graphics.Batch()
        self.water_batch = pyglet.graphics.Batch()
        self.overlay_batch = pyglet.graphics.Batch()
        global_cubes = self.gl.cubes.cubes
        handler = self.gl.cubes  # to get color constants

        # We'll batch faces per cube
        for pos, cube in self.cubes.items():
            if cube.name == "torch":
                self._add_torch(cube, handler)
                continue
            if cube.name == "tall_grass":
                self._add_cross_plant(cube, handler)
                continue
            x, y, z = pos
            vertices = None
            for dx, dy, dz, fi in self.FACE_DIRECTIONS:
                neighbour = (x+dx, y+dy, z+dz)
                neighbour_cube = global_cubes.get(neighbour)
                if not handler.should_render_face(cube, neighbour_cube, fi):
                    continue
                if cube.name == "water":
                    face_vertices = handler.get_face_vertices(cube, fi)
                else:
                    if vertices is None:
                        vertices = cube_vertices(pos)
                    face_vertices = vertices[fi]
                self._add_face(cube, fi, handler, face_vertices)

        self.dirty = False

    def _add_face(self, cube, face_index, handler, face_vertices):
        """Add a single face quad to the batch."""
        tex_group = handler.get_face_texture(cube, face_index)

        if cube.name == "water":
            clr = handler.get_water_face_color(cube.p, face_index)
        else:
            if face_index == 3:   # top
                clr = handler.top_color
                shade = 1.0
            elif face_index == 2: # bottom
                clr = handler.bottom_color
                shade = 0.5
            elif face_index in (0, 4):  # left or back
                clr = handler.ns_color
                shade = 0.8
            else:  # right or front
                clr = handler.ew_color
                shade = 0.6

            tinted = handler.get_block_face_color(cube, face_index, shade)
            if tinted is not None:
                clr = tinted

        tex_coords = (('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
                      if cube.name == "water"
                      else handler.get_light_coordinates(face_vertices, cube))
        if cube.name == "water":
            batch = self.water_batch
        elif cube.type == "alpha":
            batch = self.cutout_batch
        else:
            batch = self.batch
        attributes = [('v3f', face_vertices), tex_coords, clr]
        sway = handler.get_sway_attribute(face_vertices, cube)
        if sway is not None:
            attributes.append(sway)
        batch.add(4, GL_QUADS, tex_group, *attributes)

        if cube.name == "water":
            return

        # 1.20.1 grass draws a tinted grayscale overlay on top of the dirt side
        overlay = handler.get_grass_overlay(cube, face_index, shade)
        if overlay is not None:
            overlay_group, overlay_color = overlay
            attributes = [
                ('v3f', face_vertices),
                handler.get_light_coordinates(face_vertices, cube),
                overlay_color,
            ]
            sway = handler.get_sway_attribute(face_vertices, cube)
            if sway is not None:
                attributes.append(sway)
            self.overlay_batch.add(4, GL_QUADS, overlay_group, *attributes)

    def _add_torch(self, cube, handler):
        """Render a standing torch as two crossed transparent planes."""
        x, y, z = cube.p
        bottom = y - 0.5
        top = bottom + 0.625
        half_width = 0.32
        quads = (
            (x - half_width, bottom, z - half_width,
             x + half_width, bottom, z + half_width,
             x + half_width, top, z + half_width,
             x - half_width, top, z - half_width),
            (x - half_width, bottom, z + half_width,
             x + half_width, bottom, z - half_width,
             x + half_width, top, z - half_width,
             x - half_width, top, z + half_width),
        )
        texture = handler.get_face_texture(cube, 3)
        for vertices in quads:
            self.cutout_batch.add(4, GL_QUADS, texture,
                                  ('v3f', vertices),
                                  handler.get_light_coordinates(vertices, cube),
                                  handler.top_color)

    def _add_cross_plant(self, cube, handler):
        """Render Minecraft short grass as two crossed full-height planes."""
        x, y, z = cube.p
        bottom, top = y - 0.5, y + 0.5
        half = 0.5
        quads = (
            (x - half, bottom, z - half, x + half, bottom, z + half,
             x + half, top, z + half, x - half, top, z - half),
            (x - half, bottom, z + half, x + half, bottom, z - half,
             x + half, top, z - half, x - half, top, z + half),
        )
        texture = handler.get_face_texture(cube, 3)
        color = handler.get_block_face_color(cube, 3, 1.0) or handler.top_color
        for vertices in quads:
            attributes = [
                ('v3f', vertices),
                handler.get_light_coordinates(vertices, cube),
                color,
            ]
            sway = handler.get_sway_attribute(vertices, cube)
            if sway is not None:
                attributes.append(sway)
            self.cutout_batch.add(4, GL_QUADS, texture, *attributes)

    def render_opaque(self):
        if not self.dirty:
            self.batch.draw()

    def render_cutout(self):
        if not self.dirty:
            self.cutout_batch.draw()

    def render_shadow(self):
        if not self.dirty:
            self.batch.draw()
            self.cutout_batch.draw()

    def render_overlay(self):
        if not self.dirty:
            self.overlay_batch.draw()

    def render_water(self):
        if not self.dirty:
            self.water_batch.draw()
