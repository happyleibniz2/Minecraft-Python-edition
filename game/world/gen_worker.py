"""Vectorised, process-safe chunk generation.

This module deliberately imports *only* NumPy and the lightweight noise
module.  It must not import ``settings`` (which loads game configuration and
pyglet font resources) so that it can be used as a ``ProcessPoolExecutor``
worker without recreating the game.

The public surface is intentionally small:

``configure(...)``
    Install the seed / world constants in the current process.

``generate_chunk(origin)``
    Return ``(origin, uint8 array)`` for one 4x4 column chunk.

``worker_init(...)`` / ``worker_generate(origin)``
    Picklable wrappers used by the process pool.
"""

import math
import random

import numpy as np

from game.world.PerlinNoise import PerlinNoise


# Block palette used by the fast path.  IDs are stable for a single world and
# are only exchanged between the parent and its worker processes.
BLOCK_NAMES = (
    "air",              # 0
    "bedrock",          # 1
    "stone",            # 2
    "grass",            # 3
    "dirt",             # 4
    "sand",             # 5
    "sandstone",        # 6
    "gravel",           # 7
    "water",            # 8
    "log_oak",          # 9
    "leaves_oak",       # 10
    "tall_grass",       # 11
    "cactus",           # 12
    "diamond_ore",      # 13
    "redstone_ore",     # 14
    "gold_ore",         # 15
    "iron_ore",         # 16
    "lapis_ore",        # 17
    "coal_ore",         # 18
    "emerald_ore",      # 19
)
BLOCK_IDS = {name: index for index, name in enumerate(BLOCK_NAMES)}

_AIR = BLOCK_IDS["air"]
_BEDROCK = BLOCK_IDS["bedrock"]
_STONE = BLOCK_IDS["stone"]
_GRASS = BLOCK_IDS["grass"]
_DIRT = BLOCK_IDS["dirt"]
_SAND = BLOCK_IDS["sand"]
_SANDSTONE = BLOCK_IDS["sandstone"]
_GRAVEL = BLOCK_IDS["gravel"]
_WATER = BLOCK_IDS["water"]
_LOG = BLOCK_IDS["log_oak"]
_LEAVES = BLOCK_IDS["leaves_oak"]
_TALL_GRASS = BLOCK_IDS["tall_grass"]
_CACTUS = BLOCK_IDS["cactus"]
_DIAMOND = BLOCK_IDS["diamond_ore"]
_REDSTONE = BLOCK_IDS["redstone_ore"]
_GOLD = BLOCK_IDS["gold_ore"]
_IRON = BLOCK_IDS["iron_ore"]
_LAPIS = BLOCK_IDS["lapis_ore"]
_COAL = BLOCK_IDS["coal_ore"]
_EMERALD = BLOCK_IDS["emerald_ore"]

# Biome codes (kept local so the worker does not import game.world.Biomes).
_OCEAN = 0
_BIG_MOUNTAINS = 1
_MOUNTAINS = 2
_DESERT = 3
_TAIGA = 4
_FOREST = 5
_PLAINS = 6

# Lookup tables indexed by biome code.
_GRASS_LOOKUP = np.array(
    [_SAND, _STONE, _GRASS, _SAND, _GRASS, _GRASS, _GRASS], dtype=np.uint8
)
_DIRT_LOOKUP = np.array(
    [_SAND, _DIRT, _DIRT, _SAND, _DIRT, _DIRT, _DIRT], dtype=np.uint8
)
_STONE_LOOKUP = np.array(
    [_GRAVEL, _STONE, _STONE, _SANDSTONE, _STONE, _STONE, _STONE], dtype=np.uint8
)
_TREE_CHANCE = np.array([70, 70, 70, 70, 50, 50, 70], dtype=np.int64)
_IS_OCEAN = np.array([1, 0, 0, 0, 0, 0, 0], dtype=bool)
_IS_WOODLAND = np.array([0, 0, 0, 0, 1, 1, 0], dtype=bool)
_PLANT_LOOKUP = np.array(
    [0, 0, 0, _CACTUS, 0, 0, _TALL_GRASS], dtype=np.uint8
)

_MASK64 = np.uint64(0xFFFFFFFFFFFFFFFF)
_C1 = np.uint64(0x9E3779B185EBCA87)
_C2 = np.uint64(0xC2B2AE3D27D4EB4F)
_C3 = np.uint64(0x165667B19E3779F9)
_M1 = np.uint64(0xBF58476D1CE4E5B9)
_M2 = np.uint64(0x94D049BB133111EB)
_S30 = np.uint64(30)
_S27 = np.uint64(27)
_S31 = np.uint64(31)
_INV_2_64 = 1.0 / float(1 << 64)

# ---------------------------------------------------------------------------
# Process-wide configuration
# ---------------------------------------------------------------------------
_SEED = 0
_OFFSETS = (0.0,) * 16
_WORLD_NOISE = None
_BIOME_NOISE = None
_CHUNK_SIZE = (4, 384, 4)
_MIN_Y = -64
_MAX_Y = 319
_SEA_LEVEL = 63
_HEIGHT = _MAX_Y - _MIN_Y + 1
_MARGIN = 2


def configure(seed, offsets, chunk_size, min_y, max_y, sea_level,
              world_noise=None, biome_noise=None):
    """Install the constants used by :func:`generate_chunk`."""
    global _SEED, _OFFSETS, _CHUNK_SIZE, _MIN_Y, _MAX_Y, _SEA_LEVEL
    global _HEIGHT, _WORLD_NOISE, _BIOME_NOISE
    _SEED = int(seed)
    _OFFSETS = tuple(float(value) for value in offsets)
    _CHUNK_SIZE = tuple(int(value) for value in chunk_size)
    _MIN_Y = int(min_y)
    _MAX_Y = int(max_y)
    _SEA_LEVEL = int(sea_level)
    _HEIGHT = _MAX_Y - _MIN_Y + 1
    _WORLD_NOISE = world_noise or PerlinNoise(_SEED, mh=8)
    _BIOME_NOISE = biome_noise or PerlinNoise(_SEED ** 2, mh=10)


def worker_init(seed, offsets, chunk_size, min_y, max_y, sea_level):
    configure(seed, offsets, chunk_size, min_y, max_y, sea_level)


def worker_generate(origin):
    """Process-pool entry point: ship a flat uint8 block-ID array."""
    origin, volume = generate_chunk(origin)
    return origin, volume.reshape(-1)


# ---------------------------------------------------------------------------
# Scalar helpers (kept bit-identical to worldGenerator's versions)
# ---------------------------------------------------------------------------
def coordinate_seed(seed, x, y, z, salt=0):
    value = (seed ^ salt ^ (x * 0x9E3779B185EBCA87)
             ^ (y * 0xC2B2AE3D27D4EB4F) ^ (z * 0x165667B19E3779F9))
    value &= (1 << 64) - 1
    value ^= value >> 30
    value = (value * 0xBF58476D1CE4E5B9) & ((1 << 64) - 1)
    value ^= value >> 27
    value = (value * 0x94D049BB133111EB) & ((1 << 64) - 1)
    return value ^ (value >> 31)


def _smoothstep(low, high, value):
    value = np.clip((value - low) / (high - low), 0.0, 1.0)
    return value * value * (3.0 - 2.0 * value)


def _coordinate_seed_many(x, y, z, salt):
    x = np.asarray(x, dtype=np.int64).astype(np.uint64)
    y = np.asarray(y, dtype=np.int64).astype(np.uint64)
    z = np.asarray(z, dtype=np.int64).astype(np.uint64)
    value = (np.uint64(_SEED) ^ np.uint64(salt)
             ^ (x * _C1) ^ (y * _C2) ^ (z * _C3))
    value &= _MASK64
    value ^= value >> _S30
    value = (value * _M1) & _MASK64
    value ^= value >> _S27
    value = (value * _M2) & _MASK64
    return value ^ (value >> _S31)


def _random_at_many(x, y, z, salt):
    return _coordinate_seed_many(x, y, z, salt).astype(np.float64) * _INV_2_64


# ---------------------------------------------------------------------------
# Terrain fields
# ---------------------------------------------------------------------------
def sample_height_many(x, z):
    offsets = _OFFSETS
    noise = _WORLD_NOISE.noise2d_many
    continentalness = noise((x + offsets[0]) / 480, (z + offsets[1]) / 480)
    erosion = noise((x + offsets[2]) / 200, (z + offsets[3]) / 200)
    ridge_noise = noise((x + offsets[4]) / 120, (z + offsets[5]) / 120)
    detail = noise((x + offsets[6]) / 45, (z + offsets[7]) / 45)
    valley = np.abs(noise((x + offsets[8]) / 140, (z + offsets[9]) / 140))

    land = _smoothstep(-0.18, 0.28, continentalness)
    ridge = np.maximum(0.0, 1.0 - np.abs(ridge_noise) * 1.8)
    erosion_factor = np.clip(0.65 - erosion, 0.0, 1.25)
    height = _SEA_LEVEL + continentalness * 18 + detail * 5
    height += land * np.maximum(0.0, ridge - 0.48) / 0.52 * erosion_factor * 55
    height -= land * np.maximum(0.0, 0.16 - valley) / 0.16 * 10
    height = np.where(
        continentalness < -0.16,
        _SEA_LEVEL - 5 + (continentalness + 0.16) * 72 + detail * 5,
        height,
    )
    height = np.round(np.clip(height, _MIN_Y + 5, _MAX_Y - 16))
    return height.astype(np.int64)


def sample_biome_many(x, z, height):
    offsets = _OFFSETS
    climate = _BIOME_NOISE.noise2d_many
    temperature = climate((x + offsets[10]) / 260, (z + offsets[11]) / 260)
    humidity = climate((x + offsets[12]) / 220, (z + offsets[13]) / 220)

    land_biome = np.select(
        (
            height >= 115,
            height >= 90,
            (temperature > 0.24) & (humidity < 0.08),
            temperature < -0.22,
            humidity > 0.14,
        ),
        (_BIG_MOUNTAINS, _MOUNTAINS, _DESERT, _TAIGA, _FOREST),
        default=_PLAINS,
    )
    return np.where(height < _SEA_LEVEL, _OCEAN, land_biome).astype(np.int64)


def cave_mask_many(x, y, z, surface):
    """Vectorised ``worldGenerator.is_cave`` for arbitrary point arrays."""
    offsets = _OFFSETS
    noise = _WORLD_NOISE.noise_many
    valid = (y > _MIN_Y + 4) & (y <= surface)
    depth = surface - y
    openness = np.clip((depth - 5) / 48.0, 0.0, 1.0)

    cheese = noise((x + offsets[0]) / 44.0, (y + offsets[14]) / 34.0,
                   (z + offsets[1]) / 44.0)
    threshold = np.where(depth < 5, 0.62, 0.46 - openness * 0.10)
    tunnel_a = np.abs(noise((x + offsets[4]) / 23.0, (y + offsets[15]) / 19.0,
                            (z + offsets[5]) / 23.0))
    tunnel_b = np.abs(noise((x + offsets[8]) / 27.0, (y - offsets[14]) / 21.0,
                            (z + offsets[9]) / 27.0))

    carved = (cheese > threshold) | (
        (tunnel_a < 0.045) & (tunnel_b < 0.045)
    )
    return valid & carved


def ore_ids_many(x, y, z, biome):
    """Vectorised ``worldGenerator._ore_at``; returns 0 for no ore."""
    selector = _random_at_many(x // 2, y // 2, z // 2, 0x0AE)
    eligible = _random_at_many(x, y, z, 0x0AF) < 0.72
    chosen = np.zeros(x.shape, dtype=np.uint8)
    cumulative = np.zeros(x.shape, dtype=np.float64)

    def consider(mask, chance, block_id):
        nonlocal cumulative
        cumulative = cumulative + np.where(mask, chance, 0.0)
        take = eligible & (chosen == 0) & (selector < cumulative)
        chosen[take] = block_id

    deep = y <= 16
    depth_factor = np.clip((16 - y) / 80.0, 0.0, 1.0)
    consider(deep, 0.0015 + depth_factor * 0.007, _DIAMOND)
    consider(deep, 0.002 + depth_factor * 0.008, _REDSTONE)
    consider(y <= 32, np.full(x.shape, 0.004), _GOLD)
    iron_factor = np.clip(1.0 - np.abs(y - 16) / 96.0, 0.0, 1.0)
    consider(np.ones(x.shape, dtype=bool), 0.002 + iron_factor * 0.012, _IRON)
    lapis_factor = np.clip(1.0 - np.abs(y) / 64.0, 0.0, 1.0)
    consider(np.ones(x.shape, dtype=bool), lapis_factor * 0.005, _LAPIS)
    coal_factor = np.clip(1.0 - np.abs(y - 96) / 128.0, 0.0, 1.0)
    consider(np.ones(x.shape, dtype=bool), coal_factor * 0.014, _COAL)
    mountain = (biome == _MOUNTAINS) | (biome == _BIG_MOUNTAINS)
    consider(mountain & (y >= -16) & (y <= 256),
             np.full(x.shape, 0.004), _EMERALD)
    return chosen


# ---------------------------------------------------------------------------
# Block placement helpers
# ---------------------------------------------------------------------------
def _set_if_air(out, x, y, z, block_id, x0, z0):
    local_x = x - x0
    local_z = z - z0
    if not (0 <= local_x < _CHUNK_SIZE[0] and 0 <= local_z < _CHUNK_SIZE[2]):
        return
    local_y = y - _MIN_Y
    if 0 <= local_y < _HEIGHT and out[local_y, local_x, local_z] == _AIR:
        out[local_y, local_x, local_z] = block_id


def _place_tree(out, rng, x, y, z, x0, z0):
    tree_height = rng.randint(5, 7)
    for i in range(y + 1, y + tree_height + 1):
        _set_if_air(out, x, i, z, _LOG, x0, z0)
    for i in range(x - 2, x + 3):
        for j in range(z - 2, z + 3):
            for k in range(y + tree_height - 2, y + tree_height):
                _set_if_air(out, i, k, j, _LEAVES, x0, z0)
    for i in range(tree_height, tree_height + 1):
        for j in range(-1, 2):
            for k in range(-1, 2):
                _set_if_air(out, x + j, y + i, z + k, _LEAVES, x0, z0)
    cl = 2
    for i in range(tree_height + 1, tree_height + 2):
        for j in range(-1, 2):
            for k in range(-1, 2):
                if cl % 2 != 0:
                    _set_if_air(out, x + j, y + i, z + k, _LEAVES, x0, z0)
                cl += 1
    _set_if_air(out, x, y + tree_height + 1, z, _LEAVES, x0, z0)


# ---------------------------------------------------------------------------
# Chunk generation
# ---------------------------------------------------------------------------
def generate_chunk(origin):
    """Generate one ``CHUNK_SIZE`` column chunk as a compact uint8 volume.

    The returned array has shape ``(height, chunk_x, chunk_z)``.  ``height``
    spans ``WORLD_MIN_Y..WORLD_MAX_Y``; index 0 is the bottom of the world.
    """
    x0, z0 = int(origin[0]), int(origin[1])
    size_x, _, size_z = _CHUNK_SIZE

    # A two-block margin is enough for oak leaves (radius 2) to cross a chunk
    # border.  Each chunk therefore computes the trees rooted just outside its
    # own columns and clips their blocks to the local volume.
    margin = _MARGIN
    xs = np.arange(x0 - margin, x0 + size_x + margin, dtype=np.int64)
    zs = np.arange(z0 - margin, z0 + size_z + margin, dtype=np.int64)
    grid_x, grid_z = np.meshgrid(xs, zs, indexing="ij")
    flat_x = grid_x.ravel()
    flat_z = grid_z.ravel()

    heights = sample_height_many(flat_x, flat_z)
    biomes = sample_biome_many(flat_x, flat_z, heights)
    surface_open = cave_mask_many(flat_x, heights, flat_z, heights)
    surface_open &= ~_IS_OCEAN[biomes]

    out = np.zeros((_HEIGHT, size_x, size_z), dtype=np.uint8)

    # Columns that actually live inside this chunk are filled in bulk below.
    output_columns = []
    output_heights = []
    output_depths = []
    output_biomes = []
    output_dirt = []
    output_stone = []
    output_rngs = []

    for index in range(flat_x.size):
        x = int(flat_x[index])
        z = int(flat_z[index])
        height = int(heights[index])
        biome = int(biomes[index])
        is_ocean = bool(_IS_OCEAN[biome])
        is_woodland = bool(_IS_WOODLAND[biome])
        open_surface = bool(surface_open[index])
        inside = (x0 <= x < x0 + size_x and z0 <= z < z0 + size_z)

        rng = random.Random(coordinate_seed(_SEED, x, 0, z, 0xC011))
        spawn_tree = (
            rng.randint(0, int(_TREE_CHANCE[biome])) == 20
            and height > _SEA_LEVEL + 1
            and not is_ocean
        )

        if not open_surface and spawn_tree and is_woodland:
            _place_tree(out, rng, x, height, z, x0, z0)
        elif inside:
            plant = int(_PLANT_LOOKUP[biome])
            if not open_surface and plant == _TALL_GRASS and rng.randint(0, 6) == 0:
                _set_if_air(out, x, height + 1, z, _TALL_GRASS, x0, z0)
            elif not open_surface and plant == _CACTUS and rng.randint(0, 31) == 0:
                for cactus_y in range(height + 1,
                                      height + rng.randint(2, 3) + 1):
                    _set_if_air(out, x, cactus_y, z, _CACTUS, x0, z0)

        if not inside:
            continue

        local_x = x - x0
        local_z = z - z0
        if not open_surface:
            out[height - _MIN_Y, local_x, local_z] = (
                _STONE_LOOKUP[biome] if is_ocean else _GRASS_LOOKUP[biome]
            )
        if is_ocean:
            out[height + 1 - _MIN_Y:_SEA_LEVEL + 1 - _MIN_Y,
                local_x, local_z] = _WATER

        output_columns.append((x, z, local_x, local_z))
        output_heights.append(height)
        output_depths.append(rng.randint(3, 5))
        output_biomes.append(biome)
        output_dirt.append(int(_DIRT_LOOKUP[biome]))
        output_stone.append(int(_STONE_LOOKUP[biome]))
        output_rngs.append(rng)

    # Bulk underground pass: one vectorised cave/ore evaluation for all
    # underground voxels in this chunk.
    if output_columns:
        counts = np.array(
            [height - _MIN_Y for height in output_heights], dtype=np.int64
        )
        total = int(counts.sum())
        if total:
            flat_y = np.empty(total, dtype=np.int64)
            flat_x = np.empty(total, dtype=np.int64)
            flat_z = np.empty(total, dtype=np.int64)
            surface = np.empty(total, dtype=np.int64)
            depth_limit = np.empty(total, dtype=np.int64)
            dirt_ids = np.empty(total, dtype=np.uint8)
            stone_ids = np.empty(total, dtype=np.uint8)
            biome_ids = np.empty(total, dtype=np.int64)

            cursor = 0
            for index, (x, z, _lx, _lz) in enumerate(output_columns):
                count = int(counts[index])
                end = cursor + count
                flat_x[cursor:end] = x
                flat_z[cursor:end] = z
                flat_y[cursor:end] = np.arange(_MIN_Y, output_heights[index])
                surface[cursor:end] = output_heights[index]
                depth_limit[cursor:end] = output_depths[index]
                dirt_ids[cursor:end] = output_dirt[index]
                stone_ids[cursor:end] = output_stone[index]
                biome_ids[cursor:end] = output_biomes[index]
                cursor = end

            depth = surface - flat_y
            material = np.where(depth <= depth_limit, dirt_ids, stone_ids)
            ore = ore_ids_many(flat_x, flat_y, flat_z, biome_ids)
            material = np.where((depth > depth_limit) & (ore != 0), ore, material)
            carved = cave_mask_many(flat_x, flat_y, flat_z, surface)
            material[carved] = _AIR

            local_x = flat_x - x0
            local_z = flat_z - z0
            local_y = flat_y - _MIN_Y
            out[local_y, local_x, local_z] = material

        # Bedrock is applied last, mirroring the original column loop where it
        # short-circuits before the cave/material checks.  The four random
        # draws continue the same per-column RNG sequence used for the
        # surface depth.
        for index, (_x, _z, local_x, local_z) in enumerate(output_columns):
            out[0, local_x, local_z] = _BEDROCK
            rng = output_rngs[index]
            for block_y in range(_MIN_Y + 1, _MIN_Y + 5):
                chance = (_MIN_Y + 5 - block_y) / 5.0
                if rng.random() < chance:
                    out[block_y - _MIN_Y, local_x, local_z] = _BEDROCK

    return (x0, z0), out
