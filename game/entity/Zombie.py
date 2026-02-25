import math
from game.entity.Entity import Entity


class Zombie(Entity):
    def __init__(self, gl):
        super().__init__(gl)
        # very simple walking speed
        self.speed = 0.02
        # add a little cube so it is visible (optional)
        self.model.addCube(0, 0, 0, 0.5, 0.5, 0.5, gl.panorama)

    def update(self):
        # move slowly toward the player on the XZ plane
        from settings import clock
        dt = clock.get_time() / 1000.0
        if dt <= 0:
            dt = 0.001
        px, py, pz = self.gl.player.position
        x, y, z = self.position
        dx = px - x
        dz = pz - z
        dist = math.hypot(dx, dz)
        if dist > 0.1:
            self.position[0] += (dx / dist) * self.speed * dt
            self.position[2] += (dz / dist) * self.speed * dt
        super().update()
