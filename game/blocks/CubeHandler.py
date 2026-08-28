from collections import deque

from OpenGL.GL import *
from functions import roundPos, cube_vertices, adjacent
from game.blocks.Cube import Cube
from game.blocks.RenderChunk import RenderChunk
from game.blocks.Water import FluidState, water_face_vertices
from game.Frustum import Frustum
from game.world.Biomes import Biomes, getBiomeByTemp
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

        # Render chunks
        self.render_chunks = {}
        self.RENDER_CHUNK_SIZE = (16, 16, 16)
        self.max_rebuilds_per_frame = 2

        # Frustum culling (kept but disabled)
        self.frustum = Frustum()

    def _get_chunk_key(self, pos):
        x, y, z = pos
        cx = x // self.RENDER_CHUNK_SIZE[0]
        cy = y // self.RENDER_CHUNK_SIZE[1]
        cz = z // self.RENDER_CHUNK_SIZE[2]
        return (cx, cy, cz)

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

    def add(self, p, t, now=False, fluid_level=0, fluid_source=None, fluid_falling=False):
        if p in self.cubes:
            if t == "water" and self.cubes[p].name == "water":
                source = fluid_level == 0 and not fluid_falling if fluid_source is None else fluid_source
                self._set_water_state(p, FluidState(fluid_level, source, fluid_falling))
            return
        cube = self.cubes[p] = Cube(t, p, self.block[t],
                                    'alpha' if t in self.alpha_textures else 'blend' if (t == 'water' or t == "lava") else 'solid')

        if cube.name not in ('water', 'lava'):
            self.collidable[p] = cube
        elif cube.name == "water":
            source = fluid_level == 0 and not fluid_falling if fluid_source is None else fluid_source
            self.fluids[p] = FluidState(max(0, min(7, fluid_level)), source, fluid_falling)

        chunk_key = self._get_chunk_key(p)
        if chunk_key not in self.render_chunks:
            self.render_chunks[chunk_key] = RenderChunk(
                chunk_key[0], chunk_key[1], chunk_key[2],
                self.RENDER_CHUNK_SIZE, self.gl
            )
        self.render_chunks[chunk_key].add_cube(p, cube)

        # Mark neighbours dirty
        for dx, dy, dz in ((1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)):
            adj_key = self._get_chunk_key((p[0]+dx, p[1]+dy, p[2]+dz))
            if adj_key in self.render_chunks:
                self.render_chunks[adj_key].dirty = True

        # Legacy adjacency (for shown flags – not used for rendering but kept)
        for adj in adjacent(*cube.p):
            if adj not in self.cubes:
                self.set_adj(cube, adj, True)
            else:
                a, b = cube.type, self.cubes[adj].type
                if a == b and (a == 'solid' or b == 'blend'):
                    self.set_adj(self.cubes[adj], cube.p, False)
                elif a != 'blend' and b != 'solid':
                    self.set_adj(self.cubes[adj], cube.p, False)
                    self.set_adj(cube, adj, True)

        if t == "water" and now:
            self._schedule_fluid(p)
        if now:
            self._schedule_adjacent_water(p)

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

        chunk_key = self._get_chunk_key(p)
        if chunk_key in self.render_chunks:
            self.render_chunks[chunk_key].remove_cube(p)

        for dx, dy, dz in ((1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)):
            adj_key = self._get_chunk_key((p[0]+dx, p[1]+dy, p[2]+dz))
            if adj_key in self.render_chunks:
                self.render_chunks[adj_key].dirty = True

        for adj in adjacent(*cube.p):
            if adj in self.cubes:
                self.set_adj(self.cubes[adj], cube.p, True)
        if was_water or cube.name != "water":
            self._schedule_adjacent_water(p)

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

        if state.source or (not can_fall and (state.falling or state.level < 7)):
            next_level = 1 if state.source or state.falling else state.level + 1
            if next_level <= 7:
                for dx, dz in ((-1, 0), (1, 0), (0, -1), (0, 1)):
                    self._flow_water_into((x + dx, y, z + dz), FluidState(next_level, False, False))

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
                chunk.dirty = True

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
            return neighbour.type in ('alpha', 'blend')
        if neighbour.name != "water":
            return neighbour.type in ('alpha', 'blend')
        if face_index in (2, 3):
            return False
        return self.get_water_height(neighbour.p) < self.get_water_height(cube.p)

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
            temperature = self.gl.worldGen.perlinBiomes(x, z) * 3
            self.biome_cache[key] = Biomes(getBiomeByTemp(temperature))
        return self.biome_cache[key]

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

    def set_adj(self, cube, adj, state):
        x, y, z = cube.p
        X, Y, Z = adj
        d = X - x, Y - y, Z - z
        f = 'left', 'right', 'bottom', 'top', 'back', 'front'
        for i in (0, 1, 2):
            if d[i] == 0:
                continue
            j = i + i
            if d[i] > 0:
                a, b = f[j + 1], f[j]
            else:
                a, b = f[j], f[j + 1]
            cube.shown[a] = state
            if not state and cube.faces[a]:
                cube.faces[a].delete()
                cube.faces[a] = None

    def updateCube(self, cube, customColor=None):
        # No‑op – we use chunk rebuilds
        pass

    def show(self, v, t, i, clrC=None):
        return None

    def rebuild_dirty_chunks(self, player_pos, render_distance=None):
        if render_distance is None:
            render_distance = settings.CHUNKS_RENDER_DISTANCE

        dirty = [chunk for chunk in self.render_chunks.values() if chunk.dirty]
        if not dirty:
            return

        # Only filter by distance if culling is enabled
        if settings.DISTANCE_CULLING:
            def within_distance(chunk):
                cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
                cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
                cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
                dx = cx - player_pos[0]
                dy = cy - player_pos[1]
                dz = cz - player_pos[2]
                return dx*dx + dy*dy + dz*dz < render_distance*render_distance
            dirty = [c for c in dirty if within_distance(c)]

        def priority(chunk):
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
            dx = cx - player_pos[0]
            dy = cy - player_pos[1]
            dz = cz - player_pos[2]
            return dx*dx + dy*dy + dz*dz

        dirty.sort(key=priority)
        for chunk in dirty[:self.max_rebuilds_per_frame]:
            chunk.rebuild()

    def render(self, player_pos, render_distance=None):
        if render_distance is None:
            render_distance = settings.CHUNKS_RENDER_DISTANCE

        self.frustum.extract()

        visible = []
        for chunk in self.render_chunks.values():
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
            dx = cx - player_pos[0]
            dy = cy - player_pos[1]
            dz = cz - player_pos[2]
            distance_squared = dx*dx + dy*dy + dz*dz
            # Distance check – only if culling is enabled
            if settings.DISTANCE_CULLING:
                if distance_squared > render_distance*render_distance:
                    continue

            x0 = chunk.cx * self.RENDER_CHUNK_SIZE[0] - 0.5
            y0 = chunk.cy * self.RENDER_CHUNK_SIZE[1] - 0.5
            z0 = chunk.cz * self.RENDER_CHUNK_SIZE[2] - 0.5
            x1 = x0 + self.RENDER_CHUNK_SIZE[0]
            y1 = y0 + self.RENDER_CHUNK_SIZE[1]
            z1 = z0 + self.RENDER_CHUNK_SIZE[2]
            if not self.frustum.cube_in_frustum(x0, y0, z0, x1, y1, z1):
                continue

            visible.append((distance_squared, chunk))

        for _, chunk in visible:
            chunk.render_opaque()

        self.visible_water_chunks = sorted(visible, key=lambda item: item[0], reverse=True)

    def render_water(self):
        glDepthMask(GL_FALSE)
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            for _, chunk in self.visible_water_chunks:
                chunk.render_water()
        finally:
            glDepthMask(GL_TRUE)
