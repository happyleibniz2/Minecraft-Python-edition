from functions import *
from settings import *


class Button:
    def __init__(self, gl, text, x, y, text_x=None, button=None, button_hovered=None,
                 label_color=None):
        self.text = text
        self.x = x
        self.y = y
        self.gl = gl
        self.event = None
        self.text_x = text_x
        self.button_hovered = button_hovered
        self.button_ = button
        # Drawn with the default colour when None; a tuple like (255, 80, 80)
        # overrides it (used to highlight the top cloud-quality tier).
        self.label_color = label_color
        self.button = button if button else gl.gui.GUI_TEXTURES["button_bg"]
        self.button_h = (button_hovered if button_hovered
                         else self.gl.gui.GUI_TEXTURES["button_bg_hover"])

    def setEvent(self, event):
        self.event = event

    def update(self, mp, mc):
        if not self.button_:
            self.button = self.gl.gui.GUI_TEXTURES["button_bg"]
        else:
            self.button = self.button_
        if checkHover(self.x, self.y,
                      self.button.width, self.button.height,
                      mp[0], mp[1]):
            self.button = self.button_h
            if mc == 1:
                self.gl.sound.playGuiSound("click")
                if self.event:
                    self.event()

        self.button.blit(self.x, self.gl.HEIGHT - self.y - self.button.height)
        color_args = {"label_color": self.label_color} if self.label_color else {}
        if not self.text_x:
            drawInfoLabel(self.gl, self.text, xx=self.gl.WIDTH // 2, yy=self.gl.HEIGHT - self.y - 25, style=[('', '')],
                          size=12, anchor_x='center', **color_args)
        else:
            drawInfoLabel(self.gl, self.text, xx=self.text_x, yy=self.gl.HEIGHT - self.y - 25, style=[('', '')],
                          size=12, anchor_x='center', **color_args)
