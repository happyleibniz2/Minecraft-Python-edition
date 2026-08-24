from pyglet.sprite import Sprite
from functions import *
from settings import *


class Sliderbox:
    def __init__(self, gl, text, maxval, x, y):
        self.text = text
        self.maxval = maxval
        self.x = x
        self.y = y
        self.gl = gl
        self.event = None
        self.val = 100
        self.lastButtonClicked = False

        self.bg = gl.gui.GUI_TEXTURES["edit_bg"]
        self.slider_img = gl.gui.GUI_TEXTURES["slider"]
        self.bg_sprite = None
        self.slider_sprite = None

    def update(self, mp):
        pos = (self.bg.width / self.maxval) * self.val
        if pos > self.bg.width - self.slider_img.width:
            pos = self.bg.width - self.slider_img.width

        y_pos = self.gl.HEIGHT - self.y - self.bg.height
        self.bg_sprite = Sprite(self.bg, x=self.x, y=y_pos)
        self.slider_sprite = Sprite(self.slider_img, x=self.x + pos, y=y_pos)

        if checkHover(self.x, self.y,
                      self.bg.width, self.bg.height,
                      mp[0], mp[1]):
            if pygame.mouse.get_pressed(3)[0]:
                self.val = round((mp[0] - self.x) * self.maxval / self.bg.width)
                pos = mp[0] - self.x
                if pos > self.bg.width - self.slider_img.width:
                    pos = self.bg.width - self.slider_img.width
                self.slider_sprite.x = self.x + pos
                self.lastButtonClicked = True
        if self.lastButtonClicked and not pygame.mouse.get_pressed(3)[0]:
            self.gl.sound.playGuiSound("click")
            self.lastButtonClicked = False

        self.bg_sprite.draw()
        self.slider_sprite.draw()
        drawInfoLabel(self.gl, self.text, xx=self.x, yy=self.gl.HEIGHT - self.y + 15, style=[('', '')],
                      size=12)