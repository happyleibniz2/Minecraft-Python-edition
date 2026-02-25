from random import randint


class BlockSound:
    def __init__(self, gl):
        self.gl = gl
        self.cntr = 0
        self.pickUpAlreadyPlayed = False

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
        self.cntr += 1
        if self.cntr % 100 != 0 or self.cntr == 0:
            return

        sound = self.gl.sound.SOUNDS["damage"]["fallbig"][0]

        if blockName.endswith("wool"):
            sound = self.gl.sound.SOUNDS["damage"]["fallsmall"][0]
        if hp > 0:
            bl = len(self.gl.sound.SOUNDS["damage"]["hit"])
            sound = self.gl.sound.SOUNDS["damage"]["hit"][randint(0, bl - 1)]

        chnl = sound.play()
        chnl.set_volume(self.gl.sound.volume)

    def playStepSound(self, blockName, custom=300):
        self.cntr += 1
        if self.cntr % custom != 0 or self.cntr == 0:
            return
        blName = self.getBlockSound(blockName)

        bl = len(self.gl.sound.BLOCKS_SOUND["step"][blName])
        chnl = self.gl.sound.BLOCKS_SOUND["step"][blName][randint(0, bl - 1)].play()
        try:
            chnl.set_volume(self.gl.sound.volume)
        except:
            pass

    def playBoomSound(self):
        sounds = self.gl.sound.BLOCKS_SOUND.get("explode")
        if not sounds:
            return
        # sounds should be a list due to loader flattening
        try:
            idx = randint(0, len(sounds) - 1)
            chnl = sounds[idx].play()
            chnl.set_volume(self.gl.sound.volume)
        except Exception:
            pass

    def playBlockSound(self, blockName):
        blName = self.getBlockSound(blockName)

        bl = len(self.gl.sound.BLOCKS_SOUND["dig"][blName])
        chnl = self.gl.sound.BLOCKS_SOUND["dig"][blName][randint(0, bl - 1)].play()
        chnl.set_volume(self.gl.sound.volume)

    def playPickUpSound(self):
        if not self.pickUpAlreadyPlayed:
            snd = self.gl.sound.BLOCKS_SOUND.get("pickUp")
            if snd is None:
                return
            # snd might be a single Sound or list
            try:
                if isinstance(snd, list):
                    chnl = snd[0].play()
                else:
                    chnl = snd.play()
                chnl.set_volume(self.gl.sound.volume)
            except Exception:
                pass
            self.pickUpAlreadyPlayed = True

# BUG WHEN PLAYING
# <UNDONE> chnl.set_volume(self.gl.sound.volume)
#             ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^ ^
# AttributeError: 'NoneType' object has no attribute 'set_volume'
