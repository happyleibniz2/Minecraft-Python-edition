# Must run before pyglet.window is imported: pyglet 2.x otherwise creates a
# hidden 1x1 shadow window and a second GL context, and the game must own
# exactly one window/context.
import pyglet
pyglet.options['shadow_window'] = False

from pyglet.window import key
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

    def update(self, mp, mc, keys):
        if checkHover(self.x, self.y,
                      self.bg.width, self.bg.height,
                      mp[0], mp[1]):
            if mc == 1:
                self.focused = True
        else:
            if mc == 1:
                self.focused = False
        if self.focused:
            host = getattr(self.gl, "host", None)
            shift_down = bool(
                host is not None and
                (host.key_down(key.LSHIFT) or host.key_down(key.RSHIFT))
            )
            for i in keys:
                if i == key.BACKSPACE:
                    self.text = self.text[0:-1]
                elif i == key.ENTER or i == key.ESCAPE:
                    self.focused = False
                    if self.event:
                        self.event(self.text)
                elif 32 <= i <= 126:
                    if len(self.text) > 26:
                        continue
                    self.text += chr(i).upper() if shift_down else chr(i)

        self.bg.blit(self.x, self.gl.HEIGHT - self.y - self.bg.height)
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
            
    def setEvent(self, event):  # Add this method
        self.event = event
