import math
from random import randint
import pyglet
from OpenGL.GL import *
from game.blocks.BlockEvent import *
from functions import roundPos
from game.blocks.DestroyBlock import DestroyBlock
from settings import *

class Player:
    WALK_SPEED = 4.317
    SPRINT_MULTIPLIER = 1.3
    SNEAK_MULTIPLIER = 0.3

    def __init__(self, x=0, y=0, z=0, rotation=None, gl=None):
        if rotation is None:
            rotation = [0, 0]
        print("Init Player class...")
        self.is_spectator = False
        self.position, self.rotation = [x, y, z], rotation
        self.speed = self.WALK_SPEED
        self.gl = gl
        self.gl.allowEvents.setdefault("collisions", True)
        self.gravity = 5.8
        self.tVel = 50
        self.dy = 0
        self.shift = 0
        self.cameraShake = [0, False]
        self.canShake = True
        self.lastShiftPos = self.position
        self.cameraType = 1
        self.is_sprinting = False
        self.mouse_sensitivity = MOUSE_SENSITIVITY
        self._mouse_dx = 0.0
        self._mouse_dy = 0.0
        self.hp = -1
        self.bInAir = False
        self.playerDead = False
        self.inventory = None

        self.lastPlayerPosOnGround = [0, 0, 0]
        self.playerFallY = 0

        self.gl.allowEvents["collisions"] = True

    @staticmethod
    def get_physics_dt():
        fps = max(MAX_FPS, 30)
        return min(max(1.0 / fps, 0.016), 0.05)

    def updateView(self):
        """Apply the player's view transformation (camera). No push/pop – caller handles it."""
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glTranslatef(-self.position[0],
                     -self.position[1] + self.shift + self.cameraShake[0],
                     -self.position[2])

    def setCameraShake(self, dt):
        if not self.canShake or self.shift > 0:
            return

        if not self.cameraShake[1]:
            self.cameraShake[0] -= 0.007 * dt * 60
            if self.cameraShake[0] < -0.1:
                self.cameraShake[1] = True
        else:
            self.cameraShake[0] += 0.007 * dt * 60
            if self.cameraShake[0] > 0.1:
                self.cameraShake[1] = False

    def setShift(self, enabled, dt):
        target = 0.17 if enabled else 0
        step = 1.5 * dt
        if self.shift < target:
            self.shift = min(target, self.shift + step)
        elif self.shift > target:
            self.shift = max(target, self.shift - step)

    def updatePosition(self, dt):
        if not self.gl.allowEvents["movePlayer"]:
            self.clear_look()
            self.is_sprinting = False
            self._update_fov(dt)
            self.move(dt, 0, 0, 0)
            return

        self._apply_mouse_look()
        key = pygame.key.get_pressed()
        forward = int(key[pygame.K_w]) - int(key[pygame.K_s])
        strafe = int(key[pygame.K_d]) - int(key[pygame.K_a])
        input_length = math.hypot(forward, strafe)
        if input_length:
            forward /= input_length
            strafe /= input_length

        sneaking = key[pygame.K_LSHIFT] and not self.is_spectator
        sprinting = key[pygame.K_LCTRL] and forward > 0 and not sneaking
        move_speed = self.speed
        if sprinting:
            move_speed *= self.SPRINT_MULTIPLIER
        elif sneaking:
            move_speed *= self.SNEAK_MULTIPLIER

        rot_y = math.radians(self.rotation[1])
        dx = (forward * math.sin(rot_y) + strafe * math.cos(rot_y)) * move_speed * dt
        dz = (-forward * math.cos(rot_y) + strafe * math.sin(rot_y)) * move_speed * dt

        if self.is_spectator:
            vertical = int(key[pygame.K_SPACE]) - int(key[pygame.K_LSHIFT])
            self.position = [
                self.position[0],
                self.position[1] + vertical * self.speed * dt,
                self.position[2],
            ]
            self.setShift(False, dt)
        else:
            self.setShift(sneaking, dt)
            if key[pygame.K_SPACE]:
                self.jump()

        start_x = self.position[0]
        start_z = self.position[2]
        sub_steps = 1 if self.is_spectator else 10
        sub_dt = dt / sub_steps
        step_x = dx / sub_steps
        step_z = dz / sub_steps
        for _ in range(sub_steps):
            move_x = step_x
            move_z = step_z
            sneak_grounded = (sneaking and self.dy <= 0 and
                               self._has_support(self.position[0], self.position[1], self.position[2]))
            if sneak_grounded:
                move_x, move_z = self._limit_sneak_movement(move_x, move_z)
            ground_y = self.position[1]
            self.move(sub_dt, move_x, 0, move_z)
            if sneak_grounded and self._has_support(self.position[0], ground_y, self.position[2]):
                self.position = [self.position[0], ground_y, self.position[2]]
                self.dy = 0
                self.bInAir = False

        moved = abs(self.position[0] - start_x) > 1e-6 or abs(self.position[2] - start_z) > 1e-6
        self.is_sprinting = sprinting and moved
        if moved and not self.is_spectator:
            self.setCameraShake(dt)
            ground = roundPos((self.position[0], self.position[1] - 2, self.position[2]))
            if ground in self.gl.cubes.cubes and not sneaking:
                self.gl.blockSound.playStepSound(self.gl.cubes.cubes[ground].name, custom=15)
        self._update_fov(dt)

    def queue_look(self, dx, dy):
        self._mouse_dx += dx
        self._mouse_dy += dy

    def clear_look(self):
        self._mouse_dx = 0.0
        self._mouse_dy = 0.0

    def _apply_mouse_look(self):
        if not self._mouse_dx and not self._mouse_dy:
            return
        sensitivity = self.mouse_sensitivity * 0.6 + 0.2
        scale = sensitivity ** 3 * 8 * 0.15
        self.look(self._mouse_dx * scale, self._mouse_dy * scale)
        self.clear_look()

    def look(self, dx, dy):
        self.rotation[0] = max(-90, min(90, self.rotation[0] + dy))
        self.rotation[1] += dx

    def _update_fov(self, dt):
        target_fov = FOV + 10 if self.is_sprinting else FOV
        blend = 1 - math.exp(-10 * dt)
        self.gl.fov += (target_fov - self.gl.fov) * blend

    def give_debug_items(self):
        for block in (
            "grass", "stone", "log_birch", "cactus", "water",
            "crafting_table", "debug", "ancient_debris", "tnt", "log_oak",
        ):
            self.inventory.addBlock(block)

    def _has_support(self, x, y, z):
        support_y = round(y - 1.75)
        if abs(y - (support_y + 1.75)) > 0.1:
            return False

        for offset_x in (-0.24, 0.24):
            for offset_z in (-0.24, 0.24):
                if roundPos((x + offset_x, support_y, z + offset_z)) in self.gl.cubes.collidable:
                    return True
        return False

    def _limit_sneak_movement(self, dx, dz):
        x, y, z = self.position
        if self._has_support(x + dx, y, z + dz):
            return dx, dz
        if dx and self._has_support(x + dx, y, z):
            return dx, 0
        if dz and self._has_support(x, y, z + dz):
            return 0, dz
        return 0, 0

    def jump(self):
        if self._has_support(self.position[0], self.position[1], self.position[2]):
            self.dy = 5.5

    def move(self, dt, dx, dy, dz):
        if self.is_spectator:
            dt = 0
        self.dy -= dt * self.gravity
        self.dy = max(self.dy, -self.tVel)
        dy += self.dy * dt

        if self.dy > 19.8:
            self.dy = 19.8

        x, y, z = self.position
        if self.is_spectator:
            self.position = [x + dx, y + dy, z + dz]
            return

        col = self.collide((x + dx, y + dy, z + dz))
        col2 = roundPos((col[0], col[1] - 2, col[2]))
        self.canShake = self.position[1] == col[1]
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
            if 3 < self.playerFallY:
                self.hp -= 1
                if self.playerFallY < 10:
                    self.hp -= 3
                elif self.playerFallY < 16:
                    self.hp -= 5
                elif self.playerFallY < 23:
                    self.hp -= 8
                elif self.playerFallY < 30:
                    self.hp -= 11
                else:
                    self.hp = 0
                self.gl.blockSound.cntr = 99
                self.gl.blockSound.damageByBlock(self.gl.cubes.cubes[col2].name, self.hp)
            if self.hp <= 0 and not self.playerDead:
                self.dead()

            self.bInAir = False
            self.gl.particles.addParticle((col[0], col[1] - 1, col[2]),
                                          self.gl.cubes.cubes[col2],
                                          direction="down",
                                          count=10)
        self.position = list(col)

    def dead(self):
        self.playerDead = True
        self.gl.deathScreen()
        for i in self.inventory.inventory.items():
            for j in range(i[1][1]):
                self.gl.droppedBlock.addBlock((
                    self.position[0] + randint(-2, 2), self.position[1], self.position[2] + randint(-2, 2)
                ), i[1][0])
            self.inventory.inventory[i[0]] = [i[1][0], 0]

    def mouseEvent(self, button, dt):
        blockByVec = self.gl.cubes.hitTest(self.position, self.get_sight_vector())

        if button == 1 and blockByVec[0]:
            self.gl.destroy.destroy(self.gl.cubes.cubes[blockByVec[0]].name, blockByVec, dt)
        else:
            self.gl.destroy.destroyStage = -1

        if button == 2 and blockByVec[0]:
            if self.inventory.inventory[self.inventory.activeInventory][1] == 0:
                itm = -1
                for item in self.inventory.inventory.items():
                    i = item[1]
                    if i[0] == self.gl.cubes.cubes[blockByVec[0]].name and i[1] != 0:
                        itm = item[0]
                        break
                if itm != -1:
                    self.inventory.inventory[self.inventory.activeInventory] = [
                        self.inventory.inventory[itm][0], self.inventory.inventory[itm][1]]
                    self.inventory.inventory[itm][1] = 0
                    self.gl.gui.showText(self.inventory.inventory[itm][0])
        if button == 3:
            if blockByVec[0] and self.shift <= 0:
                if blockByVec[0] in self.gl.cubes.cubes:
                    if canOpenBlock(self, self.gl.cubes.cubes[blockByVec[0]], self.gl):
                        openBlockInventory(self, self.gl.cubes.cubes[blockByVec[0]], self.gl)
                        return
            if blockByVec[1] and self.shift <= 0:
                if blockByVec[1] in self.gl.cubes.cubes:
                    if canOpenBlock(self, self.gl.cubes.cubes[blockByVec[1]], self.gl):
                        openBlockInventory(self, self.gl.cubes.cubes[blockByVec[1]], self.gl)
                        return
            if blockByVec[1]:
                playerPos = tuple(roundPos((self.position[0], self.position[1] - 1, self.position[2])))
                playerPos2 = tuple(roundPos((self.position[0], self.position[1], self.position[2])))
                blockByVec = blockByVec[1][0], blockByVec[1][1], blockByVec[1][2]
                if self.inventory.inventory[self.inventory.activeInventory][0] and \
                        self.inventory.inventory[self.inventory.activeInventory][1] and blockByVec != playerPos and \
                        blockByVec != playerPos2:
                    self.gl.cubes.add(blockByVec, self.inventory.inventory[self.inventory.activeInventory][0], now=True)
                    self.gl.blockSound.playBlockSound(self.gl.cubes.cubes[blockByVec].name)
                    self.inventory.inventory[self.inventory.activeInventory][1] -= 1

    def collide(self, pos):
        if -90 > pos[1] > -9000:
            if not self.playerDead:
                self.hp -= 2
                self.gl.blockSound.damageByBlock("ahh", 1)
                if self.hp <= 0:
                    self.dead()

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

    def get_sight_vector(self):
        rotX, rotY = -self.rotation[0] / 180 * math.pi, self.rotation[1] / 180 * math.pi
        dx, dz = math.sin(rotY), -math.cos(rotY)
        dy, m = math.sin(rotX), math.cos(rotX)
        return dx * m, dy, dz * m

    def x(self):
        return self.position[0]

    def y(self):
        return self.position[1]

    def z(self):
        return self.position[2]

    def update(self, dt):
        self.updatePosition(dt)
