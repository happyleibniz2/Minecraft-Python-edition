from OpenGL.GL import *
from functions import roundPos, cube_vertices, adjacent
from game.blocks.Cube import Cube
from game.blocks.RenderChunk import RenderChunk

class CubeHandler:
    top_color = ('c3f', (1.0,) * 12)
    ns_color = ('c3f', (0.8,) * 12)
    ew_color = ('c3f', (0.6,) * 12)
    bottom_color = ('c3f', (0.5,) * 12)

    def __init__(self, batch, block, opaque, alpha_textures, gl):
        self.block = block
        self.alpha_textures = alpha_textures
        self.gl = gl

        # All cubes (world pos -> Cube)
        self.cubes = {}

        # Collidable cubes (for physics)
        self.collidable = {}

        # Render chunks
        self.render_chunks = {}
        self.RENDER_CHUNK_SIZE = (8, 8, 8)   # smaller = faster rebuilds
        self.max_rebuilds_per_frame = 2      # limit rebuilds to avoid lag

        # For compatibility
        self.fluids = {}

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

        # Add to collidable if solid
        if cube.name not in ('water', 'lava'):
            self.collidable[p] = cube

        # Add to render chunk
        chunk_key = self._get_chunk_key(p)
        if chunk_key not in self.render_chunks:
            self.render_chunks[chunk_key] = RenderChunk(
                chunk_key[0], chunk_key[1], chunk_key[2],
                self.RENDER_CHUNK_SIZE, self.gl
            )
        self.render_chunks[chunk_key].add_cube(p, cube)

        # Mark adjacent chunks dirty
        for dx, dy, dz in ((1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)):
            adj_key = self._get_chunk_key((p[0]+dx, p[1]+dy, p[2]+dz))
            if adj_key in self.render_chunks:
                self.render_chunks[adj_key].dirty = True

        # Existing adjacency logic (for shown faces, though we now rebuild chunks entirely)
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

        # Mark neighbours dirty
        for dx, dy, dz in ((1,0,0), (-1,0,0), (0,1,0), (0,-1,0), (0,0,1), (0,0,-1)):
            adj_key = self._get_chunk_key((p[0]+dx, p[1]+dy, p[2]+dz))
            if adj_key in self.render_chunks:
                self.render_chunks[adj_key].dirty = True

        # Update adjacent cubes (they may now have new exposed faces)
        # We don't need to update shown because we rebuild chunks, but we still update collidable.
        # We'll also update the neighbours' collidable status (should already be fine).
        for adj in adjacent(*cube.p):
            if adj in self.cubes:
                self.set_adj(self.cubes[adj], cube.p, True)

    def set_adj(self, cube, adj, state):
        # This updates the shown flag, but now we don't use it for rendering.
        # However, it might be used elsewhere, so we keep it.
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
        # No‑op because we use chunk rebuilds
        pass

    def show(self, v, t, i, clrC=None):
        # Not used
        return None

    def rebuild_dirty_chunks(self, player_pos, render_distance=64):
        """Rebuild up to max_rebuilds_per_frame dirty chunks, closest first."""
        dirty = [chunk for chunk in self.render_chunks.values() if chunk.dirty]
        if not dirty:
            return

        # Filter chunks within render distance
        def within_distance(chunk):
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
            dx = cx - player_pos[0]
            dy = cy - player_pos[1]
            dz = cz - player_pos[2]
            return dx*dx + dy*dy + dz*dz < render_distance*render_distance

        dirty = [c for c in dirty if within_distance(c)]

        # Sort by distance
        def priority(chunk):
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
            dx = cx - player_pos[0]
            dy = cy - player_pos[1]
            dz = cz - player_pos[2]
            return dx*dx + dy*dy + dz*dz

        dirty.sort(key=priority)

        # Rebuild limited number
        for chunk in dirty[:self.max_rebuilds_per_frame]:
            chunk.rebuild()

    def render(self, player_pos, render_distance=64):
        """Render only chunks within render distance."""
        for chunk in self.render_chunks.values():
            cx = chunk.cx * self.RENDER_CHUNK_SIZE[0] + self.RENDER_CHUNK_SIZE[0]//2
            cy = chunk.cy * self.RENDER_CHUNK_SIZE[1] + self.RENDER_CHUNK_SIZE[1]//2
            cz = chunk.cz * self.RENDER_CHUNK_SIZE[2] + self.RENDER_CHUNK_SIZE[2]//2
            dx = cx - player_pos[0]
            dy = cy - player_pos[1]
            dz = cz - player_pos[2]
            if dx*dx + dy*dy + dz*dz < render_distance*render_distance:
                chunk.render()