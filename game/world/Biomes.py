all_biomes = ["forest", "desert", "ocean", "taiga", "mountains", "big_mountains", "plains"]

WATER_COLORS = {
    "forest": (0x3F, 0x76, 0xE4),
    "desert": (0x3F, 0x76, 0xE4),
    "ocean": (0x43, 0xD5, 0xEE),
    "taiga": (0x3D, 0x57, 0xD6),
    "mountains": (0x3F, 0x76, 0xE4),
    "big_mountains": (0x39, 0x38, 0xC9),
    "plains": (0x3F, 0x76, 0xE4),
}

WATER_FOG_COLORS = {
    "ocean": (0x04, 0x1F, 0x33),
    "forest": (0x05, 0x05, 0x33),
    "desert": (0x05, 0x05, 0x33),
    "taiga": (0x05, 0x05, 0x33),
    "mountains": (0x05, 0x05, 0x33),
    "big_mountains": (0x05, 0x05, 0x33),
    "plains": (0x05, 0x05, 0x33),
}


def getBiomeByTemp(temp):
    temp = float(temp)
    """
    Classic alpha 1.2.3-like climate bands:
    - hotter = desert / ocean edge
    - moderate = forest
    - cold = taiga
    - very cold = mountains / big mountains
    """
    if temp >= 24:
        return all_biomes[2]  # ocean
    if temp >= 12:
        return all_biomes[1]  # desert
    if temp >= 7:
        return all_biomes[6]  # plains
    if temp >= 2:
        return all_biomes[0]  # forest
    if temp >= -8:
        return all_biomes[3]  # taiga
    if temp >= -30:
        return all_biomes[4]  # mountains
    return all_biomes[5]  # big mountains


class Biomes:
    def __init__(self, biome):
        self.biome = biome

    def getBiomeGrass(self):
        if self.biome == "desert":
            return "sand"
        if self.biome == "ocean":
            return "sand"
        if self.biome == "forest" :
            return "grass"
        if self.biome == "plains":
            return "grass"
        if self.biome == "taiga":
            return "grass"
        if self.biome == "mountains":
            return "grass"
        if self.biome == "big_mountains":
            return "stone"
        return "grass"

    def getBiomePlant(self):
        if self.biome == "desert":
            return "cactus"
        if self.biome == "plains":
            return "tall_grass"

    def getBiomeDirt(self):
        if self.biome == "desert":
            return "sand"
        if self.biome == "forest" or self.biome == "plains" or self.biome == "taiga" or self.biome == "mountains" \
                or self.biome == "big_mountains":
            return "dirt"
        if self.biome == "ocean":
            return "sand"
        return "dirt"

    def getBiomeStone(self):
        if self.biome == "desert":
            return "sandstone"
        if self.biome == "forest" or self.biome == "plains" or self.biome == "taiga" or self.biome == "mountains":
            return "stone"
        if self.biome == "ocean":
            return "gravel"
        if self.biome == "big_mountains":
            return "stone"
        return "stone"

    def getWaterColor(self):
        return WATER_COLORS.get(self.biome, WATER_COLORS["forest"])

    def getWaterFogColor(self):
        return WATER_FOG_COLORS.get(self.biome, WATER_FOG_COLORS["forest"])
