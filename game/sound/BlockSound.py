from random import randint
import traceback
import logging
from game.sound.SoundPhysics import SoundPhysics

class BlockSound:
    def __init__(self, gl):
        self.gl = gl
        self.cntr = 0
        self.pickUpAlreadyPlayed = False
        self.physics = SoundPhysics(gl)

    def _safe_set_volume(self, chnl, position=None):
        if chnl is not None:
            try:
                self.physics.apply(chnl, position, self.gl.sound.volume)
            except Exception as e:
                print(e)
                print("Beginning Error Report...")
                print("at ", end=" ")
                print(traceback.format_exc())
                print("End Error Report")

    def getBlockSound(self, blockName):
        blName = "grass"

        if blockName == "grass" or blockName == "tnt" or blockName.startswith("leaves"):
            blName = "grass"
        if blockName == "stone" or blockName == "bedrock" or blockName == "brick" or blockName.endswith("ore"):
            blName = "stone"
        if blockName == "dirt" or blockName == "gravel":
            blName = "gravel"
        if blockName == "sand":
            blName = "sand"
        if blockName.startswith("log") or blockName == "crafting_table":
            blName = "wood"
        if blockName.endswith("wool"):
            blName = "cloth"

        return blName

    def damageByBlock(self, blockName, hp):
        sound = self.gl.sound.SOUNDS["damage"]["fallbig"][0]

        if blockName.endswith("wool"):
            sound = self.gl.sound.SOUNDS["damage"]["fallsmall"][0]
        if hp > 0:
            bl = len(self.gl.sound.SOUNDS["damage"]["hit"])
            sound = self.gl.sound.SOUNDS["damage"]["hit"][randint(0, bl - 1)]

        chnl = sound.play()
        self._safe_set_volume(chnl)

    def playStepSound(self, blockName, custom=300, position=None):
        self.cntr += 1
        if self.cntr % custom != 0 or self.cntr == 0:
            return
        blName = self.getBlockSound(blockName)

        bl = len(self.gl.sound.BLOCKS_SOUND["step"][blName])
        chnl = self.gl.sound.BLOCKS_SOUND["step"][blName][randint(0, bl - 1)].play()
        self._safe_set_volume(chnl, position)

    def playBoomSound(self, position=None):
        bl = len(self.gl.sound.BLOCKS_SOUND["explode"])
        chnl = self.gl.sound.BLOCKS_SOUND["explode"][randint(0, bl - 1)].play()
        self._safe_set_volume(chnl, position)

    def playBlockSound(self, blockName, position=None):
        blName = self.getBlockSound(blockName)

        bl = len(self.gl.sound.BLOCKS_SOUND["dig"][blName])
        chnl = self.gl.sound.BLOCKS_SOUND["dig"][blName][randint(0, bl - 1)].play()
        self._safe_set_volume(chnl, position)

    def playPickUpSound(self):
        if not self.pickUpAlreadyPlayed:
            chnl = self.gl.sound.BLOCKS_SOUND["pickUp"].play()
            self._safe_set_volume(chnl)
            self.pickUpAlreadyPlayed = True

# BUG WHEN PLAYING TODO
# <UNDONE> chnl.set_volume(self.gl.sound.volume)
#             ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^
# AttributeError: 'NoneType' object has no attribute 'set_volume'
