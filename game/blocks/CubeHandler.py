import math
from collections import deque

from OpenGL.GL import *
from functions import roundPos, cube_vertices, adjacent
from game.blocks.Cube import Cube
from game.blocks.RenderChunk import RenderChunk
from game.blocks.Water import FluidState, water_face_vertices
from game.Frustum import Frustum
from game.world.Biomes import Biomes, getBiomeByTemp
from game.world.BiomeColors import BiomeColorProvider, is_tinted
import settings  # for DISTANCE_CULLING and CHUNK_RENDER_DISTANCE


class CubeHandler:
    top_color = ('c3f', (1.0,) * 12)
    ns_color = ('c3f', (0.8,) * 12)
    ew_color = ('c3f', (0.6,) * 12)
    bottom_color = ('c3f', (0.5,) * 12)

    def __init__(self, batch, block, opaque, alpha_textures, gl):
        self.block = block
        self.alpha_textures = alpha_textures
        self.gl = gl

        self.cubes = {}          # world pos -> Cube
        self.collidable = {}     # solid cubes for collision
        self.fluids = {}
        self.fluid_queue = deque()
        self.fluid_pending = set()
        self.fluid_accumulator = 0.0
        self.water_tint_cache = {}
        self.biome_cache = {}
        self.visible_water_chunks = []
        self.biome_colors = BiomeColorProvider()
        self.block_tint_cache = {}

        # Render chunks
        self.render_chunks = {}
        # (cx, cz) -> set of cy. Replaces the linear dict scans in render /
        # rebuild_dirty_chunks / chunks_within_distance / render_shadow.
        self._chunks_by_column = {}
        self.RENDER_CHUNK_SIZE = (16, 8, 16)
        self.max_rebuilds_per_frame = 1
        self.rebuild_cube_budget = 256
        self.rebuild_time_budget = 0.004

        # Conservative AABB frustum culling.
        self.frustum = Frustum()

    def _get_chunk_key(self, pos):
        x, y, z = pos
        cx = x // self.RENDER_CHUNK_SIZE[0]
        cy = y // self.RENDER_CHUNK_SIZE[1]
        cz = z // self.RENDER_CHUNK_SIZE[2]
        return (cx, cy, cz)

    def _get_or_create_chunk(self, chunk_key):
        chunk = self.render_chunks.get(chunk_key)
        if chunk is not None:
            return chunk
        chunk = RenderChunk(
            chunk_key[0], chunk_key[1], chunk_key[2],
            self.RENDER_CHUNK_SIZE, self.gl,
        )
        self.render_chunks[chunk_key] = chunk
        column_key = (chunk_key[0], chunk_key[2])
        column = self._chunks_by_column.get(column_key)
        if column is None:
            self._chunks_by_column[column_key] = {chunk_key[1]}
        else:
            column.add(chunk_key[1])
        return chunk

    def _iter_chunks_near(self, center, radius):
        """Yield populated chunks whose column lies inside the radius box.

        Cost scales with the number of loaded chunks inside the box, not with
        the size of ``render_chunks``. The extra ``+1`` on each end provides a
        small safety margin so that chunks whose AABB grazes the radius but
        whose center sits just outside are not culled by the coarse filter.
        """
        sx, _, sz = self.RENDER_CHUNK_SIZE
        cx0 = int((center[0] - radius) // sx) - 1
        cx1 = int((center[0] + radius) // sx) + 2
        cz0 = int((center[2] - radius) // sz) - 1
        cz1 = int((center[2] + radius) // sz) + 2
        by_column = self._chunks_by_column
        render_chunks = self.render_chunks
        for cx in range(cx0, cx1):
            for cz in range(cz0, cz1):
                column = by_column.get((cx, cz))
                if not column:
                    continue
                for cy in column:
                    chunk = render_chunks.get((cx, cy, cz))
                    if chunk is not None:
                        yield chunk

    def hitTest(self, p, vec, dist=4, include_fluids=False):
        m = 8
        x, y, z = p
        dx, dy, dz = vec
        dx /= m
        dy /= m
        dz /= m
        prev = None
        for i in range(dist * m):
            key = roundPos((x, y, z))
            if key in self.cubes and (include_fluids or key not in self.fluids):
                return key, prev
            prev = key
            x, y, z = x + dx, y + dy, z + dz
        return None, None

    def first_committed_solid_on_segment(self, start, end, clearance=0.1):
        """Return the first rendered opaque voxel crossed by an exact DDA."""
        delta = tuple(end[index] - start[index] for index in range(3))
        length = sum(value * value for value in delta) ** 0.5
        if length <= 1e-9:
            return None, None
        stop_t = max(0.0, 1.0 - clearance / length)
        cell = [math.floor(start[index] + 0.5) for index in range(3)]
        end_cell = [math.floor(end[index] + 0.5) for index in range(3)]
        steps = [1 if value > 0 else -1 if value < 0 else 0 for value in delta]
        t_max = []
        t_delta = []
        for axis, value in enumerate(delta):
            if value > 0:
                boundary = cell[axis] + 0.5
                t_max.append((boundary - start[axis]) / value)
                t_delta.append(1.0 / value)
            elif value < 0:
                boundary = cell[axis] - 0.5
                t_max.append((boundary - start[axis]) / value)
                t_delta.append(-1.0 / value)
            else:
                t_max.append(float("inf"))
                t_delta.append(float("inf"))

        max_steps = sum(abs(end_cell[index] - cell[index]) for index in range(3)) + 3
        for _ in range(max_steps):
            crossing = min(t_max)
            if crossing >= stop_t:
                break
            for axis in range(3):
                if abs(t_max[axis] - crossing) <= 1e-10:
                    cell[axis] += steps[axis]
                    t_max[axis] += t_delta[axis]
            position = tuple(cell)
            cube = self.cubes.get(position)
            if cube is None or cube.type != "solid":
                continue
            chunk = self.render_chunks.get(self._get_chunk_key(position))
            if chunk is not None and not chunk.dirty:
                return position, crossing * length
        return None, None

    REPLACEABLE = ("water", "lava", "tall_grass")

    def add(self, p, t, now=False, fluid_level=0, fluid_source=None, fluid_falling=False):
        if t in ("torch", "tall_grass") and (p[0], p[1] - 1, p[2]) not in self.collidable:
            return False
        if p in self.cubes:
            if t == "water" and self.cubes[p].name == "water":
                source = fluid_level == 0 and not fluid_falling if fluid_source is None else fluid_source
                self._set_water_state(p, FluidState(fluid_level, source, fluid_falling))
                return True
            if self.cubes[p].name not in self.REPLACEABLE:
                return False
            self._clear_fluid(p)
        cube = self.cubes[p] = Cube(t, p, self.block[t],
                                    self.block_render_type(t, self.alpha_textures))

        if cube.name not in ('water', 'lava', 'torch', 'tall_grass'):
            self.collidable[p] = cube
        elif cube.name == "water":
            source = fluid_level == 0 and not fluid_falling if fluid_source is None else fluid_source
            self.fluids[p] = FluidState(max(0, min(7, fluid_level)), source, fluid_falling)

        chunk_key = self._get_chunk_key(p)
        self._get_or_create_chunk(chunk_key).add_cube(p, cube)

        self._mark_boundary_chunks_dirty(p, chunk_key)

        if t == "water" and now:
            self._schedule_fluid(p)
        if now:
            self._schedule_adjacent_water(p)
        if t == "torch" and getattr(self.gl, "light", None) is not None:
            self.gl.light.addLightSource(*p)
        mod_loader = getattr(self.gl, "mod_loader", None)
        if mod_loader is not None:
            mod_loader.post("block_added", scene=self.gl, position=p, block=cube)
        return True

    def remove(self, p):
        if p not in self.cubes:
            return
        if self.cubes[p].name == "bedrock":
            return
        was_water = p in self.fluids and self.cubes[p].name == "water"
        if p in self.fluids:
            self.fluids.pop(p)
        cube = self.cubes.pop(p)
        if p in self.collidable:
            del self.collidable[p]
        if cube.name == "torch" and getattr(self.gl, "light", None) is not None:
            self.gl.light.removeLightSource(*p)

        chunk_key = self._get_chunk_key(p)
        chunk = self.render_chunks.get(chunk_key)
        if chunk is not None:
            chunk.remove_cube(p)

        self._mark_boundary_chunks_dirty(p, chunk_key)
        if was_water or cube.name != "water":
            self._schedule_adjacent_water(p)
        mod_loader = getattr(self.gl, "mod_loader", None)
        if mod_loader is not None:
            mod_loader.post("block_removed", scene=self.gl, position=p, block=cube)

        # standing torches break when their supporting block disappears
        above = (p[0], p[1] + 1, p[2])
        above_cube = self.cubes.get(above)
        if above_cube is not None and above_cube.name in ("torch", "tall_grass") and p not in self.collidable:
            unsupported = above_cube.name
            self.remove(above)
            if unsupported == "torch":
                dropped = getattr(self.gl, "droppedBlock", None)
                if dropped is not None:
                    dropped.addBlock(above, "torch")

    def _clear_fluid(self, p):
        self.fluids.pop(p, None)
        self.cubes.pop(p, None)
        chunk = self.render_chunks.get(self._get_chunk_key(p))
        if chunk is not None:
            chunk.remove_cube(p)

    def place_water_source(self, p):
        if p in self.cubes and self.cubes[p].name != "water":
            return False
        state = FluidState(0, True, False)
        if p in self.cubes:
            self._set_water_state(p, state)
        else:
            self.add(p, "water", now=True, fluid_source=True)
        self._schedule_fluid(p)
        self._schedule_adjacent_water(p)
        return True

    def update_fluids(self, dt):
        if not self.fluid_queue:
            self.fluid_accumulator = 0
            return
        self.fluid_accumulator = min(self.fluid_accumulator + dt, 1.0)
        while self.fluid_accumulator >= 0.25:
            self.fluid_accumulator -= 0.25
            updates = min(len(self.fluid_queue), 128)
            for _ in range(updates):
                p = self.fluid_queue.popleft()
                self.fluid_pending.discard(p)
                self._update_water(p)

    def _update_water(self, p):
        state = self.fluids.get(p)
        if state is None or self.cubes.get(p, None) is None or self.cubes[p].name != "water":
            return

        if not state.source:
            incoming = self._incoming_water_state(p)
            if incoming is None:
                self.remove(p)
                return
            if incoming != state:
                self._set_water_state(p, incoming)
                state = incoming

        x, y, z = p
        below = (x, y - 1, z)
        can_fall = self._can_water_enter(below)
        if can_fall:
            self._flow_water_into(below, FluidState(state.level, False, True))

        if can_fall:
            return

        if state.source or state.falling or state.level < 7:
            next_level = 1 if state.source or state.falling else state.level + 1
            if next_level <= 7:
                for dx, dz in self._preferred_flow_directions(p):
                    self._flow_water_into((x + dx, y, z + dz), FluidState(next_level, False, False))

    def _preferred_flow_directions(self, p, max_distance=4):
        weights = {}
        for direction in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            dx, dz = direction
            target = (p[0] + dx, p[1], p[2] + dz)
            if not self._can_water_enter(target):
                continue
            weights[direction] = self._flow_weight(target, max_distance)
        if not weights:
            return ()
        lowest = min(weights.values())
        return tuple(direction for direction, weight in weights.items() if weight == lowest)

    def _flow_weight(self, start, max_distance):
        if self._can_water_enter((start[0], start[1] - 1, start[2])):
            return 0

        visited = {start}
        frontier = [start]
        for distance in range(1, max_distance + 1):
            next_frontier = []
            for position in frontier:
                for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    neighbour = (position[0] + dx, position[1], position[2] + dz)
                    if neighbour in visited or not self._can_water_enter(neighbour):
                        continue
                    if self._can_water_enter((neighbour[0], neighbour[1] - 1, neighbour[2])):
                        return distance
                    visited.add(neighbour)
                    next_frontier.append(neighbour)
            frontier = next_frontier
            if not frontier:
                break
        return 1000

    def _incoming_water_state(self, p):
        x, y, z = p
        above = self.fluids.get((x, y + 1, z))
        if above is not None:
            return FluidState(above.level, False, True)

        neighbours = [
            self.fluids.get((x - 1, y, z)), self.fluids.get((x + 1, y, z)),
            self.fluids.get((x, y, z - 1)), self.fluids.get((x, y, z + 1)),
        ]
        source_count = sum(1 for state in neighbours if state is not None and state.source)
        below = (x, y - 1, z)
        supported = below in self.collidable or bool(self.fluids.get(below, None) and self.fluids[below].source)
        if source_count >= 2 and supported:
            return FluidState(0, True, False)

        levels = []
        for state in neighbours:
            if state is None:
                continue
            if state.source or state.falling:
                levels.append(1)
            elif state.level < 7:
                levels.append(state.level + 1)
        if not levels:
            return None
        return FluidState(min(levels), False, False)

    def _flow_water_into(self, p, state):
        if p in self.cubes and self.cubes[p].name != "water":
            return
        existing = self.fluids.get(p)
        if existing is not None:
            if existing.source or (existing.falling and not state.falling):
                return
            if existing.falling == state.falling and existing.level <= state.level:
                return
            self._set_water_state(p, state)
        else:
            self.add(
                p,
                "water",
                fluid_level=state.level,
                fluid_source=state.source,
                fluid_falling=state.falling,
            )
        self._schedule_fluid(p)
        self._schedule_adjacent_water(p)

    def _can_water_enter(self, p):
        return p not in self.cubes or self.cubes[p].name == "water"

    def _set_water_state(self, p, state):
        state = FluidState(max(0, min(7, state.level)), state.source, state.falling)
        if self.fluids.get(p) == state:
            return
        self.fluids[p] = state
        self._mark_block_dirty(p)
        self._schedule_fluid(p)

    def _schedule_fluid(self, p):
        if p not in self.fluid_pending:
            self.fluid_pending.add(p)
            self.fluid_queue.append(p)

    def _schedule_adjacent_water(self, p):
        for neighbour in adjacent(*p):
            if neighbour in self.fluids and self.cubes[neighbour].name == "water":
                self._schedule_fluid(neighbour)

    def _mark_block_dirty(self, p):
        positions = (p,) + tuple(adjacent(*p))
        for position in positions:
            chunk = self.render_chunks.get(self._get_chunk_key(position))
            if chunk is not None:
                chunk.mark_dirty()

    def get_water_height(self, p):
        state = self.fluids.get(p)
        if state is None:
            return 0
        x, y, z = p
        if state.falling or (x, y + 1, z) in self.fluids:
            return 1.0
        return max(1 / 9, (8 - state.level) / 9)

    def should_render_face(self, cube, neighbour, face_index):
        if neighbour is None:
            return True
        if cube.name != "water":
            if cube.type in ("alpha", "blend") and neighbour.name == cube.name:
                return False
            return neighbour.type in ('alpha', 'blend')
        if neighbour.name != "water":
            return neighbour.type in ('alpha', 'blend')
        if face_index in (2, 3):
            return False
        return self.get_water_height(neighbour.p) < self.get_water_height(cube.p)

    @staticmethod
    def block_render_type(name, alpha_textures):
        if name in alpha_textures:
            return "alpha"
        if name in ("water", "lava"):
            return "blend"
        return "solid"

    def get_face_vertices(self, cube, face_index):
        if cube.name != "water":
            return cube_vertices(cube.p)[face_index]
        height = self.get_water_height(cube.p)
        lower_height = 0
        dx, dy, dz, _ = RenderChunk.FACE_DIRECTIONS[face_index]
        neighbour = (cube.p[0] + dx, cube.p[1] + dy, cube.p[2] + dz)
        if face_index not in (2, 3) and neighbour in self.fluids:
            lower_height = min(height, self.get_water_height(neighbour))
        return water_face_vertices(cube.p, face_index, height, lower_height)

    def get_face_texture(self, cube, face_index):
        if cube.name == "water" and face_index == 3:
            state = self.fluids.get(cube.p)
            if state is not None and not state.source and not state.falling:
                return self.gl.texture["water_flow"]
        return cube.t[face_index]

    def get_light_coordinates(self, face_vertices, cube=None):
        light = getattr(self.gl, "light", None)
        if light is None:
            return 't2f', (0, 0, 1, 0, 1, 1, 0, 1)
        return light.texture_coordinates(face_vertices, cube)

    def get_sway_attribute(self, face_vertices, cube):
        light = getattr(self.gl, "light", None)
        if light is None:
            return None
        return light.sway_attribute(face_vertices, cube)

    def get_water_color(self, p, fog=False):
        x, _, z = p
        seed = getattr(self.gl.worldGen, "seed", None)
        cache = self.water_tint_cache if not fog else None
        key = (seed, x, z)
        if cache is not None and key in cache:
            return cache[key]

        colors = []
        radius = 1 if not fog else 0
        for offset_x in range(-radius, radius + 1):
            for offset_z in range(-radius, radius + 1):
                biome = self._get_biome(x + offset_x, z + offset_z)
                colors.append(biome.getWaterFogColor() if fog else biome.getWaterColor())
        color = tuple(sum(sample[i] for sample in colors) // len(colors) for i in range(3))
        if cache is not None:
            cache[key] = color
        return color

    def _get_biome(self, x, z):
        seed = getattr(self.gl.worldGen, "seed", None)
        key = (seed, x, z)
        if key not in self.biome_cache:
            sample_biome = getattr(self.gl.worldGen, "sample_biome", None)
            if sample_biome is not None:
                biome_name = sample_biome(x, z)
            else:
                biome_name = getBiomeByTemp(self.gl.worldGen.perlinBiomes(x, z) * 3)
            self.biome_cache[key] = Biomes(biome_name)
        return self.biome_cache[key]

    # Minecraft tints only the grass top face; sides and bottom keep dirt tones.
    TINTED_FACES = {
        "grass": (3,),
    }

    def get_block_face_color(self, cube, face_index, shade):
        """Biome-tinted vertex colour for a face, or ``None`` when untinted."""
        if not is_tinted(cube.name):
            return None

        tinted_faces = self.TINTED_FACES.get(cube.name)
        if tinted_faces is not None and face_index not in tinted_faces:
            return None

        x, _, z = cube.p
        key = (cube.name, x, z)
        multiplier = self.block_tint_cache.get(key)
        if multiplier is None:
            biome = self._get_biome(x, z).biome
            multiplier = self.biome_colors.block_multiplier(cube.name, biome)
            if multiplier is None:
                return None
            self.block_tint_cache[key] = multiplier

        rgb = tuple(component * shade for component in multiplier)
        return 'c3f', rgb * 4

    def get_grass_overlay(self, cube, face_index, shade):
        """Tinted side overlay for the 1.20.1 grass block, or ``None``."""
        if cube.name != "grass" or face_index in (2, 3):
            return None

        overlay = getattr(self.gl, "grass_side_overlay", None)
        if overlay is None:
            return None

        x, _, z = cube.p
        key = ("grass_overlay", x, z)
        multiplier = self.block_tint_cache.get(key)
        if multiplier is None:
            biome = self._get_biome(x, z).biome
            multiplier = self.biome_colors.grass_overlay_multiplier(biome)
            self.block_tint_cache[key] = multiplier

        rgb = tuple(component * shade for component in multiplier)
        return overlay, ('c3f', rgb * 4)

    def get_water_face_color(self, p, face_index):
        shade = 1.0 if face_index == 3 else 0.5 if face_index == 2 else 0.8 if face_index in (0, 4) else 0.6
        color = self.get_water_color(p)
        rgb = tuple(component / 255 * shade for component in color)
        return 'c3f', rgb * 4

    def get_water_current(self, p):
        x, y, z = roundPos(p)
        if (x, y, z) not in self.fluids and (x, y - 1, z) in self.fluids:
            y -= 1
        state = self.fluids.get((x, y, z))
        if state is None or state.source:
            return 0.0, 0.0

        flow_x = 0.0
        flow_z = 0.0
        for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
            neighbour = self.fluids.get((x + dx, y, z + dz))
            if neighbour is not None:
                difference = neighbour.level - state.level
            elif (x + dx, y, z + dz) not in self.cubes:
                difference = 1
            else:
                continue
            if difference > 0:
                flow_x += dx * difference
                flow_z += dz * difference
        length = (flow_x * flow_x + flow_z * flow_z) ** 0.5
        if not length:
            return 0.0, 0.0
        return flow_x / length, flow_z / length

    def _mark_boundary_chunks_dirty(self, p, chunk_key):
        """Only adjacent render chunks can change when a boundary block changes."""
        sx, sy, sz = self.RENDER_CHUNK_SIZE
        local_x, local_y, local_z = p[0] % sx, p[1] % sy, p[2] % sz
        neighbours = []
        if local_x == 0:
            neighbours.append((chunk_key[0] - 1, chunk_key[1], chunk_key[2]))
        elif local_x == sx - 1:
            neighbours.append((chunk_key[0] + 1, chunk_key[1], chunk_key[2]))
        if local_y == 0:
            neighbours.append((chunk_key[0], chunk_key[1] - 1, chunk_key[2]))
        elif local_y == sy - 1:
            neighbours.append((chunk_key[0], chunk_key[1] + 1, chunk_key[2]))
        if local_z == 0:
            neighbours.append((chunk_key[0], chunk_key[1], chunk_key[2] - 1))
        elif local_z == sz - 1:
            neighbours.append((chunk_key[0], chunk_key[1], chunk_key[2] + 1))

        for key in neighbours:
            chunk = self.render_chunks.get(key)
            if chunk is not None:
                chunk.mark_dirty()

    def updateCube(self, cube, customColor=None):
        # No‑op – we use chunk rebuilds
        pass

    def show(self, v, t, i, clrC=None):
        return None

    def rebuild_dirty_chunks(self, player_pos, render_distance=None,
                             max_rebuilds=None, cube_budget=None, time_budget=None):
        if render_distance is None:
            render_distance = settings.CHUNKS_RENDER_DISTANCE
        if max_rebuilds is None:
            max_rebuilds = self.max_rebuilds_per_frame
        if cube_budget is None:
            cube_budget = self.rebuild_cube_budget
        if time_budget is None:
            time_budget = self.rebuild_time_budget

        dirty = [chunk for chunk in self._iter_chunks_near(player_pos, render_distance)
                 if chunk.dirty]
        if not dirty:
            return

        def priority(chunk):
            return (chunk._rebuild_items is None,
                    self.chunk_distance_squared(chunk, player_pos))

        dirty.sort(key=priority)
        for chunk in dirty[:max_rebuilds]:
            adaptive_budget = cube_budget * min(4, 1 << chunk.rebuild_restarts)
            adaptive_time = (0 if time_budget <= 0 else
                             time_budget * min(2, 1 + chunk.rebuild_restarts))
            chunk.rebuild_step(adaptive_budget, adaptive_time)

    def chunks_within_distance(self, player_pos, render_distance=None):
        """Return the exact render-section set eligible for player updates."""
        if render_distance is None:
            render_distance = settings.CHUNKS_RENDER_DISTANCE
        if not settings.DISTANCE_CULLING:
            return list(self.render_chunks.values())

        distance_squared = render_distance * render_distance
        return [
            chunk for chunk in self._iter_chunks_near(player_pos, render_distance)
            if self.chunk_distance_squared(chunk, player_pos) <= distance_squared
        ]

    def chunk_bounds(self, chunk):
        x0 = chunk.cx * self.RENDER_CHUNK_SIZE[0] - 0.5
        y0 = chunk.cy * self.RENDER_CHUNK_SIZE[1] - 0.5
        z0 = chunk.cz * self.RENDER_CHUNK_SIZE[2] - 0.5
        return (x0, y0, z0,
                x0 + self.RENDER_CHUNK_SIZE[0],
                y0 + self.RENDER_CHUNK_SIZE[1],
                z0 + self.RENDER_CHUNK_SIZE[2])

    def chunk_distance_squared(self, chunk, player_pos):
        x0, y0, z0, x1, y1, z1 = self.chunk_bounds(chunk)
        dx = max(x0 - player_pos[0], 0.0, player_pos[0] - x1)
        dy = max(y0 - player_pos[1], 0.0, player_pos[1] - y1)
        dz = max(z0 - player_pos[2], 0.0, player_pos[2] - z1)
        return dx * dx + dy * dy + dz * dz

    def render(self, player_pos, render_distance=None):
        if render_distance is None:
            render_distance = settings.CHUNKS_RENDER_DISTANCE

        self.frustum.extract()

        visible = []
        render_distance_squared = render_distance * render_distance
        for chunk in self._iter_chunks_near(player_pos, render_distance):
            distance_squared = self.chunk_distance_squared(chunk, player_pos)
            # Distance check – only if culling is enabled
            if settings.DISTANCE_CULLING:
                if distance_squared > render_distance_squared:
                    continue

            x0, y0, z0, x1, y1, z1 = self.chunk_bounds(chunk)
            if not self.frustum.cube_in_frustum(x0, y0, z0, x1, y1, z1):
                continue

            center_x = (x0 + x1) / 2
            center_y = (y0 + y1) / 2
            center_z = (z0 + z1) / 2
            center_distance = ((center_x - player_pos[0]) ** 2
                               + (center_y - player_pos[1]) ** 2
                               + (center_z - player_pos[2]) ** 2)
            visible.append((center_distance, chunk))

        visible.sort(key=lambda item: item[0])
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        try:
            glDisable(GL_BLEND)
            glDepthMask(GL_TRUE)
            for _, chunk in visible:
                chunk.render_opaque()
        finally:
            glPopAttrib()

        # Binary foliage/plant cutouts write depth only for genuinely opaque
        # texels. Keeping blending off prevents partial mip alpha from hiding
        # terrain behind leaves.
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT)
        try:
            glDisable(GL_BLEND)
            glEnable(GL_ALPHA_TEST)
            glAlphaFunc(GL_GREATER, 0.5)
            for _, chunk in visible:
                chunk.render_cutout()
        finally:
            glPopAttrib()

        # tinted grass side overlays: alpha cut-outs sitting on the dirt sides
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_POLYGON_OFFSET_FILL)
            glPolygonOffset(-1.0, -1.0)
            for _, chunk in visible:
                chunk.render_overlay()
        finally:
            glPopAttrib()

        self.visible_water_chunks = list(reversed(visible))

    def render_shadow(self, center, radius):
        """Render nearby opaque chunk geometry into the sun/moon depth map."""
        radius_squared = radius * radius
        for chunk in self._iter_chunks_near(center, radius):
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0] / 2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2] / 2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1] / 2
            dx, dy, dz = cx - center[0], cy - center[1], cz - center[2]
            if dx * dx + dy * dy + dz * dz <= radius_squared:
                chunk.render_shadow()

    def render_water(self):
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDepthMask(GL_FALSE)
            for _, chunk in self.visible_water_chunks:
                chunk.render_water()
        finally:
            glPopAttrib()