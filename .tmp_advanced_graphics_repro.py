from types import SimpleNamespace

from game.Lighting.Light import FRAGMENT_SHADER, Light
from game.world.Clouds import Clouds
from game.world.DayNightCycle import DayNightCycle
import settings

failures = []

cycle = DayNightCycle()
if not hasattr(cycle, "galaxy_stars"):
    failures.append("galaxy star field missing")
if not hasattr(cycle, "light_direction"):
    failures.append("dynamic sun/moon shadow direction missing")

clouds = Clouds(SimpleNamespace())
if not hasattr(clouds, "clusters"):
    failures.append("clouds are still one flat quad")
if not hasattr(clouds, "shadow_offset"):
    failures.append("cloud shadows cannot synchronize to cloud movement")

light = Light(SimpleNamespace())
for attribute in ("shadow_fbo", "shadow_texture", "shadow_matrix"):
    if not hasattr(light, attribute):
        failures.append(f"{attribute} missing")
for symbol in ("shadowMap", "shadowCoord", "cloudShadow"):
    if symbol not in FRAGMENT_SHADER:
        failures.append(f"shader {symbol} missing")

if not hasattr(settings, "PLAYER_SHADOWS"):
    failures.append("PLAYER_SHADOWS setting missing")

print("red-capable advanced graphics failures:")
for failure in failures:
    print(" -", failure)
print("total:", len(failures))
assert not failures, failures
