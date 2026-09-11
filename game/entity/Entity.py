import math

from game.models.Model import Model
from functions import roundPos

class Entity:
    def __init__(self, gl):
        self.shift = 0
        self.bInAir = None
        self.canShake = None
        self.hp = 20
        self.is_dead = False
        self.hurt_cooldown = 0.0
        self.width = 0.6
        self.height = 1.8
        self.pick_radius = 0.1
        self.dy = 0
        print("doing some buggy things in the Entity class...")
        self.position = [0, 100, 0]
        self.rotation = [0, 0, 0]
        self.gravity = 5.8
        self.gl = gl
        self.tVel = 50
        self.lastPlayerPosOnGround = [0, 0, 0]
        self.playerFallY = 0
        self.kW, self.kS, self.kA, self.kD = 0, 0, 0, 0
        self.gl.allowEvents["collisions"] = True
        self.speed = 0.02
        self.model = Model(gl)

    def update(self, dt):
        self.tick_combat(dt)
        self.update_pos(dt)

    def render(self, a):
        if self.is_dead:
            return
        self.model.drawModel(self.position, self.rotation)

    def tick_combat(self, dt):
        self.hurt_cooldown = max(0.0, self.hurt_cooldown - dt)

    def get_hitbox(self):
        half_width = self.width / 2
        ground = self.position[1] - 1.25
        return (
            self.position[0] - half_width, ground, self.position[2] - half_width,
            self.position[0] + half_width, ground + self.height, self.position[2] + half_width,
        )

    def get_visibility_bounds(self):
        """Conservative bounds covering the model's animated visual envelope."""
        x0, y0, z0, x1, y1, z1 = self.get_hitbox()
        return (x0 - 1.25, y0 - 1.5, z0 - 1.25,
                x1 + 1.25, y1 + 1.5, z1 + 1.25)

    def hurt(self, damage, attacker=None):
        if self.is_dead or self.hurt_cooldown > 0:
            return False
        self.hp -= max(0.0, damage)
        self.hurt_cooldown = 0.5
        if attacker is not None:
            self.knockback_from(attacker)
        if self.hp <= 0:
            self.die()
        return True

    def knockback_from(self, attacker, strength=0.4):
        dx = self.position[0] - attacker.position[0]
        dz = self.position[2] - attacker.position[2]
        distance = math.hypot(dx, dz)
        if distance <= 1e-6:
            return
        target = (
            self.position[0] + dx / distance * strength,
            self.position[1],
            self.position[2] + dz / distance * strength,
        )
        self.position = list(self.collide(target))
        self.dy = max(self.dy, 2.0)

    def die(self):
        self.is_dead = True
        entities = getattr(self.gl, "entity", None)
        if entities is not None and self in entities:
            entities.remove(self)

    def update_pos(self, dt):
        DX, DY, DZ = 0, 0, 0
        self.position = [self.position[0] + DX, self.position[1] + DY, self.position[2] + DZ]
        if dt < 0.2:
            dt /= 10
            DX /= 10
            DY /= 10
            DZ /= 10
            for i in range(10):
                self.move(dt, DX, DY, DZ)

    def move(self, dt, dx, dy, dz):
        self.dy -= dt * self.gravity
        self.dy = max(self.dy, -self.tVel)
        dy += self.dy * dt

        if self.dy > 19.8:
            self.dy = 19.8

        x, y, z = self.position
        col = self.collide((x + dx, y + dy, z + dz))
        col2 = roundPos((col[0], col[1] - 2, col[2]))
        self.canShake = self.position[1] == col[1]
        if self.position[0] != col[0] or self.position[2] != col[2]:
            if col2 in self.gl.cubes.cubes and self.shift <= 0:
                self.gl.blockSound.playStepSound(
                    self.gl.cubes.cubes[col2].name, custom=15, position=self.position
                )
        if not self.bInAir:
            for i in range(1, 6):
                col21 = roundPos((col[0], col[1] - i, col[2]))
                if col21 not in self.gl.cubes.cubes:
                    self.bInAir = True
                    if self.playerFallY < col[1]:
                        self.playerFallY = round(col[1] - self.lastPlayerPosOnGround[1])
                else:
                    self.bInAir = False
                    break
        else:
            self.lastPlayerPosOnGround = col

        if self.bInAir and col2 in self.gl.cubes.cubes:
            hp = self.hp
        # FIX: ensure position is a mutable list
        self.position = list(col)

    def collide(self, pos):
        p = list(pos)
        np = roundPos(pos)
        for face in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)):
            for i in (0, 1, 2):
                if not face[i]:
                    continue
                d = (p[i] - np[i]) * face[i]
                pad = 0.25
                if d < pad:
                    continue
                for dy in (0, 1):
                    op = list(np)
                    op[1] -= dy
                    op[i] += face[i]
                    if tuple(op) in self.gl.cubes.collidable:
                        p[i] -= (d - pad) * face[i]
                        if face[1]:
                            self.dy = 0
                        break
        return tuple(p)
