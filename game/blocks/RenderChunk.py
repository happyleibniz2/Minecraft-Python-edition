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
        global_cubes = self.gl.cubes.cubes
        handler = self.gl.cubes  # to get color constants

        # We'll batch faces per cube
        for pos, cube in self.cubes.items():
            x, y, z = pos
            vertices = None
            for dx, dy, dz, fi in self.FACE_DIRECTIONS:
                neighbour = (x+dx, y+dy, z+dz)
                if neighbour not in global_cubes:
                    if vertices is None:
                        vertices = cube_vertices(pos)
                    self._add_face(cube, fi, handler, vertices[fi])
                else:
                    nb = global_cubes[neighbour]
                    if nb.type in ('alpha', 'blend'):
                        if vertices is None:
                            vertices = cube_vertices(pos)
                        self._add_face(cube, fi, handler, vertices[fi])

        self.dirty = False

    def _add_face(self, cube, face_index, handler, face_vertices):
        """Add a single face quad to the batch."""
        tex_group = cube.t[face_index]

        # Use appropriate color
        if face_index == 3:   # top
            clr = handler.top_color
        elif face_index == 2: # bottom
            clr = handler.bottom_color
        elif face_index in (0, 4):  # left or back
            clr = handler.ns_color
        else:  # right or front
            clr = handler.ew_color

        self.batch.add(4, GL_QUADS, tex_group,
                       ('v3f', face_vertices),
                       ('t2f', (0,0, 1,0, 1,1, 0,1)),
                       clr)

    def render(self):
        if not self.dirty:
            self.batch.draw()
