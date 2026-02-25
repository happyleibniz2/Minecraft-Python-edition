import os
import time
from random import randint
import pygame
from OpenGL.GL import *
import pyglet
from settings import *


def load_textures(self):
    print("Loading textures...")
    t = self.texture
    dirs = ['textures']
    while dirs:
        d = dirs.pop(0)
        textures = os.listdir(d)
        for file in textures:
            if os.path.isdir(d + '/' + file):
                dirs += [d + '/' + file]
            else:
                if ".png" not in file:
                    continue

                try:
                    image = pyglet.image.load(d + '/' + file)
                except Exception as e:
                    print(f"Failed to load texture {d}/{file}: {e}")
                    continue
                if image.width == 1024 and image.height == 1024 or image.width == 512 and image.height == 512 or image.width == 256 and image.height == 256 or image.width == 128 and image.height == 128:
                    # Adjust loading method for 1024x textures
                    texture = image.get_texture()  # Example adjustment for higher resolution
                elif image.width == 8 and image.height == 8 or image.width == 16 and image.height == 16 or image.width == 32 and image.height == 32 or image.width == 64 and image.height == 64:
                    # Continue with the existing method for other resolutions
                    texture = image.get_mipmapped_texture()

                n = file.split('.')[0]
                self.texture_dir[n] = d
                self.texture[n] = pyglet.graphics.TextureGroup(texture)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

                print("Successful loaded", n, "texture!")
    done = []
    items = sorted(self.texture_dir.items(), key=lambda i: i[0])
    for n1, d in items:
        n = n1.split(' ')[0]
        if n in done:
            continue
        done += [n]
        if d.startswith('textures/blocks'):
            if d == 'textures/blocks':
                self.inventory_textures[n] = pyglet.resource.image(f"{d}/{n}.png")
                self.block[n] = t[n], t[n], t[n], t[n], t[n], t[n]
            elif d == 'textures/blocks/tbs':
                self.inventory_textures[n] = pyglet.resource.image(f"{d}/{n} s.png")
                self.block[n] = t[n + ' s'], t[n + ' s'], t[n + ' b'], t[n + ' t'], t[n + ' s'], t[n + ' s']
            elif d == 'textures/blocks/ts':
                self.inventory_textures[n] = pyglet.resource.image(f"{d}/{n} s.png")
                self.block[n] = t[n + ' s'], t[n + ' s'], t[n + ' t'], t[n + ' t'], t[n + ' s'], t[n + ' s']
            if n in self.inventory_textures:
                self.inventory_textures[n].width = 22
                self.inventory_textures[n].height = 22


def translateSeed(seed):
    res = ""
    if seed == "":
        seed = str(randint(998, 43433))
    for i in seed:
        res += str(ord(i))
    while len(res) < 10:
        res += res[:-1]
    return int(res[0:10])


def cube_vertices(pos, n=0.5):
    x, y, z = pos
    v = tuple((x + X, y + Y, z + Z) for X in (-n, n) for Y in (-n, n) for Z in (-n, n))
    return tuple(tuple(k for j in i for k in v[j]) for i in
                 ((0, 1, 3, 2), (5, 4, 6, 7), (0, 4, 5, 1), (3, 7, 6, 2), (4, 0, 2, 6), (1, 5, 7, 3)))


def flatten(lst): return sum(map(list, lst), [])


def roundPos(pos):
    x, y, z = pos
    return round(x), round(y), round(z)


def getSum(s):
    res = 0
    for i in s:
        res += int(i)

    return res


def adjacent(x, y, z):
    for p in ((x - 1, y, z), (x + 1, y, z), (x, y - 1, z), (x, y + 1, z), (x, y, z - 1), (x, y, z + 1)): yield p


def drawInfoLabel(gl, text, xx=0, yy=0, style=None, size=15, anchor_x='left', anchor_y='baseline', opacity=1, rotate=0,
                  label_color=(255, 255, 255), shadow_color=(56, 56, 56), scale=0, shadow=True):
    if style is None:
        style = []
    
    # Use the mainFont from settings
    font = mainFont if 'mainFont' in globals() else pygame.font.SysFont('arial', size)
    
    y = -21
    ms = size / 6
    for i in text.split("\n"):
        ix = ms
        iy = gl.HEIGHT + y + yy - ms
        if xx:
            ix = xx + ms
        if yy:
            iy = yy - ms
            
        # Create text surfaces with pygame
        text_surface = font.render(i, True, label_color)
        shadow_surface = font.render(i, True, shadow_color)
        
        # Apply opacity
        if opacity < 1:
            text_surface.set_alpha(round(opacity * 255))
            shadow_surface.set_alpha(round(opacity * 255))
        
        # Get position based on anchors
        text_rect = text_surface.get_rect()
        shadow_rect = shadow_surface.get_rect()
        
        if anchor_x == 'center':
            text_rect.centerx = ix
            shadow_rect.centerx = ix - ms
        elif anchor_x == 'right':
            text_rect.right = ix
            shadow_rect.right = ix - ms
        else:  # left
            text_rect.left = ix
            shadow_rect.left = ix - ms
            
        if anchor_y == 'center':
            text_rect.centery = iy
            shadow_rect.centery = iy + ms
        elif anchor_y == 'top':
            text_rect.top = iy
            shadow_rect.top = iy + ms
        else:  # baseline
            text_rect.bottom = iy
            shadow_rect.bottom = iy + ms
        
        # Draw shadow first (if enabled)
        if shadow:
            # Convert pygame surface to OpenGL texture and draw
            shadow_data = pygame.image.tostring(shadow_surface, 'RGBA', True)
            glPushAttrib(GL_ENABLE_BIT)
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            
            glRasterPos2i(int(shadow_rect.x), int(shadow_rect.y))
            glDrawPixels(shadow_surface.get_width(), shadow_surface.get_height(), 
                        GL_RGBA, GL_UNSIGNED_BYTE, shadow_data)
            glPopAttrib()
        
        # Draw main text
        text_data = pygame.image.tostring(text_surface, 'RGBA', True)
        glPushAttrib(GL_ENABLE_BIT)
        glDisable(GL_DEPTH_TEST)
        glEnable(GL_BLEND)
        glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
        
        glRasterPos2i(int(text_rect.x), int(text_rect.y))
        glDrawPixels(text_surface.get_width(), text_surface.get_height(), 
                    GL_RGBA, GL_UNSIGNED_BYTE, text_data)
        glPopAttrib()
        
        y -= 21


def getElpsTime():
    return time.perf_counter_ns() * 1000 / 1000000000


def checkHover(ox, oy, ow, oh, mx, my):
    if ox < mx < ox + ow and oy < my < oy + oh:
        return True
    return False
