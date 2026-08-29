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
        self.water_batch = pyglet.graphics.Batch()
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
        self.water_batch = pyglet.graphics.Batch()
        global_cubes = self.gl.cubes.cubes
        handler = self.gl.cubes  # to get color constants

        # We'll batch faces per cube
        for pos, cube in self.cubes.items():
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

        batch = self.water_batch if cube.name == "water" else self.batch
        batch.add(4, GL_QUADS, tex_group,
                  ('v3f', face_vertices),
                  ('t2f', (0,0, 1,0, 1,1, 0,1)),
                  clr)

    def render_opaque(self):
        if not self.dirty:
            self.batch.draw()

    def render_water(self):
        if not self.dirty:
            self.water_batch.draw()
