import math
from game.entity.Entity import Entity

class Zombie(Entity):
    def __init__(self, gl):
        super().__init__(gl)
        head_width = 1
        head_height = 1
        head_d = 1
        head_x = -1
        head_y = 3
        head_z = 0.25
        self.model.addCube(head_x, head_y, head_z, head_width, head_height, head_d, gl.zombie_head_texture)
        self.model.addCube(head_x, 1.5, 0.5, head_width, head_height*2, head_d/2, gl.zombie_clothes_texture)
        self.model.addCube(-0.5, 0, 0.5, head_width / 2, head_height*2, head_d / 2, gl.zombie_leg_texture)
        self.model.addCube(-1, 0, 0.5, head_width / 2.3, head_height*1.92, head_d / 2, gl.zombie_leg_texture)
        self.model.addCube(-1.5, 1.5, 0.5, head_width/2, head_height*2, head_d/2, gl.zombie_hand_texture)
        self.model.addCube(0, 1.5, 0.5, head_width / 2, head_height * 2, head_d / 2,
                           gl.zombie_hand_texture)

    def update(self, dt):
        self.position = list(self.position)
        self.rotation = list(self.rotation)
        if hasattr(self.gl, 'player'):
            dx = self.gl.player.position[0] - self.position[0]
            dz = self.gl.player.position[2] - self.position[2]
            distance = math.hypot(dx, dz)
            if distance > 0.1:
                # Move towards player at a constant speed (meters per second)
                step = min(self.speed * dt * 60, distance)   # normalize to 60 fps equivalent
                self.position[0] += (dx / distance) * step
                self.position[2] += (dz / distance) * step
                self.rotation[1] = int(math.degrees(math.atan2(dx, dz)))
        super().update(dt)   # pass dt to parent's update