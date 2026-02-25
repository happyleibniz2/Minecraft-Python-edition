import os
import pyglet
from OpenGL.GL import *
from settings import *
from functions import drawInfoLabel


class GUI:
    def __init__(self, gl):
        print("Init GUI class...")

        self.GUI_TEXTURES = {}
        self.shows = {}
        self.gl = gl

        # load textures used by GUI elements immediately
        self._load_gui_textures()

        # text rendering state for floating labels; use drawInfoLabel instead of
        # pyglet.text.Label to avoid font issues.
        self.lopacity = 255
        self.text = ""

    def showText(self, text):
        # store text for later rendering in update()
        self.text = text
        self.lopacity = 255

    def update(self):
        # draw floating text with shadow using functions.drawInfoLabel
        if self.text:
            # decrease opacity each frame
            self.lopacity -= 1
            if self.lopacity < 0:
                self.lopacity = 255
            else:
                # shadow
                drawInfoLabel(self.gl, self.text, xx=self.gl.WIDTH // 2 + 2,
                              yy=90, size=12, opacity=self.lopacity,
                              label_color=(56, 56, 56), shadow=False)
                # main text
                drawInfoLabel(self.gl, self.text, xx=self.gl.WIDTH // 2,
                              yy=90 + 2, size=12, opacity=self.lopacity,
                              label_color=(255, 255, 255), shadow=False)
        for i in self.shows.values():
            i[0].blit(*i[1])

    def addGuiElement(self, image, pos):
        self.shows[image] = [self.GUI_TEXTURES[image], pos]

    class _GuiTex:
        """Helper wrapper that exposes the minimal interface expected by
        game code: `.blit(x,y)`, `.width`, and `.height`.  Under the hood it
        keeps both a TextureGroup for use in batches and the original image
        for direct blitting."""
        __slots__ = ("group", "image", "width", "height")
        def __init__(self, group, image):
            self.group = group
            self.image = image
            self.width = image.width
            self.height = image.height
        def blit(self, x, y):
            try:
                self.image.blit(x, y)
            except Exception:
                pass

    def _load_gui_textures(self):
        """Recursively load all PNG files under the `gui` directory into
        :pyattr:`GUI_TEXTURES` using the filename (without extension) as the key.
        This ensures buttons, sliders and other widgets have their textures
        available immediately when the GUI is constructed.
        """
        print("Loading GUI textures...")
        for root, dirs, files in os.walk("gui"):
            for fname in files:
                if not fname.lower().endswith(".png"):
                    continue
                key = os.path.splitext(fname)[0]
                path = os.path.join(root, fname)
                try:
                    image = pyglet.image.load(path)
                except Exception as e:
                    print(f"Failed to load GUI texture {path}: {e}")
                    continue
                tex = image.get_texture()
                group = pyglet.graphics.TextureGroup(tex)
                # store wrapper instead of raw group
                self.GUI_TEXTURES[key] = self._GuiTex(group, image)
                # use nearest filtering so GUI stays pixel‑sharp
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
