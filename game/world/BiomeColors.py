"""Minecraft 1.20.1 biome colormap tinting.

Grass and foliage colours are sampled from ``textures/colormap/grass.png`` and
``textures/colormap/foliage.png`` using Minecraft's exact lookup:

    temperature = clamp(temperature, 0, 1)
    downfall    = clamp(downfall, 0, 1) * temperature
    x = (1 - temperature) * 255
    y = (1 - downfall)    * 255

Because this project's grass/leaf textures already have green baked in (unlike
Minecraft's grayscale ones), the sampled colour is normalised against a
reference biome. Tinting therefore shifts hue between biomes without
double-darkening the artwork.
"""

import os

from game.world.Biomes import all_biomes

# temperature / downfall per biome, mirroring Minecraft's biome definitions
BIOME_CLIMATE = {
    "forest": (0.7, 0.8),
    "desert": (2.0, 0.0),
    "ocean": (0.5, 0.5),
    "taiga": (0.25, 0.8),
    "mountains": (0.2, 0.3),
    "big_mountains": (0.0, 0.5),
}

# plains-like reference, matching the tone the textures were authored at
REFERENCE_CLIMATE = (0.8, 0.4)

DEFAULT_GRASS = (145, 189, 89)
DEFAULT_FOLIAGE = (119, 171, 47)

GRASS_TINTED_BLOCKS = ("grass", "tall_grass")
FOLIAGE_TINTED_BLOCKS = ("leaves_oak", "leaves_taiga", "sapling")

# Grayscale (vanilla 1.20.1) art takes the raw colormap colour, exactly like
# Minecraft. Textures that already have green baked in are normalised against a
# reference biome instead, so they shift hue without being double-darkened.
GRAYSCALE_BLOCKS = {"grass"}


def _clamp01(value):
    return max(0.0, min(1.0, value))


class ColorMap:
    """A 256x256 Minecraft colormap with Minecraft's sampling rules."""

    def __init__(self, path, default):
        self.default = default
        self.pixels = None
        self.width = 0
        self.height = 0
        self._load(path)

    def _load(self, path):
        if not os.path.isfile(path):
            return
        try:
            from PIL import Image
        except ImportError:
            Image = None

        if Image is not None:
            image = Image.open(path).convert("RGB")
            self.width, self.height = image.size
            self.pixels = list(image.getdata())
            return

        try:
            import pyglet
        except ImportError:
            return

        image = pyglet.image.load(path)
        self.width, self.height = image.width, image.height
        data = image.get_image_data()
        raw = data.get_data("RGB", self.width * 3)
        # pyglet rows run bottom-to-top; flip so row 0 is the top row
        rows = [raw[y * self.width * 3:(y + 1) * self.width * 3] for y in range(self.height)]
        rows.reverse()
        pixels = []
        for row in rows:
            for x in range(self.width):
                offset = x * 3
                pixels.append((row[offset], row[offset + 1], row[offset + 2]))
        self.pixels = pixels

    def sample(self, temperature, downfall):
        if not self.pixels:
            return self.default

        temperature = _clamp01(temperature)
        downfall = _clamp01(downfall) * temperature
        x = int((1.0 - temperature) * (self.width - 1))
        y = int((1.0 - downfall) * (self.height - 1))
        x = max(0, min(self.width - 1, x))
        y = max(0, min(self.height - 1, y))
        return self.pixels[y * self.width + x]


class BiomeColorProvider:
    """Resolves per-biome grass and foliage tint multipliers."""

    def __init__(self, directory=os.path.join("textures", "colormap")):
        self.grass_map = ColorMap(os.path.join(directory, "grass.png"), DEFAULT_GRASS)
        self.foliage_map = ColorMap(os.path.join(directory, "foliage.png"), DEFAULT_FOLIAGE)

        reference_temp, reference_rain = REFERENCE_CLIMATE
        self._grass_reference = self.grass_map.sample(reference_temp, reference_rain)
        self._foliage_reference = self.foliage_map.sample(reference_temp, reference_rain)

        self._grass_cache = {}
        self._foliage_cache = {}

    @property
    def loaded(self):
        return bool(self.grass_map.pixels) and bool(self.foliage_map.pixels)

    def grass_color(self, biome):
        if biome not in self._grass_cache:
            temperature, downfall = BIOME_CLIMATE.get(biome, REFERENCE_CLIMATE)
            self._grass_cache[biome] = self.grass_map.sample(temperature, downfall)
        return self._grass_cache[biome]

    def foliage_color(self, biome):
        if biome not in self._foliage_cache:
            temperature, downfall = BIOME_CLIMATE.get(biome, REFERENCE_CLIMATE)
            self._foliage_cache[biome] = self.foliage_map.sample(temperature, downfall)
        return self._foliage_cache[biome]

    def _multiplier(self, color, reference):
        return tuple(
            _clamp01(channel / reference_channel) if reference_channel else 1.0
            for channel, reference_channel in zip(color, reference)
        )

    def grass_multiplier(self, biome):
        return self._multiplier(self.grass_color(biome), self._grass_reference)

    def foliage_multiplier(self, biome):
        return self._multiplier(self.foliage_color(biome), self._foliage_reference)

    def _direct(self, color):
        return tuple(channel / 255.0 for channel in color)

    def block_multiplier(self, block_name, biome):
        """Tint multiplier for a block, or ``None`` when it is not tinted."""
        if block_name in GRASS_TINTED_BLOCKS:
            if block_name in GRAYSCALE_BLOCKS:
                return self._direct(self.grass_color(biome))
            return self.grass_multiplier(biome)
        if block_name in FOLIAGE_TINTED_BLOCKS:
            if block_name in GRAYSCALE_BLOCKS:
                return self._direct(self.foliage_color(biome))
            return self.foliage_multiplier(biome)
        return None

    def grass_overlay_multiplier(self, biome):
        """Tint for the grayscale side overlay: always the raw biome colour."""
        return self._direct(self.grass_color(biome))


def is_tinted(block_name):
    return block_name in GRASS_TINTED_BLOCKS or block_name in FOLIAGE_TINTED_BLOCKS
