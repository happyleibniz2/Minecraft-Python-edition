import random
from collections import deque
from mobs.cow import Cow as Cow
from game.world.Biomes import Biomes, getBiomeByTemp
from game.world.PerlinNoise import PerlinNoise
from settings import *
import pickle


class worldGenerator:
    def __init__(self, glClass, seed=43242, world=None):
        self.world = open('saves/Current_world/world.dat', 'rb').read()
        self.cow = None
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
        self.blocks = {}  # dict(pickle.loads(self.world))
        self.loading = deque()
        self.last_gen_tick = 0

    def add(self, p, t):
        if p in self.blocks:
            return
        self.blocks[p] = t
        self.loading.append((p, t))
        self.gl.cubes.add(p, t)

    def genChunk(self, player, max_chunks_per_call=8, max_blocks_per_call=256):
        if player.hp == -1:
            player.hp = 20

        now = pygame.time.get_ticks()
        if now - getattr(self, 'last_gen_tick', 0) < 15:
            return
        self.last_gen_tick = now

        chunks_processed = 0
        while self.queue and chunks_processed < max_chunks_per_call:
            self.gen(*self.queue.popleft())
            chunks_processed += 1

        block_budget = max_blocks_per_call
        while self.loading and block_budget > 0:
            p, t = self.loading.popleft()
            if p in self.gl.cubes.cubes:
                try:
                    self.gl.cubes.updateCube(self.gl.cubes.cubes[p])
                except Exception:
                    pass
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
                ch = 70
                if activeBiome.biome in ["forest", "taiga"]:
                    ch = 50

                spawnTree = random.randint(0, ch) == 20 and y > sy - 5
                af = activeBiome.getBiomeGrass()
                self.add((x, y, z), af)
                if self.gl.startPlayerPos == [0, -9000, 0] and not spawnTree:
                    self.gl.startPlayerPos = [x, y + 2, z]
                    self.gl.player.position = [x, y + 2, z]
                    self.gl.player.lastPlayerPosOnGround = [x, y + 2, z]

                if spawnTree and activeBiome.biome in ["forest", "taiga"]:
                    self.spawnTree(x, y, z)

                self.add((x, 0, z), "bedrock")
                for i in range(1, y):
                    if i > y - random.randint(5, 10):
                        self.add((x, i, z), activeBiome.getBiomeDirt())
                        if activeBiome.getBiomePlant() == "cactus":
                            self.add((x, y + 1, z), "cactus")
                    else:
                        self.add((x, i, z), activeBiome.getBiomeStone())
                        self.genOre(x, i, z)

    def genOre(self, x, y, z):
        if random.randint(0, 5753) != random.randint(0, 1575):
            return
        r1 = random.randint(-1, 2)
        r2 = random.randint(0, 2)
        ore = self.getOreByY(int(y))

        for xi in range(r1, r2):
            for yi in range(r1):
                for zi in range(r2):
                    self.add((int(x + xi), int(y + yi), int(z + zi)), ore)

    def getOreByY(self, y):
        if y < 20:
            _diamond = random.randint(1, 1176)
            if _diamond > 54:
                return "diamond_ore"
            if random.randint(1, 1234) > 54:
                return "emerald_ore"
            if random.randint(1, 16) < 54:
                return "redstone_ore"
        elif y < 96:
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
