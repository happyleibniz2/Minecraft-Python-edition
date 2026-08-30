import math
from types import SimpleNamespace

import numpy as np
import pyglet
window = pyglet.window.Window(160, 120, visible=False)
window.switch_to()

from OpenGL.GL import *
from OpenGL.GLU import gluLookAt, gluPerspective

from functions import load_textures
from game.Lighting.Light import FRAGMENT_SHADER, Light
from game.Scene import Scene
from game.blocks.CubeHandler import CubeHandler
from game.entity.Cow import Cow
from game.world.Clouds import Clouds
from game.world.DayNightCycle import DayNightCycle
import settings


print("=== ATMOSPHERE / GALAXY ===")
cycle = DayNightCycle(18000)
assert len(cycle.galaxy_stars) == 420
assert len(cycle.stars) == 180
assert cycle.star_brightness > 0.99
assert cycle.zenith_color != cycle.horizon_color
print(f"night sky: {len(cycle.stars)} stars + {len(cycle.galaxy_stars)} galaxy points")
print("horizon:", tuple(round(c, 3) for c in cycle.horizon_color))
print("zenith :", tuple(round(c, 3) for c in cycle.zenith_color))

directions = []
for ticks in (1000, 6000, 11000, 18000):
    cycle.set_time(ticks)
    directions.append(cycle.light_direction)
assert len({tuple(round(v, 3) for v in direction) for direction in directions}) == 4
assert all(direction[1] >= 0 for direction in directions)
print("sun/moon light direction changes with time and always points above horizon")


print("\n=== LAYERED CLOUDS ===")
cloud_scene = SimpleNamespace(light=None)
clouds = Clouds(cloud_scene)
assert len(clouds.clusters) > 50, len(clouds.clusters)
assert clouds.DRAW_DISTANCE >= 256
puff_count = sum(len(cluster[3]) for cluster in clouds.clusters)
assert puff_count > 300
before = clouds.shadow_offset
clouds.update(10.0)
after = clouds.shadow_offset
assert after != before
print(f"cloud field: {len(clouds.clusters)} clusters / {puff_count} layered puffs")
print(f"draw distance: {clouds.DRAW_DISTANCE} blocks; wind offset {before} -> {after}")

player_stub = SimpleNamespace(position=[0, 2, 0], rotation=[0, 0])
cycle.set_time(6000)
clouds.render(player_stub, cycle)
assert glGetError() == GL_NO_ERROR
print("procedural cloud field renders GL-cleanly")


print("\n=== REAL SHADOW MAP ===")
assets = SimpleNamespace(texture={}, block={}, texture_dir={}, inventory_textures={})
load_textures(assets)
assets.allowEvents = {"collisions": True}
assets.worldGen = SimpleNamespace(seed=1, perlinBiomes=lambda x, z: 1)
assets.light = Light(assets)
assets.blockSound = SimpleNamespace(playStepSound=lambda *a, **k: None)
assets.particles = SimpleNamespace(addParticle=lambda *a, **k: None)
assets.entity = []
handler = CubeHandler(None, assets.block, None,
                      ("leaves_oak", "leaves_taiga", "torch"), assets)
assets.cubes = handler

assert assets.light.initialize()
assert assets.light.shadow_fbo
assert assets.light.shadow_texture
print(f"shadow FBO={assets.light.shadow_fbo}, depth texture={assets.light.shadow_texture}, size={assets.light.SHADOW_SIZE}")

for x in range(-5, 6):
    for z in range(-5, 6):
        handler.add((x, 0, z), "stone")
for y in range(1, 5):
    handler.add((0, y, 0), "cobblestone")
for chunk in handler.render_chunks.values():
    chunk.rebuild()

glViewport(0, 0, 160, 120)
glMatrixMode(GL_PROJECTION)
glLoadIdentity()
gluPerspective(60, 160 / 120, 0.1, 100)
glMatrixMode(GL_MODELVIEW)
glLoadIdentity()
gluLookAt(8, 6, 10, 0, 1, 0, 0, 1, 0)

cycle.set_time(6000)
before_matrix = None
assert assets.light.begin_shadow_pass((0, 2, 0), cycle.light_direction)
handler.render_shadow((0, 2, 0), 50)
before_matrix = assets.light.shadow_matrix.copy()
assets.light.end_shadow_pass()
assert assets.light.shadow_ready

glBindTexture(GL_TEXTURE_2D, assets.light.shadow_texture)
depth = np.asarray(glGetTexImage(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, GL_FLOAT))
written = int(np.count_nonzero(depth < 0.9999))
assert written > 100, written
print(f"terrain wrote {written} depth texels into the real shadow map")

cycle.set_time(1000)
assert assets.light.begin_shadow_pass((0, 2, 0), cycle.light_direction)
handler.render_shadow((0, 2, 0), 50)
after_matrix = assets.light.shadow_matrix.copy()
assets.light.end_shadow_pass()
assert not np.allclose(before_matrix, after_matrix)
print("shadow matrix changes as the sun moves")


print("\n=== ENTITY / PLAYER CASTERS ===")
cow = Cow(assets)
cow.position = [2, 1.75, 0]
assets.entity.append(cow)

# Entity-only depth pass on an otherwise empty map proves it is a real caster.
assert assets.light.begin_shadow_pass((2, 2, 0), cycle.light_direction)
cow.render(0)
assets.light.end_shadow_pass()
glBindTexture(GL_TEXTURE_2D, assets.light.shadow_texture)
entity_depth = np.asarray(glGetTexImage(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, GL_FLOAT))
entity_written = int(np.count_nonzero(entity_depth < 0.9999))
assert entity_written > 0
print(f"cow wrote {entity_written} shadow-map texels")

shadow_scene = Scene.__new__(Scene)
shadow_scene.player = SimpleNamespace(position=[0, 1.75, 0], is_spectator=False)
assert assets.light.begin_shadow_pass((0, 2, 0), cycle.light_direction)
shadow_scene.drawPlayerShadowCaster()
assets.light.end_shadow_pass()
glBindTexture(GL_TEXTURE_2D, assets.light.shadow_texture)
player_depth = np.asarray(glGetTexImage(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT, GL_FLOAT))
player_written = int(np.count_nonzero(player_depth < 0.9999))
assert player_written > 0
print(f"player proxy wrote {player_written} shadow-map texels")

# The Scene shadow pass must include its dynamic block-entity batch (dropped
# blocks/items today; chests can use the same path when added).
calls = {"chunks": 0, "block_entities": 0, "end": 0}
pass_scene = Scene.__new__(Scene)
pass_scene.player = SimpleNamespace(position=[0, 2, 0], is_spectator=True)
pass_scene.dayNight = SimpleNamespace(light_direction=(0, 1, 0))
pass_scene.light = SimpleNamespace(
    SHADOW_RADIUS=48,
    begin_shadow_pass=lambda *args: True,
    end_shadow_pass=lambda: calls.__setitem__("end", calls["end"] + 1),
)
pass_scene.cubes = SimpleNamespace(
    render_shadow=lambda *args: calls.__setitem__("chunks", calls["chunks"] + 1))
pass_scene.entity = []
pass_scene.stuffBatch = SimpleNamespace(
    draw=lambda: calls.__setitem__("block_entities", calls["block_entities"] + 1))
pass_scene.renderShadowMap()
assert calls == {"chunks": 1, "block_entities": 1, "end": 1}, calls
print("dynamic block-entity batch participates in shadow casting")


print("\n=== CLOUD SHADOW SHADER ===")
for symbol in ("shadowMap", "shadowCoord", "realtimeShadow", "cloudNoise", "cloudShadow"):
    assert symbol in FRAGMENT_SHADER
assets.light.set_clouds(clouds.shadow_offset, clouds.coverage)
assets.light.set_sky_brightness(1.0)
assets.light.set_environment((0.5, 0.7, 1.0), 20, 100)
assert assets.light.begin_render()
assert glGetIntegerv(GL_CURRENT_PROGRAM) == assets.light.shader
assets.light.end_render()
assert glGetError() == GL_NO_ERROR
print("PCF real-time shadows and synchronized procedural cloud shadows compiled and bound")


print("\n=== PLAYER SHADOW OPTION ===")
assert hasattr(settings, "PLAYER_SHADOWS")
main_source = open("minecraft_main_program.py", encoding="utf-8").read()
assert "Player Shadows: {'YES' if settings.PLAYER_SHADOWS else 'NO'}" in main_source
assert "player_shadow_button.setEvent(toggle_player_shadows)" in main_source
scene_source = open("game/Scene.py", encoding="utf-8").read()
assert "game_settings.PLAYER_SHADOWS" in scene_source
print("persistent Player Shadows YES/NO option is wired to the caster pass")

window.close()
print("\nadvanced graphics test passed")
