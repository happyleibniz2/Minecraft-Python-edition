from types import SimpleNamespace

import pyglet
window = pyglet.window.Window(800, 400, visible=False)
window.switch_to()

from OpenGL.GL import *
from OpenGL.GLU import gluLookAt, gluPerspective
from PIL import Image, ImageChops

from functions import load_textures
from game.Lighting.Light import Light
from game.blocks.CubeHandler import CubeHandler
from game.world.DayNightCycle import DayNightCycle

assets = SimpleNamespace(texture={}, block={}, texture_dir={}, inventory_textures={})
load_textures(assets)
assets.worldGen = SimpleNamespace(seed=1, perlinBiomes=lambda x, z: 1)
assets.light = Light(assets)
handler = CubeHandler(None, assets.block, None,
                      ("leaves_oak", "leaves_taiga", "torch"), assets)
assets.cubes = handler

for x in range(-8, 9):
    for z in range(-8, 9):
        handler.add((x, 0, z), "stone")
for y in range(1, 7):
    handler.add((0, y, 0), "cobblestone")
for y in range(1, 4):
    handler.add((-3, y, 2), "planks_oak")
for chunk in handler.render_chunks.values():
    chunk.rebuild()

assert assets.light.initialize()
cycle = DayNightCycle(2000)
assert assets.light.begin_shadow_pass((0, 2, 0), cycle.light_direction)
handler.render_shadow((0, 2, 0), 55)
assets.light.end_shadow_pass()
assert assets.light.shadow_ready

glEnable(GL_DEPTH_TEST)
glEnable(GL_TEXTURE_2D)
glEnable(GL_ALPHA_TEST)
glAlphaFunc(GL_GREATER, 0.1)
assets.light.set_sky_brightness(0.9)
assets.light.set_environment((0.45, 0.62, 0.88), 50, 120)
assets.light.set_clouds((0, 0), 2.0)   # isolate the real shadow map


def panel(left, shadows):
    glEnable(GL_SCISSOR_TEST)
    glViewport(left, 0, 400, 400)
    glScissor(left, 0, 400, 400)
    glClearColor(0.45, 0.62, 0.88, 1)
    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glMatrixMode(GL_PROJECTION)
    glLoadIdentity()
    gluPerspective(52, 1, 0.1, 100)
    glMatrixMode(GL_MODELVIEW)
    glLoadIdentity()
    gluLookAt(11, 9, 14, 0, 1, 0, 0, 1, 0)

    saved = assets.light.shadow_ready
    assets.light.shadow_ready = shadows
    assets.light.begin_render()
    for chunk in handler.render_chunks.values():
        chunk.render_opaque()
    assets.light.end_render()
    assets.light.shadow_ready = saved
    glDisable(GL_SCISSOR_TEST)


panel(0, False)
panel(400, True)

glFlush()
glReadBuffer(GL_BACK)
pixels = glReadPixels(0, 0, 800, 400, GL_RGBA, GL_UNSIGNED_BYTE)
image = Image.frombytes("RGBA", (800, 400), pixels).transpose(Image.Transpose.FLIP_TOP_BOTTOM)
image.save(".tmp_shadow_compare.png")

left = image.crop((0, 0, 400, 400)).convert("RGB")
right = image.crop((400, 0, 800, 400)).convert("RGB")
difference = ImageChops.difference(left, right)
changed = sum(1 for pixel in difference.getdata() if max(pixel) > 4)
assert changed > 100, changed
print("pixels changed by real-time shadows:", changed)
print("GL error:", glGetError())

window.close()
print("rendered .tmp_shadow_compare.png")
