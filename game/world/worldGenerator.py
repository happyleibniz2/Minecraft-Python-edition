import random
from collections import deque

from game.world.Biomes import Biomes, getBiomeByTemp
from game.world.PerlinNoise import PerlinNoise
from settings import *


class worldGenerator:
    SEA_LEVEL = CHUNK_SIZE[1] - 2

    def __init__(self, glClass, seed=43242):
        self.seed = seed
        self.chunks = {}
        self.worldPerlin = PerlinNoise(seed, mh=8)
        self.perlinBiomes = PerlinNoise(seed ** 2, mh=10)
        self.gl = glClass

        q = []
        for x in range(-90, 90, CHUNK_SIZE[0]):
            for y in range(-90, 90, CHUNK_SIZE[2]):
                q.append((x, y))
        q = sorted(q, key=lambda i: i[0] ** 2 + i[1] ** 2)
        self.queue = deque(q)

        self.start = len(self.queue)
        self.blocks = {}
        self.loading = deque()
        self._biome_cache = {}

    def add(self, p, t):
        # one dict lookup instead of a membership test plus an insert
        blocks = self.blocks
        if blocks.get(p) is None:
            blocks[p] = t
            self.loading.append((p, t))

    def genChunk(self, player, max_chunks_per_call=8, max_blocks_per_call=256):
        if player.hp == -1:
            player.hp = 20

        pending_limit = max_blocks_per_call * 4
        chunks_processed = 0
        while (self.queue and chunks_processed < max_chunks_per_call and
               len(self.loading) < pending_limit):
            self.gen(*self.queue.popleft())
            chunks_processed += 1

        block_budget = max_blocks_per_call
        while self.loading and block_budget > 0:
            p, t = self.loading.popleft()
            if p not in self.gl.cubes.cubes:
                self.gl.cubes.add(p, t)
            block_budget -= 1

    def _biome_data(self, biome_name):
        """Cache the per-biome constants; they never change per column."""
        data = self._biome_cache.get(biome_name)
        if data is None:
            biome = Biomes(biome_name)
            data = (
                biome,
                biome.getBiomeGrass(),
                biome.getBiomeDirt(),
                biome.getBiomeStone(),
                50 if biome_name in ("forest", "taiga") else 70,
                biome_name == "ocean",
                biome_name in ("forest", "taiga"),
                biome.getBiomePlant(),
            )
            self._biome_cache[biome_name] = data
        return data

    def gen(self, xx, zz):
        sy = CHUNK_SIZE[1]
        oldY = 0

        # hoist attribute lookups out of the per-block loops
        add = self.add
        randint = random.randint
        gen_ore = self.genOre
        world_perlin = self.worldPerlin
        biome_perlin = self.perlinBiomes
        sea_level = self.SEA_LEVEL
        ore_depth = sy - 20
        first_spawn = self.gl.startPlayerPos == [0, -9000, 0]

        for x in range(xx, xx + CHUNK_SIZE[0]):
            for z in range(zz, zz + CHUNK_SIZE[2]):
                y = world_perlin(x, z)
                biome_name = getBiomeByTemp(biome_perlin(x, z) * 3)
                (activeBiome, grass, dirt, stone,
                 ch, is_ocean, is_woodland, plant) = self._biome_data(biome_name)

                if biome_name == "mountains":
                    if -3 < oldY - y < 3:
                        y = int((oldY + y) / 2)
                elif biome_name == "big_mountains":
                    if -3 < oldY - y < 3:
                        y *= 2
                        y = int((oldY + y) / 2)
                oldY = y
                y += sy
                if is_ocean:
                    y = min(y, sea_level - 3)

                spawnTree = randint(0, ch) == 20 and y > sy - 5 and not is_ocean

                add((x, y, z), stone if is_ocean else grass)

                if is_ocean:
                    for water_y in range(y + 1, sea_level + 1):
                        add((x, water_y, z), "water")
                elif first_spawn and not spawnTree:
                    self.gl.startPlayerPos = [x, y + 2, z]
                    self.gl.player.position = [x, y + 2, z]
                    self.gl.player.lastPlayerPosOnGround = [x, y + 2, z]
                    first_spawn = False

                if spawnTree and is_woodland:
                    self.spawnTree(x, y, z)
                elif plant == "tall_grass" and randint(0, 6) == 0:
                    add((x, y + 1, z), "tall_grass")
                elif plant == "cactus" and randint(0, 31) == 0:
                    for cactus_y in range(y + 1, y + randint(2, 3) + 1):
                        add((x, cactus_y, z), "cactus")

                add((x, 0, z), "bedrock")

                # the per-block randint is deliberate: it gives the dirt/stone
                # boundary its ragged look, so it must stay per block
                for i in range(1, y):
                    add((x, i, z), dirt if i > y - randint(5, 10) else stone)
                    if i < ore_depth:
                        gen_ore(x, i, z)

    # probability that ``randint(0, 5753) == randint(0, 1575)``: for each of the
    # 1576 shared values both draws must agree, so p = 1576 / (5754 * 1576)
    ORE_CHANCE = 1.0 / 5754

    def genOre(self, x, y, z):
        # the original drew two randints per block and discarded almost all of
        # them; one cheap random() reproduces the same rate far faster
        if random.random() >= self.ORE_CHANCE:
            return
        r1 = random.randint(-1, 2)
        r2 = random.randint(0, 2)
        ore = self.getOreByY(y)

        for xi in range(r1, r2):
            for yi in range(r1):
                for zi in range(r2):
                    self.add((x + xi, yi + y, zi + z), ore)

    def getOreByY(self, y):
        if y < 20:
            if random.randint(0, 150) > 54:
                return "diamond_ore"
            if random.randint(0, 1000) > 54:
                return "emerald_ore"
            if random.randint(0, 180) < 54:
                return "redstone_ore"
        elif y < 40:
            if random.randint(0, 180) == 54:
                return "gold_ore"
        if random.randint(0, 100) < 54:
            return "iron_ore"
        if random.randint(0, 80) < 54:
            return "coal_ore"
        if random.randint(0, 180) == 54:
            return "dirt"
        if random.randint(0, 180) == 54:
            return "gravel"
        return "dirt"

    UNSAFE_GROUND = ("water", "lava", "cactus", "tnt")
    FOLIAGE = ("sapling", "tall_grass")

    def find_safe_spawn(self, center_x=None, center_z=None, radius=48):
        cubes = self.gl.cubes.cubes
        if not cubes:
            return None

        if center_x is None or center_z is None:
            origin = self.gl.startPlayerPos
            if origin and origin[1] > -9000:
                center_x = round(origin[0]) if center_x is None else center_x
                center_z = round(origin[2]) if center_z is None else center_z
            else:
                center_x = 0 if center_x is None else center_x
                center_z = 0 if center_z is None else center_z

        best = None
        best_score = None
        for x, z in self._spiral_columns(center_x, center_z, radius):
            candidate = self._column_spawn(x, z)
            if candidate is None:
                continue
            distance = abs(x - center_x) + abs(z - center_z)
            score = (distance, -candidate[1])
            if best_score is None or score < best_score:
                best = candidate
                best_score = score
                if distance == 0:
                    break
        return best

    def _spiral_columns(self, center_x, center_z, radius):
        yield center_x, center_z
        for r in range(1, radius + 1):
            for offset in range(-r, r + 1):
                yield center_x + offset, center_z - r
                yield center_x + offset, center_z + r
            for offset in range(-r + 1, r):
                yield center_x - r, center_z + offset
                yield center_x + r, center_z + offset

    def _column_spawn(self, x, z):
        cubes = self.gl.cubes.cubes
        top = self.SEA_LEVEL + 40
        for y in range(top, 0, -1):
            ground = cubes.get((x, y, z))
            if ground is None:
                continue
            if ground.name in self.UNSAFE_GROUND or ground.name.startswith("leaves"):
                return None
            if ground.name in self.FOLIAGE:
                continue
            if any((x, y + offset, z) in cubes for offset in (1, 2, 3)):
                return None
            return [x, y + 2, z]
        return None

    def spawnTree(self, x, y, z):
        treeHeight = random.randint(5, 7)

        for i in range(y, y + treeHeight):
            self.add((x, i, z), 'log_oak')
        for i in range(x + -2, x + 3):
            for j in range(z + -2, z + 3):
                for k in range(y + treeHeight - 2, y + treeHeight):
                    self.add((i, k, j), 'leaves_oak')
        for i in range(treeHeight, treeHeight + 1):
            for j in range(-1, 2):
                for k in range(-1, 2):
                    self.add((x + j, y + i, z + k), 'leaves_oak')
        cl = 2
        for i in range(treeHeight + 1, treeHeight + 2):
            for j in range(-1, 2):
                for k in range(-1, 2):
                    if cl % 2 != 0:
                        self.add((x + j, y + i, z + k), 'leaves_oak')
                    cl += 1
        self.add((x, y + treeHeight + 1, z), 'leaves_oak')
