from pyglet.sprite import Sprite
from functions import *
from settings import *


class Button:
    def __init__(self, gl, text, x, y):
        self.text = text
        self.x = x
        self.y = y
        self.gl = gl
        self.event = None

        self.bg_image = gl.gui.GUI_TEXTURES["button_bg"]
        self.bg_hover_image = gl.gui.GUI_TEXTURES["button_bg_hover"]
        # Legacy compatibility: older code expects .button.width/.height
        self.button = self.bg_image
        # Sprite will be created on update to reflect position changes
        self.sprite = None

    def setEvent(self, event):
        self.event = event

    def update(self, mp, mc):
        # Create sprite with current position
        # y coordinate: pyglet uses bottom-left, so convert from top-left
        y_pos = self.gl.HEIGHT - self.y - self.bg_image.height
        self.sprite = Sprite(self.bg_image, x=self.x, y=y_pos)
        self.button = self.sprite.image

        if checkHover(self.x, self.y,
                      self.sprite.width, self.sprite.height,
                      mp[0], mp[1]):
            self.sprite.image = self.bg_hover_image
            self.button = self.sprite.image
            if mc == 1:
                self.gl.sound.playGuiSound("click")
                if self.event:
                    self.event()
        else:
            self.sprite.image = self.bg_image
            self.button = self.sprite.image

        self.sprite.draw()
        # Draw label
        drawInfoLabel(self.gl, self.text, xx=self.gl.WIDTH // 2, yy=self.gl.HEIGHT - self.y - 25, style=[('', '')],
                      size=12, anchor_x='center')