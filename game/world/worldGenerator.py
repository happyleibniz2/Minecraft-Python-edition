import random
import threading
from collections import deque

from game.world.Biomes import Biomes, getBiomeByTemp
from game.world.PerlinNoise import PerlinNoise
from settings import *

class worldGenerator:
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
        self._lock = threading.Lock()
        self.generating = False
        self._worker_thread = None

    def start(self):
        """Begin asynchronous chunk generation if not already running."""
        if self.generating:
            return
        self.generating = True
        self._worker_thread = threading.Thread(target=self._generate_worker, daemon=True)
        self._worker_thread.start()

    def _generate_worker(self):
        # Worker runs in background thread, generates chunk data and appends to loading
        while self.queue:
            xx, zz = self.queue.popleft()
            self.gen(xx, zz)
        # when queue is empty, generation done
        self.generating = False

    def add(self, p, t):
        # store block data; actual cube creation happens on the main thread
        with self._lock:
            if p in self.blocks:
                return
            self.blocks[p] = t
            self.loading.append((p, t))
        # note: do not call gl.cubes.add() here when running in a background thread

    def genChunk(self, player):
        # kept for backwards compatibility; ensure thread is running
        if player.hp == -1:
            player.hp = 20
        if not self.generating:
            self.start()
        # generation work is performed in background thread; flush any finished cubes
        self.process_loading()

    def process_loading(self):
        # must be called from main thread to update OpenGL structures
        while self.loading:
            p, t = self.loading.popleft()
            # create cube and update its visual representation
            self.gl.cubes.add(p, t)
            self.gl.cubes.updateCube(self.gl.cubes.cubes[p])

    def gen(self, xx, zz):
        # this runs in the worker thread, so avoid touching OpenGL
        sy = CHUNK_SIZE[1]
        oldY = 0
        self.genOre(-2.0,59.75,-2.0)
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

                self.add((x, y, z), activeBiome.getBiomeGrass())
                if self.gl.startPlayerPos == [0, -9000, 0] and not spawnTree:
                    self.gl.startPlayerPos = [x, y + 2, z]
                    self.gl.player.position = [x, y + 2, z]
                    self.gl.player.lastPlayerPosOnGround = [x, y + 2, z]

                if spawnTree and activeBiome.biome in ["forest", "taiga"]:
                    self.spawnTree(x, y, z)

                self.add((x, 0, z), "bedrock")
                # self.add((x,-1,z),"emerald_ore")
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

    # background thread management ------------------------------------------------
    def _generate_worker(self):
        # keep consuming queue until exhausted
        while self.queue:
            xx, zz = self.queue.popleft()
            self.gen(xx, zz)
        self.generating = False

    def start(self):
        if not self.generating:
            self.generating = True
            self._worker_thread = threading.Thread(target=self._generate_worker, daemon=True)
            self._worker_thread.start()

    def getOreByY(self, y):
        if y < 20:
            _diamond = random.randint(0, 150)
            if _diamond > 54:
                # debug: diamond spawn, comment out to reduce output
                # print("diamond generated at ",_diamond)
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
