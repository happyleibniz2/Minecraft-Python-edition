import time

from OpenGL.GL import *
from functions import cube_vertices
from game.graphics import DisposableBatch

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
        self.batch = DisposableBatch()
        self.cutout_batch = DisposableBatch()
        self.water_batch = DisposableBatch()
        self.overlay_batch = DisposableBatch()
        self.dirty = True
        self.vertex_count = 0
        self.revision = 0
        self._rebuild_items = None
        self._rebuild_index = 0
        self._rebuild_revision = 0
        self.rebuild_restarts = 0
        self._build_batches = None
        self._builders = None

    def add_cube(self, pos, cube):
        self.cubes[pos] = cube
        self.mark_dirty()

    def remove_cube(self, pos):
        if pos in self.cubes:
            del self.cubes[pos]
            self.mark_dirty()

    def mark_dirty(self):
        self.revision += 1
        self.dirty = True

    def rebuild(self):
        """Synchronously rebuild this chunk, primarily for loading/tests."""
        self._start_rebuild()
        while not self.rebuild_step(max(1, len(self._rebuild_items)), time_budget=0):
            pass

    def rebuild_step(self, cube_budget=256, time_budget=0):
        """Advance meshing without monopolizing an entire render frame."""
        if (self._rebuild_items is not None
                and self.revision != self._rebuild_revision):
            self.rebuild_restarts += 1
            self._rebuild_items = None
            self._build_batches = None
            self._builders = None
        if self._rebuild_items is None:
            self._start_rebuild()

        end = min(self._rebuild_index + cube_budget, len(self._rebuild_items))
        global_cubes = self.gl.cubes.cubes
        handler = self.gl.cubes
        deadline = time.perf_counter() + time_budget if time_budget > 0 else None

        start = self._rebuild_index
        actual_end = start
        for index in range(start, end):
            pos, cube = self._rebuild_items[index]
            if cube.name == "torch":
                self._add_torch(cube, handler)
            elif cube.name == "tall_grass":
                self._add_cross_plant(cube, handler)
            else:
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
            actual_end = index + 1
            if (deadline is not None and (actual_end - start) % 32 == 0
                    and time.perf_counter() >= deadline):
                break
        self._rebuild_index = actual_end

        if actual_end < len(self._rebuild_items):
            return False

        if self.revision != self._rebuild_revision:
            self.rebuild_restarts += 1
            # Keep the last valid GPU batches when the snapshot changes during
            # meshing. A fresh rebuild starts on the next frame.
            self._rebuild_items = None
            self._build_batches = None
            self._builders = None
            return True

        self._flush_builders()
        previous_batches = (
            self.batch, self.cutout_batch, self.water_batch, self.overlay_batch,
        )
        self.batch, self.cutout_batch, self.water_batch, self.overlay_batch = self._build_batches
        self.dirty = False
        self.rebuild_restarts = 0
        self._rebuild_items = None
        self._build_batches = None
        self._builders = None
        for batch in previous_batches:
            batch.dispose()
        return True

    def _start_rebuild(self):
        self._rebuild_items = tuple(self.cubes.items())
        self._rebuild_index = 0
        self._rebuild_revision = self.revision
        self._build_batches = tuple(DisposableBatch() for _ in range(4))
        self._builders = {}

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
            batch = self._build_batches[2]
        elif cube.type == "alpha":
            batch = self._build_batches[1]
        else:
            batch = self._build_batches[0]
        sway = handler.get_sway_attribute(face_vertices, cube)
        self._queue_quad(batch, tex_group, face_vertices, tex_coords, clr, sway)

        if cube.name == "water":
            return

        # 1.20.1 grass draws a tinted grayscale overlay on top of the dirt side
        overlay = handler.get_grass_overlay(cube, face_index, shade)
        if overlay is not None:
            overlay_group, overlay_color = overlay
            sway = handler.get_sway_attribute(face_vertices, cube)
            self._queue_quad(
                self._build_batches[3], overlay_group, face_vertices,
                handler.get_light_coordinates(face_vertices, cube),
                overlay_color, sway,
            )

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
            self._queue_quad(
                self._build_batches[1], texture, vertices,
                handler.get_light_coordinates(vertices, cube), handler.top_color,
            )

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
            sway = handler.get_sway_attribute(vertices, cube)
            self._queue_quad(
                self._build_batches[1], texture, vertices,
                handler.get_light_coordinates(vertices, cube), color, sway,
            )

    def _queue_quad(self, batch, texture, vertices, tex_coords, color, sway=None):
        """Aggregate equal render state into one large static vertex list."""
        sway_format = sway[0] if sway is not None else None
        key = (batch, texture, tex_coords[0], color[0], sway_format)
        builder = self._builders.get(key)
        if builder is None:
            builder = self._builders[key] = {
                "batch": batch,
                "texture": texture,
                "vertices": [],
                "tex_format": tex_coords[0],
                "tex_coords": [],
                "color_format": color[0],
                "colors": [],
                "sway_format": sway_format,
                "sway": [],
            }
        builder["vertices"].extend(vertices)
        builder["tex_coords"].extend(tex_coords[1])
        builder["colors"].extend(color[1])
        if sway is not None:
            builder["sway"].extend(sway[1])

    def _flush_builders(self):
        self.vertex_count = 0
        for builder in self._builders.values():
            count = len(builder["vertices"]) // 3
            attributes = [
                ('v3f/static', tuple(builder["vertices"])),
                (builder["tex_format"] + '/static', tuple(builder["tex_coords"])),
                (builder["color_format"] + '/static', tuple(builder["colors"])),
            ]
            if builder["sway_format"] is not None:
                # Pyglet 1.5 duplicates static generic attributes internally;
                # keep this small shader-only array in its dynamic VBO.
                attributes.append((builder["sway_format"], tuple(builder["sway"])))
            builder["batch"].add(count, GL_QUADS, builder["texture"], *attributes)
            self.vertex_count += count

    def render_opaque(self):
        self.batch.draw()

    def render_cutout(self):
        self.cutout_batch.draw()

    def render_shadow(self):
        self.batch.draw()
        self.cutout_batch.draw()

    def render_overlay(self):
        self.overlay_batch.draw()

    def render_water(self):
        self.water_batch.draw()
