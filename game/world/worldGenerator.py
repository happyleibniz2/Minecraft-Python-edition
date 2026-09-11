import math
import random
import time
from collections import deque

from game.world.Biomes import Biomes
from game.world.PerlinNoise import PerlinNoise
from settings import *


class _HashRng:
    """Deterministic per-column RNG built on worldGenerator._random_at.

    Avoids allocating a ``random.Random`` (which seeds a full MT state) for
    every generated column. Only the methods the column generator and tree
    spawner actually use are implemented.
    """

    __slots__ = ("world", "x", "z", "counter")

    def __init__(self, world, x, z):
        self.world = world
        self.x = x
        self.z = z
        self.counter = 0

    def randint(self, low, high):
        value = self.world._random_at(self.x, self.counter, self.z, 0xC011)
        self.counter += 1
        return low + int(value * (high - low + 1))

    def random(self):
        value = self.world._random_at(self.x, self.counter, self.z, 0xC011)
        self.counter += 1
        return value


class worldGenerator:
    MIN_Y = WORLD_MIN_Y
    MAX_Y = WORLD_MAX_Y
    SEA_LEVEL = SEA_LEVEL
    GENERATION_RADIUS = CHUNKS_RENDER_DISTANCE
    BACKGROUND_GENERATION_RADIUS = 64

    def __init__(self, glClass, seed=43242):
        self.seed = seed
        self.chunks = {}
        self.worldPerlin = PerlinNoise(seed, mh=8)
        self.perlinBiomes = PerlinNoise(seed ** 2, mh=10)
        self.gl = glClass
        offset_rng = random.Random(seed ^ 0x5DEECE66D)
        self._noise_offsets = tuple(offset_rng.uniform(-8192, 8192) for _ in range(16))
        self._height_cache = {}
        self._terrain_cache = {}
        self._column_biome_cache = {}

        q = []
        radius = self.GENERATION_RADIUS
        for x in range(-radius, radius + 1, CHUNK_SIZE[0]):
            for z in range(-radius, radius + 1, CHUNK_SIZE[2]):
                q.append((x, z))
        q = sorted(q, key=lambda i: i[0] ** 2 + i[1] ** 2)
        self.queue = deque(q)
        self.queued_chunks = set(q)
        self.generated_chunks = set()
        self.generating_chunks = set()
        self.pending_columns = deque()
        self._remaining_columns = {}
        self._last_queue_center = None

        self.start = len(self.queue)
        self.blocks = {}
        self.loading = deque()
        self._biome_cache = {}

    def add(self, p, t):
        blocks = self.blocks
        if blocks.get(p) is None:
            blocks[p] = t
            self.loading.append((p, t))

    def genChunk(self, player, max_chunks_per_call=8, max_blocks_per_call=256,
                 time_budget=0.004):
        if player.hp == -1:
            player.hp = 20
        self._queue_around(player.position)

        pending_limit = max_blocks_per_call * 4
        chunks_started = 0
        columns_generated = 0
        column_budget = max(1, max_blocks_per_call // 64)
        deadline = time.perf_counter() + time_budget if time_budget > 0 else None
        while column_budget > 0 and len(self.loading) < pending_limit:
            if not self.pending_columns:
                if not self.queue or chunks_started >= max_chunks_per_call:
                    break
                if time_budget > 0:
                    origin = self.queue[0]
                    center_x = math.floor(player.position[0] / CHUNK_SIZE[0]) * CHUNK_SIZE[0]
                    center_z = math.floor(player.position[2] / CHUNK_SIZE[2]) * CHUNK_SIZE[2]
                    dx, dz = origin[0] - center_x, origin[1] - center_z
                    if dx * dx + dz * dz > self.BACKGROUND_GENERATION_RADIUS ** 2:
                        break
                origin = self.queue.popleft()
                self.queued_chunks.discard(origin)
                self.generating_chunks.add(origin)
                self._remaining_columns[origin] = CHUNK_SIZE[0] * CHUNK_SIZE[2]
                for x in range(origin[0], origin[0] + CHUNK_SIZE[0]):
                    for z in range(origin[1], origin[1] + CHUNK_SIZE[2]):
                        self.pending_columns.append((x, z, origin))
                chunks_started += 1

            x, z, origin = self.pending_columns.popleft()
            self._generate_column(x, z)
            columns_generated += 1
            self._remaining_columns[origin] -= 1
            if self._remaining_columns[origin] == 0:
                del self._remaining_columns[origin]
                self.generating_chunks.discard(origin)
                self.generated_chunks.add(origin)
            column_budget -= 1
            if deadline is not None and time.perf_counter() >= deadline:
                break

        block_budget = max_blocks_per_call
        blocks_loaded = 0
        while self.loading and block_budget > 0:
            p, t = self.loading.popleft()
            if p not in self.gl.cubes.cubes:
                self.gl.cubes.add(p, t)
                blocks_loaded += 1
            block_budget -= 1
        return columns_generated, blocks_loaded

    @property
    def generated_count(self):
        return len(self.generated_chunks)

    def _queue_around(self, position):
        size_x, _, size_z = CHUNK_SIZE
        center = (math.floor(position[0] / size_x) * size_x,
                  math.floor(position[2] / size_z) * size_z)
        if center == self._last_queue_center:
            return
        self._last_queue_center = center
        desired = set()
        radius = self.GENERATION_RADIUS
        for x in range(center[0] - radius, center[0] + radius + 1, size_x):
            for z in range(center[1] - radius, center[1] + radius + 1, size_z):
                origin = (x, z)
                if ((x - center[0]) ** 2 + (z - center[1]) ** 2 <= radius ** 2
                        and origin not in self.generated_chunks
                        and origin not in self.generating_chunks):
                    desired.add(origin)
        self.queued_chunks = desired
        pending = list(self.queued_chunks)
        pending.sort(key=lambda item: ((item[0] - center[0]) ** 2
                                       + (item[1] - center[1]) ** 2))
        self.queue = deque(pending)

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
        for x in range(xx, xx + CHUNK_SIZE[0]):
            for z in range(zz, zz + CHUNK_SIZE[2]):
                self._generate_column(x, z)

    def _generate_column(self, x, z):
        add = self.add
        sea_level = self.SEA_LEVEL
        y = self.sample_height(x, z)
        biome_name = self.sample_biome(x, z)
        (_active_biome, grass, dirt, stone,
          ch, is_ocean, is_woodland, plant) = self._biome_data(biome_name)
        rng = _HashRng(self, x, z)
        spawnTree = rng.randint(0, ch) == 20 and y > sea_level + 1 and not is_ocean

        surface_open = not is_ocean and self.is_cave(x, y, z, y)
        if not surface_open:
            add((x, y, z), stone if is_ocean else grass)

        if is_ocean:
            for water_y in range(y + 1, sea_level + 1):
                add((x, water_y, z), "water")
        if not surface_open and spawnTree and is_woodland:
            self.spawnTree(x, y, z, rng)
        elif not surface_open and plant == "tall_grass" and rng.randint(0, 6) == 0:
            add((x, y + 1, z), "tall_grass")
        elif not surface_open and plant == "cactus" and rng.randint(0, 31) == 0:
            for cactus_y in range(y + 1, y + rng.randint(2, 3) + 1):
                add((x, cactus_y, z), "cactus")

        # Below a handful of blocks of overburden, cave noise can never fire,
        # so the per-block carve test is skipped entirely on very shallow
        # columns. The remaining columns still call is_cave as usual.
        can_carve = y > self.MIN_Y + 8

        surface_depth = rng.randint(3, 5)
        for block_y in range(self.MIN_Y, y):
            if block_y == self.MIN_Y:
                add((x, block_y, z), "bedrock")
                continue
            if block_y <= self.MIN_Y + 4:
                bedrock_chance = (self.MIN_Y + 5 - block_y) / 5
                if rng.random() < bedrock_chance:
                    add((x, block_y, z), "bedrock")
                    continue
            if can_carve and self.is_cave(x, block_y, z, y):
                continue
            depth = y - block_y
            material = dirt if depth <= surface_depth else stone
            # Cheap pre-filter: _ore_at itself rejects ~72% of blocks with the
            # same 0x0AF hash, so probing that hash first skips the remaining
            # ore-selection work for the overwhelming majority of stone.
            ore = None
            if depth > surface_depth and self._random_at(x, block_y, z, 0x0AF) < 0.72:
                ore = self._ore_at(x, block_y, z, biome_name)
            add((x, block_y, z), ore or material)

    @staticmethod
    def _clamp(value, low, high):
        return max(low, min(high, value))

    @staticmethod
    def _smoothstep(low, high, value):
        value = max(0.0, min(1.0, (value - low) / (high - low)))
        return value * value * (3.0 - 2.0 * value)

    @staticmethod
    def _evict_some(cache, limit):
        """Drop roughly a quarter of the entries instead of flushing."""
        target = len(cache) - (limit * 3 // 4)
        for key in list(cache.keys())[:target]:
            cache.pop(key, None)

    def _terrain_parameters(self, x, z):
        key = (x, z)
        cached = self._terrain_cache.get(key)
        if cached is not None:
            return cached
        offsets = self._noise_offsets
        noise = self.worldPerlin.noise2d
        continentalness = noise((x + offsets[0]) / 420, (z + offsets[1]) / 420)
        erosion = noise((x + offsets[2]) / 180, (z + offsets[3]) / 180)
        ridge_noise = noise((x + offsets[4]) / 105, (z + offsets[5]) / 105)
        detail = noise((x + offsets[6]) / 38, (z + offsets[7]) / 38)
        valley = abs(noise((x + offsets[8]) / 125, (z + offsets[9]) / 125))
        result = continentalness, erosion, ridge_noise, detail, valley
        if len(self._terrain_cache) >= 65536:
            self._evict_some(self._terrain_cache, 65536)
        self._terrain_cache[key] = result
        return result

    def sample_height(self, x, z):
        key = (x, z)
        cached = self._height_cache.get(key)
        if cached is not None:
            return cached
        continentalness, erosion, ridge_noise, detail, valley = self._terrain_parameters(x, z)
        land = self._smoothstep(-0.18, 0.28, continentalness)
        ridge = max(0.0, 1.0 - abs(ridge_noise) * 1.8)
        erosion_factor = self._clamp(0.65 - erosion, 0.0, 1.25)
        height = self.SEA_LEVEL + continentalness * 52 + detail * 9
        height += land * max(0.0, ridge - 0.48) / 0.52 * erosion_factor * 125
        height -= land * max(0.0, 0.16 - valley) / 0.16 * 24
        if continentalness < -0.16:
            height = self.SEA_LEVEL - 5 + (continentalness + 0.16) * 72 + detail * 5
        height = round(self._clamp(height, self.MIN_Y + 5, self.MAX_Y - 16))
        if len(self._height_cache) >= 65536:
            self._evict_some(self._height_cache, 65536)
        self._height_cache[key] = height
        return height

    def sample_biome(self, x, z):
        key = (x, z)
        cached = self._column_biome_cache.get(key)
        if cached is not None:
            return cached
        height = self.sample_height(x, z)
        if height < self.SEA_LEVEL:
            biome = "ocean"
        else:
            offsets = self._noise_offsets
            climate = self.perlinBiomes.noise2d
            temperature = climate((x + offsets[10]) / 260, (z + offsets[11]) / 260)
            humidity = climate((x + offsets[12]) / 220, (z + offsets[13]) / 220)
            if height >= 135:
                biome = "big_mountains"
            elif height >= 105:
                biome = "mountains"
            elif temperature > 0.24 and humidity < 0.08:
                biome = "desert"
            elif temperature < -0.22:
                biome = "taiga"
            elif humidity > 0.14:
                biome = "forest"
            else:
                biome = "plains"
        if len(self._column_biome_cache) >= 65536:
            self._evict_some(self._column_biome_cache, 65536)
        self._column_biome_cache[key] = biome
        return biome

    def is_cave(self, x, y, z, surface=None):
        surface = self.sample_height(x, z) if surface is None else surface
        if y <= self.MIN_Y + 4 or y > surface:
            return False
        offsets = self._noise_offsets
        noise = self.worldPerlin.noise
        depth = surface - y

        # Cheese caverns only open up below a few blocks of overburden and
        # their threshold rises with depth. Restructuring the branch means the
        # noise call is skipped entirely in the shallow band where the feature
        # cannot fire, which is a large share of the near-surface column.
        if depth >= 5:
            cheese = noise((x + offsets[0]) / 44, (y + offsets[14]) / 34,
                           (z + offsets[1]) / 44)
            openness = self._clamp((depth - 5) / 48, 0.0, 1.0)
            threshold = 0.46 - openness * 0.10
            if cheese > threshold:
                return True

        tunnel_a = abs(noise((x + offsets[4]) / 23, (y + offsets[15]) / 19,
                             (z + offsets[5]) / 23))
        if tunnel_a >= 0.045:
            return False
        tunnel_b = abs(noise((x + offsets[8]) / 27, (y - offsets[14]) / 21,
                             (z + offsets[9]) / 27))
        return tunnel_b < 0.045

    def _coordinate_seed(self, x, y, z, salt=0):
        value = (self.seed ^ salt ^ (x * 0x9E3779B185EBCA87)
                 ^ (y * 0xC2B2AE3D27D4EB4F) ^ (z * 0x165667B19E3779F9))
        value &= (1 << 64) - 1
        value ^= value >> 30
        value = (value * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
        value ^= value >> 27
        value = (value * 0x94D049BB133111EB) & ((1 << 64) - 1)
        return value ^ (value >> 31)

    def _random_at(self, x, y, z, salt):
        return self._coordinate_seed(x, y, z, salt) / float(1 << 64)

    def _ore_at(self, x, y, z, biome_name=None):
        selector = self._random_at(x // 2, y // 2, z // 2, 0x0AE)
        if self._random_at(x, y, z, 0x0AF) >= 0.72:
            return None
        candidates = []
        if y <= 16:
            depth_factor = self._clamp((16 - y) / 80, 0.0, 1.0)
            candidates.extend((("diamond_ore", 0.0015 + depth_factor * 0.007),
                               ("redstone_ore", 0.002 + depth_factor * 0.008)))
        if y <= 32:
            candidates.append(("gold_ore", 0.004))
        iron_factor = self._clamp(1.0 - abs(y - 16) / 96, 0.0, 1.0)
        candidates.append(("iron_ore", 0.002 + iron_factor * 0.012))
        lapis_factor = self._clamp(1.0 - abs(y) / 64, 0.0, 1.0)
        candidates.append(("lapis_ore", lapis_factor * 0.005))
        coal_factor = self._clamp(1.0 - abs(y - 96) / 128, 0.0, 1.0)
        candidates.append(("coal_ore", coal_factor * 0.014))
        if (-16 <= y <= 256
                and (biome_name or self.sample_biome(x, z)) in ("mountains", "big_mountains")):
            candidates.append(("emerald_ore", 0.004))
        cumulative = 0.0
        for ore, chance in candidates:
            cumulative += chance
            if selector < cumulative:
                return ore
        return None

    UNSAFE_GROUND = ("water", "lava", "cactus", "tnt")
    FOLIAGE = ("sapling", "tall_grass")

    def find_safe_spawn(self, center_x=None, center_z=None, radius=48, allow_water=False):
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
            candidate = self._column_spawn(x, z, allow_water)
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

    def _column_spawn(self, x, z, allow_water=False):
        cubes = self.gl.cubes.cubes
        for y in range(self.MAX_Y, self.MIN_Y - 1, -1):
            ground = cubes.get((x, y, z))
            if ground is None:
                continue
            if ground.name == "water" and allow_water:
                return [x, y + 0.5 + PLAYER_EYE_HEIGHT, z]
            if ground.name in self.UNSAFE_GROUND or ground.name.startswith("leaves"):
                return None
            if ground.name in self.FOLIAGE:
                continue
            if any((x, y + offset, z) in cubes for offset in (1, 2, 3)):
                return None
            return [x, y + 0.5 + PLAYER_EYE_HEIGHT, z]
        return None

    def spawnTree(self, x, y, z, rng=None):
        rng = rng or random
        treeHeight = rng.randint(5, 7)

        for i in range(y + 1, y + treeHeight + 1):
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