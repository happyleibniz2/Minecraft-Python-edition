import math
import os
import random
import sys
import time
from collections import deque
from concurrent.futures import ProcessPoolExecutor

import numpy as np

from game.world import gen_worker
from game.world.Biomes import Biomes
from game.world.PerlinNoise import PerlinNoise
from settings import *


class worldGenerator:
    MIN_Y = WORLD_MIN_Y
    MAX_Y = WORLD_MAX_Y
    SEA_LEVEL = SEA_LEVEL
    GENERATION_RADIUS = CHUNKS_RENDER_DISTANCE
    BACKGROUND_GENERATION_RADIUS = 64

    def __init__(self, glClass, seed=43242):
        # Replacing a world while its initial load is still running would
        # otherwise leave a spawn pool alive in the background.  The Scene
        # assigns the new generator after this constructor returns, so the old
        # one is still visible on ``glClass`` here.
        previous = getattr(glClass, "worldGen", None)
        if previous is not None and previous is not self:
            shutdown = getattr(previous, "_shutdown_executor", None)
            if shutdown is not None:
                try:
                    shutdown()
                except Exception:
                    pass

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

        # Parallel initial-generation state.  The executor is created lazily
        # on the first initial-load call so normal gameplay and unit tests do
        # not pay for worker processes.
        self._executor = None
        self._futures = {}
        self._max_inflight = 0
        self._parallel_failed = False
        self._parallel_complete = False
        self._fast_configured = False

    def add(self, p, t):
        # one dict lookup instead of a membership test plus an insert
        blocks = self.blocks
        if blocks.get(p) is None:
            blocks[p] = t
            self.loading.append((p, t))

    def genChunk(self, player, max_chunks_per_call=8, max_blocks_per_call=256,
                 time_budget=0.004):
        if player.hp == -1:
            player.hp = 20
        self._queue_around(player.position)

        # Initial loading uses the vectorised generator (and, when the entry
        # point is multiprocessing-safe, a process pool).  Background loading
        # keeps the incremental time-budgeted path below.
        if self._executor is not None:
            return self._gen_parallel(max_chunks_per_call, max_blocks_per_call)
        if time_budget <= 0 and not self._parallel_failed and not self._parallel_complete:
            self._ensure_executor()
            if self._executor is not None:
                return self._gen_parallel(max_chunks_per_call, max_blocks_per_call)
        if time_budget <= 0:
            return self._gen_fast_sequential(max_chunks_per_call)

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

    # ------------------------------------------------------------------
    # Fast / parallel generation
    # ------------------------------------------------------------------
    def _configure_fastgen(self):
        """Point the shared vectorised generator at this world's seed."""
        if self._fast_configured:
            return
        gen_worker.configure(
            self.seed, self._noise_offsets, CHUNK_SIZE,
            self.MIN_Y, self.MAX_Y, self.SEA_LEVEL,
            world_noise=self.worldPerlin, biome_noise=self.perlinBiomes,
        )
        self._fast_configured = True

    def _ensure_executor(self):
        """Create a spawn-based worker pool when the entry point is safe.

        ``multiprocessing`` re-imports ``__main__`` on Windows.  The project's
        supported entry point is ``start.py`` (which guards its body with
        ``if __name__ == "__main__"``), so we only start workers there.  A
        direct ``python minecraft_main_program.py`` run falls back to the
        in-process vectorised path instead of spawning the whole game again.
        """
        if self._executor is not None or self._parallel_failed:
            return
        main_file = getattr(sys.modules.get("__main__"), "__file__", "") or ""
        if os.path.basename(main_file).lower() != "start.py":
            self._parallel_failed = True
            return
        try:
            import multiprocessing
            workers = max(1, min(6, os.cpu_count() or 1))
            context = multiprocessing.get_context("spawn")
            self._executor = ProcessPoolExecutor(
                max_workers=workers,
                mp_context=context,
                initializer=gen_worker.worker_init,
                initargs=(
                    self.seed, self._noise_offsets, CHUNK_SIZE,
                    self.MIN_Y, self.MAX_Y, self.SEA_LEVEL,
                ),
            )
            self._max_inflight = workers * 3
        except Exception as error:
            print(f"Warning: parallel world generation unavailable ({error})")
            self._executor = None
            self._parallel_failed = True

    def _shutdown_executor(self, cancel=True):
        if self._executor is None:
            return
        for future in list(self._futures):
            if cancel:
                # Discarding a world: never ingest results from the old seed
                # into the new scene's cube handler.
                future.cancel()
            elif future.done():
                self._collect_future(future)
        self._futures.clear()
        self.generating_chunks.clear()
        try:
            self._executor.shutdown(wait=False, cancel_futures=cancel)
        except TypeError:  # Python < 3.9 compatibility
            self._executor.shutdown(wait=False)
        self._executor = None

    def _collect_future(self, future):
        origin = self._futures.pop(future, None)
        if origin is None:
            return 0
        self.generating_chunks.discard(origin)
        try:
            payload = future.result()
        except Exception as error:
            print(f"Warning: chunk generation failed for {origin}: {error}")
            payload = None
        if payload is None:
            # A failed worker must not leave a hole in the world; generate the
            # chunk locally with the same vectorised code.
            self._configure_fastgen()
            payload = gen_worker.generate_chunk(origin)
        self.generated_chunks.add(origin)
        return self._ingest_payload(payload)

    def _submit_origin(self, origin):
        if origin in self.generated_chunks or origin in self.generating_chunks:
            return False
        self.generating_chunks.add(origin)
        future = self._executor.submit(gen_worker.worker_generate, origin)
        self._futures[future] = origin
        return True

    def _gen_parallel(self, max_chunks_per_call, max_blocks_per_call):
        """Submit and harvest vectorised chunk jobs without blocking a frame."""
        columns_generated = 0
        blocks_loaded = 0

        submitted = 0
        while (self.queue and self._executor is not None
               and len(self._futures) < self._max_inflight
               and (max_chunks_per_call <= 0
                    or submitted < max_chunks_per_call)):
            if max_chunks_per_call <= 0:
                break
            origin = self.queue.popleft()
            self.queued_chunks.discard(origin)
            if self._submit_origin(origin):
                submitted += 1

        # Harvest every completed future.  Each one is a complete chunk, so
        # there is no partial-column bookkeeping to do.
        for future in [item for item in self._futures if item.done()]:
            blocks_loaded += self._collect_future(future)
            columns_generated += CHUNK_SIZE[0] * CHUNK_SIZE[2]

        if max_chunks_per_call <= 0 and not self._futures:
            # The initial-load budget is satisfied; return to the incremental
            # path for the remaining background chunks.  Mark the parallel
            # phase complete so later zero-budget calls do not recreate the
            # process pool every frame.
            self._parallel_complete = True
            self._shutdown_executor(cancel=False)
        return columns_generated, blocks_loaded

    def _gen_fast_sequential(self, max_chunks_per_call):
        """In-process fallback used when a process pool is not available."""
        self._configure_fastgen()
        columns_generated = 0
        blocks_loaded = 0
        generated = 0
        if max_chunks_per_call <= 0:
            return columns_generated, blocks_loaded
        while self.queue and generated < max_chunks_per_call:
            origin = self.queue.popleft()
            self.queued_chunks.discard(origin)
            if origin in self.generated_chunks or origin in self.generating_chunks:
                continue
            payload = gen_worker.generate_chunk(origin)
            self.generated_chunks.add(origin)
            blocks_loaded += self._ingest_payload(payload)
            columns_generated += CHUNK_SIZE[0] * CHUNK_SIZE[2]
            generated += 1
        return columns_generated, blocks_loaded

    def _ingest_payload(self, payload):
        """Copy a compact worker result into the live cube handler.

        Worker processes return a *flat* ``uint8`` array to keep the IPC
        payload small and avoid pickling a multi-dimensional view.  In-process
        generation returns the shaped ``(height, chunk_x, chunk_z)`` volume, so
        accept both here.
        """
        origin, block_array = payload
        if block_array.ndim == 1:
            block_array = block_array.reshape(
                (WORLD_MAX_Y - WORLD_MIN_Y + 1, CHUNK_SIZE[0], CHUNK_SIZE[2])
            )
        cubes = getattr(self.gl, "cubes", None)
        if cubes is not None and hasattr(cubes, "add_generated_chunk"):
            return cubes.add_generated_chunk(
                origin, block_array, gen_worker.BLOCK_NAMES, self.MIN_Y
            )

        # Headless fallback (tests/benchmarks): only the save-format dict is
        # required, so avoid creating Cube objects.
        x0, z0 = origin
        ys, xs, zs = np.nonzero(block_array)
        added = 0
        for y, x, z, block_id in zip(
                ys.tolist(), xs.tolist(), zs.tolist(),
                block_array[ys, xs, zs].tolist()):
            name = gen_worker.BLOCK_NAMES[block_id]
            if name == "air":
                continue
            self.blocks[(x0 + x, self.MIN_Y + y, z0 + z)] = name
            added += 1
        return added

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
        rng = random.Random(self._coordinate_seed(x, 0, z, 0xC011))
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
            if self.is_cave(x, block_y, z, y):
                continue
            depth = y - block_y
            material = dirt if depth <= surface_depth else stone
            ore = self._ore_at(x, block_y, z, biome_name) if depth > surface_depth else None
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
        """Drop roughly a quarter of the entries instead of flushing.

        A full clear caused periodic recompute avalanches on every cache
        overflow while travelling; keeping recently inserted entries hot
        removes those hitches without growing the cache past its limit.
        This is purely a performance change and does not affect the values
        that are cached or returned.
        """
        target = max(1, len(cache) - (limit * 3 // 4))
        for key in list(cache.keys())[:target]:
            cache.pop(key, None)

    def _terrain_parameters(self, x, z):
        key = (x, z)
        cached = self._terrain_cache.get(key)
        if cached is not None:
            return cached
        offsets = self._noise_offsets
        noise = self.worldPerlin.noise2d
        continentalness = noise((x + offsets[0]) / 480, (z + offsets[1]) / 480)
        erosion = noise((x + offsets[2]) / 200, (z + offsets[3]) / 200)
        ridge_noise = noise((x + offsets[4]) / 120, (z + offsets[5]) / 120)
        detail = noise((x + offsets[6]) / 45, (z + offsets[7]) / 45)
        valley = abs(noise((x + offsets[8]) / 140, (z + offsets[9]) / 140))
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
        height = self.SEA_LEVEL + continentalness * 18 + detail * 5
        height += land * max(0.0, ridge - 0.48) / 0.52 * erosion_factor * 55
        height -= land * max(0.0, 0.16 - valley) / 0.16 * 10
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
            if height >= 115:
                biome = "big_mountains"
            elif height >= 90:
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
        openness = self._clamp((depth - 5) / 48, 0.0, 1.0)
        cheese = noise((x + offsets[0]) / 44, (y + offsets[14]) / 34,
                       (z + offsets[1]) / 44)
        threshold = 0.62 if depth < 5 else 0.46 - openness * 0.10
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