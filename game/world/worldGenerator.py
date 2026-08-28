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

    def add(self, p, t):
        if p in self.blocks:
            return
        self.blocks[p] = t
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

    def gen(self, xx, zz):
        sy = CHUNK_SIZE[1]
        oldY = 0

        for x in range(xx, xx + CHUNK_SIZE[0]):
            for z in range(zz, zz + CHUNK_SIZE[2]):
                y = self.worldPerlin(x, z)
                biomePerlin = self.perlinBiomes(x, z) * 3
                activeBiome = Biomes(getBiomeByTemp(biomePerlin))
                if activeBiome.biome == "mountains":
                    if -3 < oldY - y < 3:
                        y = int((oldY + y) / 2)
                if activeBiome.biome == "big_mountains":
                    if -3 < oldY - y < 3:
                        y *= 2
                        y = int((oldY + y) / 2)
                oldY = y
                y += sy
                is_ocean = activeBiome.biome == "ocean"
                if is_ocean:
                    y = min(y, self.SEA_LEVEL - 3)
                ch = 70
                if activeBiome.biome in ["forest", "taiga"]:
                    ch = 50

                spawnTree = random.randint(0, ch) == 20 and y > sy - 5 and not is_ocean

                surface = activeBiome.getBiomeGrass()
                if is_ocean:
                    surface = activeBiome.getBiomeStone()
                self.add((x, y, z), surface)

                if is_ocean:
                    for water_y in range(y + 1, self.SEA_LEVEL + 1):
                        self.add((x, water_y, z), "water")
                elif self.gl.startPlayerPos == [0, -9000, 0] and not spawnTree:
                    self.gl.startPlayerPos = [x, y + 2, z]
                    self.gl.player.position = [x, y + 2, z]
                    self.gl.player.lastPlayerPosOnGround = [x, y + 2, z]

                if spawnTree and activeBiome.biome in ["forest", "taiga"]:
                    self.spawnTree(x, y, z)

                self.add((x, 0, z), "bedrock")
                for i in range(1, y):
                    if i > y - random.randint(5, 10):
                        self.add((x, i, z), activeBiome.getBiomeDirt())
                    else:
                        self.add((x, i, z), activeBiome.getBiomeStone())
                    if i < sy - 20:
                        self.genOre(x, i, z)

    def genOre(self, x, y, z):
        if random.randint(0, 5753) != random.randint(0, 1575):
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
