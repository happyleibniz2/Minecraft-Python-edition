import logging
import time

# Must run before pyglet.text/pyglet.font are imported: pyglet 2.x otherwise
# creates a hidden 1x1 shadow window and a second GL context, and the game
# must own exactly one window/context.
import pyglet
pyglet.options['shadow_window'] = False
from settings import *


class GUI:
    def __init__(self, gl):
        print("Init GUI class...")

        self.GUI_TEXTURES = {}
        self.shows = {}
        self.gl = gl

        self.lopacity = 0
        self.tooltip_until = 0.0
        self.shadow_lbl = pyglet.text.Label("",
                                            font_name='Minecraft Rus',
                                            color=(56, 56, 56, self.lopacity),
                                            font_size=12,
                                            x=self.gl.WIDTH // 2, y=90, anchor_x='center')
        self.lbl = pyglet.text.Label("",
                                     font_name='Minecraft Rus',
                                     color=(255, 255, 255, self.lopacity),
                                     font_size=12,
                                     x=self.gl.WIDTH // 2 - 2, y=90 + 2, anchor_x='center')
        logging.debug("GUI labels initialized")

    def showText(self, text):
        self.lbl.text = text
        self.shadow_lbl.text = text
        self.lopacity = 255
        self.tooltip_until = time.monotonic() + 2.0

    def hideText(self):
        self.tooltip_until = 0.0
        self.lopacity = 0
        self.lbl.text = ""
        self.shadow_lbl.text = ""

    def update(self):
        self.shadow_lbl.x = self.gl.WIDTH // 2 + 2
        self.lbl.x = self.gl.WIDTH // 2
        remaining = self.tooltip_until - time.monotonic()
        if remaining > 0 and self.lbl.text:
            self.lopacity = min(255, round(remaining / 0.5 * 255))
            self.shadow_lbl.set_style("color", (56, 56, 56, self.lopacity))
            self.shadow_lbl.draw()
            self.lbl.set_style("color", (255, 255, 255, self.lopacity))
            self.lbl.draw()
        elif self.lopacity:
            self.hideText()

        for texture, position in self.shows.values():
            x, y = position
            # Hidden elements (e.g. the crosshair parked at -100,-100 while a
            # modal window is open) used to issue an off-screen quad every
            # frame.  Skip them entirely instead.
            if (x + texture.width <= 0 or y + texture.height <= 0
                    or x >= self.gl.WIDTH or y >= self.gl.HEIGHT):
                continue
            texture.blit(x, y)

    def addGuiElement(self, image, pos):
        self.shows[image] = [self.GUI_TEXTURES[image], pos]
