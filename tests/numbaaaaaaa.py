import time
from game.world.worldGenerator import worldGenerator

gen = worldGenerator(None, seed=12345)
start = time.perf_counter()
for cx in range(0, 160, 4):
    for cz in range(0, 160, 4):
        gen.gen(cx, cz)
elapsed = time.perf_counter() - start
print(f"{elapsed:.2f}s total, {elapsed / 1600 * 1000:.2f} ms/column")