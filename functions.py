import os
import time
from random import randint

import pygame.display
import pyglet
from OpenGL.GL import *
from settings import *

# Reusable pyglet.text.Label pairs keyed by the owning GL context. The label
# pool exists to remove the hundreds of short-lived Label allocations that
# drawInfoLabel used to make every frame from tooltips, F3, buttons, sliders
# and slot counters.
_INFO_LABEL_POOL = {}


def _info_label_pool(gl, count):
    pool = _INFO_LABEL_POOL.get(id(gl))
    if pool is None:
        pool = []
        _INFO_LABEL_POOL[id(gl)] = pool
    while len(pool) < count:
        pool.append((
            pyglet.text.Label("", font_name='Minecraft Rus', font_size=15),
            pyglet.text.Label("", font_name='Minecraft Rus', font_size=15),
        ))
    return pool


def load_textures(self):
    print("Loading textures...")
    t = self.texture
    dirs = ['textures']
    # colormaps are sampled on the CPU and share names with real blocks
    # (grass.png), so they must never enter the block texture tables
    excluded_dirs = {'textures/colormap'}
    while dirs:
        d = dirs.pop(0)
        if d.replace('\\', '/') in excluded_dirs:
            continue
        textures = os.listdir(d)
        for file in textures:
            if os.path.isdir(d + '/' + file):
                dirs += [d + '/' + file]
            else:
                if not file.lower().endswith(".png"):
                    continue
                if d == "textures" and file in ("water_still.png", "water_flow.png"):
                    continue

                image = pyglet.image.load(d + '/' + file)
                if image.width == 1024 and image.height == 1024 or image.width == 512 and image.height == 512 or image.width == 256 and image.height == 256 or image.width == 128 and image.height == 128:
                    texture = image.get_texture()
                elif image.width == 8 and image.height == 8 or image.width == 16 and image.height == 16 or image.width == 32 and image.height == 32 or image.width == 64 and image.height == 64:
                    texture = image.get_mipmapped_texture()
                else:
                    texture = image.get_texture()

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
        elif d == 'textures/items':
            self.inventory_textures[n] = pyglet.image.load(f"{d}/{n}.png")
        if n in self.inventory_textures:
            self.inventory_textures[n].width = 22
            self.inventory_textures[n].height = 22

    from game.blocks.Water import configure_water_textures
    configure_water_textures(self)
    configure_grass_textures(self)
    configure_plant_textures(self)

    from game.entity.SpawnEggs import configure_spawn_eggs
    configure_spawn_eggs(self)

    from game.world.DayNightCycle import configure_celestial_textures
    configure_celestial_textures(self)


def configure_grass_textures(self):
    """Wire up the Minecraft 1.20.1 three-texture grass block.

    ``grass_block_top`` is grayscale and biome-tinted, ``grass_block_side`` is
    plain dirt, and ``grass_block_side_overlay`` is a grayscale cut-out drawn
    over the sides and tinted with the same biome colour.
    """
    required = ("grass_block_top", "grass_block_side", "grass_block_side_overlay")
    if not all(name in self.texture for name in required):
        return

    top = self.texture["grass_block_top"]
    side = self.texture["grass_block_side"]
    bottom = self.texture.get("dirt", side)

    # order: left, right, bottom, top, back, front
    self.block["grass"] = (side, side, bottom, top, side, side)
    self.grass_side_overlay = self.texture["grass_block_side_overlay"]

    path = os.path.join("textures", "blocks", "grass", "grass_block_side.png")
    if os.path.isfile(path):
        image = pyglet.image.load(path)
        image.width = 22
        image.height = 22
        self.inventory_textures["grass"] = image


def configure_plant_textures(self):
    """Register crossed short grass and preserve binary leaf cutouts."""
    tall_grass = self.texture.get("tall_grass")
    if tall_grass is not None:
        self.block["tall_grass"] = (tall_grass,) * 6
        image = pyglet.image.load(os.path.join("textures", "tall_grass.png"))
        image.width = 22
        image.height = 22
        self.inventory_textures["tall_grass"] = image

    for name in ("leaves_oak", "leaves_taiga", "tall_grass", "glass"):
        group = self.texture.get(name)
        if group is None:
            continue
        texture = group.texture
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_NEAREST)


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
    lines = text.split("\n")
    pool = _info_label_pool(gl, len(lines))
    y = -21
    ms = size / 6
    alpha = round(opacity * 255)
    shadow_rgba = (shadow_color[0], shadow_color[1], shadow_color[2], alpha)
    label_rgba = (label_color[0], label_color[1], label_color[2], alpha)

    for index, line in enumerate(lines):
        shadow_lbl, lbl = pool[index]

        ix = ms
        iy = gl.HEIGHT + y + yy - ms
        if xx:
            ix = xx + ms
        if yy:
            iy = yy - ms

        for target, tx, ty in ((shadow_lbl, ix, iy),
                               (lbl, ix - ms, iy + ms)):
            target.text = line
            target.font_size = size
            target.x = tx
            target.y = ty
            target.anchor_x = anchor_x
            target.anchor_y = anchor_y

        if not style:
            lbl.set_style("background_color", (69, 69, 69, 100))
        else:
            for st in style:
                lbl.set_style(st[0], st[1])
                shadow_lbl.set_style(st[0], st[1])
        lbl.set_style("color", label_rgba)
        shadow_lbl.set_style("color", shadow_rgba)

        glPushMatrix()
        if rotate:
            glRotatef(rotate, 0.0, 0.0, 1.0)
        if scale:
            glScalef(scale, scale, 0)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        if shadow:
            shadow_lbl.draw()
            lbl.draw()
        glPopMatrix()
        y -= 21


def getElpsTime():
    return time.perf_counter_ns() * 1000 / 1000000000


def checkHover(ox, oy, ow, oh, mx, my):
    if ox < mx < ox + ow and oy < my < oy + oh:
        return True
    return False