"""Minecraft spawn eggs.

A spawn egg is a grayscale base (``spawn_egg.png``) tinted with the mob's
primary colour, plus a grayscale spot overlay (``spawn_egg_overlay.png``)
tinted with its secondary colour. Because this renderer is fixed-function and
cannot tint two layers per quad, both layers are composited into a single
texture once at load time.

Colours are Minecraft's official spawn egg values.
"""

import os

import pyglet
from OpenGL.GL import *

# entity id -> (primary colour, secondary colour), from Minecraft
SPAWN_EGGS = {
    "cow": (0x443626, 0xA1A1A1),
    "sheep": (0xE7E7E7, 0xFFB5B5),
    "zombie": (0x00AFAF, 0x799C65),
}

BASE_TEXTURE = os.path.join("textures", "items", "spawn_egg.png")
OVERLAY_TEXTURE = os.path.join("textures", "items", "spawn_egg_overlay.png")


def egg_item_name(entity_id):
    return f"{entity_id}_spawn_egg"


def _unpack(color):
    return ((color >> 16) & 0xFF, (color >> 8) & 0xFF, color & 0xFF)


def _load_rgba(path):
    """Return (width, height, rows) with rows ordered top-to-bottom."""
    image = pyglet.image.load(path)
    width, height = image.width, image.height
    raw = image.get_image_data().get_data("RGBA", width * 4)
    rows = [bytearray(raw[y * width * 4:(y + 1) * width * 4]) for y in range(height)]
    rows.reverse()   # pyglet rows run bottom-to-top
    return width, height, rows


def _tint_over(base_rows, overlay_rows, width, height, primary, secondary):
    """Composite tinted overlay over tinted base, like Minecraft's item layers."""
    out = bytearray(width * height * 4)
    for y in range(height):
        base_row = base_rows[y]
        overlay_row = overlay_rows[y] if overlay_rows else None
        for x in range(width):
            offset = x * 4
            br, bg, bb, ba = base_row[offset:offset + 4]
            r = br * primary[0] // 255
            g = bg * primary[1] // 255
            b = bb * primary[2] // 255
            a = ba

            if overlay_row is not None:
                orr, og, ob, oa = overlay_row[offset:offset + 4]
                if oa:
                    sr = orr * secondary[0] // 255
                    sg = og * secondary[1] // 255
                    sb = ob * secondary[2] // 255
                    alpha = oa / 255.0
                    r = int(sr * alpha + r * (1 - alpha))
                    g = int(sg * alpha + g * (1 - alpha))
                    b = int(sb * alpha + b * (1 - alpha))
                    a = max(a, oa)

            target = (y * width + x) * 4
            out[target:target + 4] = bytes((r, g, b, a))
    return bytes(out)


def configure_spawn_eggs(scene):
    """Build a tinted texture and inventory icon for every spawn egg."""
    if not os.path.isfile(BASE_TEXTURE):
        return {}

    width, height, base_rows = _load_rgba(BASE_TEXTURE)
    overlay_rows = None
    if os.path.isfile(OVERLAY_TEXTURE):
        overlay_width, overlay_height, overlay_rows = _load_rgba(OVERLAY_TEXTURE)
        if (overlay_width, overlay_height) != (width, height):
            overlay_rows = None

    # the raw grayscale layers are internal only; they must never show up as
    # usable items in the inventory
    for internal in ("spawn_egg", "spawn_egg_overlay"):
        scene.inventory_textures.pop(internal, None)

    created = {}
    for entity_id, (primary, secondary) in SPAWN_EGGS.items():
        pixels = _tint_over(base_rows, overlay_rows, width, height,
                            _unpack(primary), _unpack(secondary))
        image = pyglet.image.ImageData(width, height, "RGBA", pixels, pitch=-width * 4)

        texture = image.get_texture()
        glBindTexture(GL_TEXTURE_2D, texture.id)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_NEAREST)

        name = egg_item_name(entity_id)
        scene.texture[name] = pyglet.graphics.TextureGroup(texture)

        icon = pyglet.image.ImageData(width, height, "RGBA", pixels, pitch=-width * 4)
        icon.width = 22
        icon.height = 22
        scene.inventory_textures[name] = icon
        created[name] = entity_id

    scene.spawn_egg_items = created
    return created
