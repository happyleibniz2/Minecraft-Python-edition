all_biomes = ["forest", "desert", "ocean", "taiga", "mountains", "big_mountains"]


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
            return "water"
        if self.biome == "forest" :
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

    def getBiomeDirt(self):
        if self.biome == "desert":
            return "sand"
        if self.biome == "forest" or self.biome == "taiga" or self.biome == "mountains" \
                or self.biome == "big_mountains":
            return "dirt"
        if self.biome == "ocean":
            return "water"
        return "dirt"

    def getBiomeStone(self):
        if self.biome == "desert":
            return "sandstone"
        if self.biome == "forest" or self.biome == "taiga" or self.biome == "mountains":
            return "stone"
        if self.biome == "ocean":
            return "gravel"
        if self.biome == "big_mountains":
            return "stone"
        return "stone"
