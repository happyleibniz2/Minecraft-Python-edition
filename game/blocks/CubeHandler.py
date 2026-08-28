from OpenGL.GL import *
from functions import roundPos, cube_vertices, adjacent
from game.blocks.Cube import Cube
from game.blocks.RenderChunk import RenderChunk
from game.Frustum import Frustum
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

    def hitTest(self, p, vec, dist=4):
        m = 8
        x, y, z = p
        dx, dy, dz = vec
        dx /= m
        dy /= m
        dz /= m
        prev = None
        for i in range(dist * m):
            key = roundPos((x, y, z))
            if key in self.cubes and key not in self.fluids:
                return key, prev
            prev = key
            x, y, z = x + dx, y + dy, z + dz
        return None, None

    def add(self, p, t, now=False):
        if p in self.cubes:
            return
        cube = self.cubes[p] = Cube(t, p, self.block[t],
                                    'alpha' if t in self.alpha_textures else 'blend' if (t == 'water' or t == "lava") else 'solid')

        if cube.name not in ('water', 'lava'):
            self.collidable[p] = cube

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

    def remove(self, p):
        if p not in self.cubes:
            return
        if self.cubes[p].name == "bedrock":
            return
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

        for chunk in self.render_chunks.values():
            # Distance check – only if culling is enabled
            if settings.DISTANCE_CULLING:
                cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
                cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
                cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
                dx = cx - player_pos[0]
                dy = cy - player_pos[1]
                dz = cz - player_pos[2]
                if dx*dx + dy*dy + dz*dz > render_distance*render_distance:
                    continue

            x0 = chunk.cx * self.RENDER_CHUNK_SIZE[0] - 0.5
            y0 = chunk.cy * self.RENDER_CHUNK_SIZE[1] - 0.5
            z0 = chunk.cz * self.RENDER_CHUNK_SIZE[2] - 0.5
            x1 = x0 + self.RENDER_CHUNK_SIZE[0]
            y1 = y0 + self.RENDER_CHUNK_SIZE[1]
            z1 = z0 + self.RENDER_CHUNK_SIZE[2]
            if not self.frustum.cube_in_frustum(x0, y0, z0, x1, y1, z1):
                continue

            chunk.render()
