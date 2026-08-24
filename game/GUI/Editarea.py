from pyglet.sprite import Sprite
from functions import *
from settings import *


class Editarea:
    def __init__(self, gl, text, x, y):
        self.text = ""
        self.hintText = text
        self.x = x
        self.y = y
        self.gl = gl
        self.event = None
        self.focused = False
        self.curFade = [1, True]
        self.bg = gl.gui.GUI_TEXTURES["edit_bg"]
        self.bg_sprite = None

    def update(self, mp, mc, keys):
        y_pos = self.gl.HEIGHT - self.y - self.bg.height
        self.bg_sprite = Sprite(self.bg, x=self.x, y=y_pos)

        if checkHover(self.x, self.y,
                      self.bg.width, self.bg.height,
                      mp[0], mp[1]):
            if mc == 1:
                self.focused = True
        else:
            if mc == 1:
                self.focused = False
        if self.focused:
            for i in keys:
                upperCase = False
                if pygame.key.get_pressed()[pygame.K_LSHIFT]:
                    upperCase = True

                if i == 8:
                    self.text = self.text[0:-1]
                elif i == 13 or i == 27:
                    self.focused = False
                    if self.event:
                        self.event(self.text)
                elif i != 1073742049 and i != 1073742053:
                    if len(self.text) > 26:
                        continue
                    try:
                        self.text += chr(i).upper() if upperCase else chr(i)
                    except ValueError:
                        pass

        self.bg_sprite.draw()
        drawInfoLabel(self.gl, self.text, xx=self.x + 10, yy=self.gl.HEIGHT - self.y - 25, style=[('', '')],
                      size=12)
        if not self.focused and not self.text:
            drawInfoLabel(self.gl, self.hintText, xx=self.x + 10, yy=self.gl.HEIGHT - self.y - 25, style=[('', '')],
                          size=12, label_color=(199, 199, 199))

        if self.focused:
            if self.curFade[1]:
                self.curFade[0] -= 0.1
            else:
                self.curFade[0] += 0.2

            if self.curFade[0] > 1:
                self.curFade[1] = True
                self.curFade[0] = 1
            if self.curFade[0] < 0:
                self.curFade[1] = False
                self.curFade[0] = 0
            text = pyglet.text.Label(self.text, font_name='Minecraft Rus')
            drawInfoLabel(self.gl, "_", xx=self.x + 12 + text.content_width, yy=self.gl.HEIGHT - self.y - 25,
                          style=[('', '')], size=12, opacity=self.curFade[0])

    def setEvent(self, event):
        self.event = event