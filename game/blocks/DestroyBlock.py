import math
import os
import pyglet
from OpenGL.GL import *

class DestroyBlock:
    BLOCK_HARDNESS = {
        "grass": 0.6,
        "dirt": 0.5,
        "gravel": 0.6,
        "sand": 0.5,
        "sandstone": 0.8,
        "stone": 1.5,
        "cobblestone": 2.0,
        "brick": 2.0,
        "glass": 0.3,
        "glowstone": 0.3,
        "iron_block": 5.0,
        "planks_oak": 2.0,
        "crafting_table": 2.5,
        "cactus": 0.4,
        "sapling": 0.0,
        "tnt": 0.0,
        "ancient_debris": 30.0,
        "bone_block": 2.0,
        "cow": 0.5,
        "clouds": 0.2,
        "nocolor": 1.0,
        "bedrock": None,
        "water": None,
        "lava": None,
        "debug": None,
    }
    TOOL_REQUIRED = {
        "stone", "cobblestone", "brick", "sandstone", "glowstone",
        "iron_block", "bone_block", "ancient_debris",
    }

    def __init__(self, gl):
        self.gl = gl
        self.destroyStage = -1
        self.textures = {}
        self.destroyPos = [0, 0, 0]
        self.loadTextures()

    def loadTextures(self):
        print("Loading block destroy textures...")
        for e, i in enumerate(sorted(os.listdir("textures/blocks/block_destroy"))):
            self.textures[e] = \
                pyglet.graphics.TextureGroup(pyglet.image.load("textures/blocks/block_destroy/" + i)
                                             .get_mipmapped_texture())
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

    def drawDestroy(self, ox, oy, oz):
        if self.destroyStage == -1:
            return

        s = 1.01
        x, y, z = ox + s / 2, oy + s / 2, oz + s / 2
        X, Y, Z = x - s, y - s, z - s

        vertexes = [
            (X, y, z, x, y, z, x, Y, z, X, Y, z),
            (x, y, Z, X, y, Z, X, Y, Z, x, Y, Z),
            (x, y, z, x, y, Z, x, Y, Z, x, Y, z),
            (X, y, Z, X, y, z, X, Y, z, X, Y, Z),
            (x, y, z, X, y, z, X, y, Z, x, y, Z),
            (x, Y, Z, X, Y, Z, X, Y, z, x, Y, z),
        ]

        tex_coords = ('t2f', (0, 0, 1, 0, 1, 1, 0, 1))
        mode = GL_QUADS
        stg = int(self.destroyStage)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[0]), tex_coords)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[1]), tex_coords)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[2]), tex_coords)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[3]), tex_coords)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[4]), tex_coords)
        self.gl.stuffBatch.add(4, mode, self.textures[stg], ('v3f', vertexes[5]), tex_coords)

    def destroy(self, blockName, blockByVec, dt):
        if self.destroyStage == -1 or blockByVec[0] != self.destroyPos:
            self.destroyStage = 0
            self.destroyPos = blockByVec[0]

        break_time = self.get_break_time(blockName)
        if break_time is None:
            self.destroyStage = -1
            return

        if break_time == 0:
            self.destroyStage = 10
        else:
            self.destroyStage += dt * 10 / break_time

        if self.destroyStage >= 10 - 1e-9:
            self.destroyStage = -1
            cube = self.gl.cubes.cubes.get(blockByVec[0])
            if cube is None:
                return
            print(cube.name)
            if cube.name == "leaves_oak":
                self.gl.droppedBlock.addBlock(blockByVec[0], "sapling")
            else:
                self.gl.droppedBlock.addBlock(blockByVec[0], cube.name)

            self.gl.blockSound.playBlockSound(cube.name)
            self.gl.particles.addParticle(cube.p, cube, direction="down")
            self.gl.cubes.remove(blockByVec[0])

    @classmethod
    def get_break_time(cls, block_name):
        if block_name.endswith("_ore"):
            hardness = 3.0
            requires_tool = True
        elif block_name.endswith("_wool"):
            hardness = 0.8
            requires_tool = False
        elif block_name.startswith("log_"):
            hardness = 2.0
            requires_tool = False
        elif block_name.startswith("leaves_"):
            hardness = 0.2
            requires_tool = False
        else:
            hardness = cls.BLOCK_HARDNESS.get(block_name, 1.0)
            requires_tool = block_name in cls.TOOL_REQUIRED

        if hardness is None:
            return None
        if hardness == 0:
            return 0

        ticks = math.ceil(hardness * (100 if requires_tool else 30))
        return max(1, ticks) / 20
