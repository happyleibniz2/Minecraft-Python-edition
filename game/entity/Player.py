import math
from random import randint
import pyglet
from OpenGL.GL import *
from game.blocks.BlockEvent import *
from functions import roundPos
from game.blocks.DestroyBlock import DestroyBlock
from settings import *

class Player:
    def __init__(self, x=0, y=0, z=0, rotation=None, gl=None):
        if rotation is None:
            rotation = [0, 0]
        print("Init Player class...")
        self.is_spectator = False
        self.position, self.rotation = [x, y, z], rotation
        self.speed = 4.0
        self.gl = gl
        self.gl.allowEvents.setdefault("collisions", True)
        self.gravity = 5.8
        self.tVel = 50
        self.dy = 0
        self.shift = 0
        self.cameraShake = [0, False]
        self.canShake = True
        self.acceleration = 0.0
        self.current_move_speed = 0.0
        self.lastShiftPos = self.position
        self.cameraType = 1
        self.hp = -1
        self.bInAir = False
        self.playerDead = False
        self.inventory = None

        self.lastPlayerPosOnGround = [0, 0, 0]
        self.playerFallY = 0

        self.kW, self.kS, self.kA, self.kD = 0, 0, 0, 0
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

    def setShift(self, b):
        if b:
            if self.shift < 0.17:
                self.shift += 0.05
        else:
            if self.shift > 0:
                self.shift -= 0.05

    def updatePosition(self, dt):
        if pygame.key.get_pressed()[pygame.K_p]:
            self.is_spectator = not self.is_spectator
        if pygame.key.get_pressed()[pygame.K_l]:
            self.gl.player.inventory.addBlock("grass")
            self.gl.player.inventory.addBlock("stone")
            self.gl.player.inventory.addBlock("log_birch")
            self.gl.player.inventory.addBlock("cactus")
            self.gl.player.inventory.addBlock("water")
            self.gl.player.inventory.addBlock("crafting_table")
            self.gl.player.inventory.addBlock("debug")
            self.gl.player.inventory.addBlock("ancient_debris")
            self.gl.player.inventory.addBlock("tnt")
            self.gl.player.inventory.addBlock("log_oak")

        if self.gl.allowEvents["movePlayer"]:
            rdx, rdy = pygame.mouse.get_pos()
            rdx, rdy = rdx - self.gl.WIDTH // 2, rdy - self.gl.HEIGHT // 2
            rdx /= 8
            rdy /= 8
            self.rotation[0] += rdy
            self.rotation[1] += rdx
            if self.rotation[0] > 90:
                self.rotation[0] = 90
            elif self.rotation[0] < -90:
                self.rotation[0] = -90

            DX, DY, DZ = 0, 0, 0
            minKd = 0.08 * dt * 60

            rotY = self.rotation[1] / 180 * math.pi
            key = pygame.key.get_pressed()
            if not key[pygame.K_w]:
                self.kW = 0
            if not key[pygame.K_s]:
                self.kS = 0
            if not key[pygame.K_a]:
                self.kA = 0
            if not key[pygame.K_d]:
                self.kD = 0

            move_input = 0
            if self.kW > 0 or key[pygame.K_w]:
                move_input += 1
            if self.kS > 0 or key[pygame.K_s]:
                move_input += 1
            if self.kA > 0 or key[pygame.K_a]:
                move_input += 1
            if self.kD > 0 or key[pygame.K_d]:
                move_input += 1

            if move_input:
                self.current_move_speed = min(self.current_move_speed + 0.035 * dt * 60, self.speed)
            else:
                self.current_move_speed = max(self.current_move_speed - 0.065 * dt * 60, 0.0)

            if key[pygame.K_LCTRL]:
                self.acceleration = 0.009 * dt * 60
            else:
                self.acceleration = 0

            if self.kW > 0 or key[pygame.K_w]:
                DX += self.current_move_speed * math.sin(rotY) * dt
                DZ -= self.current_move_speed * math.cos(rotY) * dt
                self.setCameraShake(dt)
                if self.kW > 0:
                    self.kW -= minKd
            if self.kS > 0 or key[pygame.K_s]:
                DX -= self.current_move_speed * math.sin(rotY) * dt
                DZ += self.current_move_speed * math.cos(rotY) * dt
                self.setCameraShake(dt)
                if self.kS > 0:
                    self.kS -= minKd
            if self.kA > 0 or key[pygame.K_a]:
                DX -= self.current_move_speed * math.cos(rotY) * dt
                DZ -= self.current_move_speed * math.sin(rotY) * dt
                self.setCameraShake(dt)
                if self.kA > 0:
                    self.kA -= minKd
            if self.kD > 0 or key[pygame.K_d]:
                DX += self.current_move_speed * math.cos(rotY) * dt
                DZ += self.current_move_speed * math.sin(rotY) * dt
                self.setCameraShake(dt)
                if self.kD > 0:
                    self.kD -= minKd

            if key[pygame.K_SPACE]:
                if self.is_spectator:
                    self.position[1] += 0.08 * dt * 60
                else:
                    if key[pygame.K_w]:
                        self.kW = 2
                    if key[pygame.K_a]:
                        self.kA = 2
                    if key[pygame.K_s]:
                        self.kS = 2
                    if key[pygame.K_d]:
                        self.kD = 2
                    self.jump()

            if key[pygame.K_LSHIFT]:
                if self.is_spectator:
                    self.position[1] -= 0.05 * dt * 60
                else:
                    self.setShift(True)
                    self.acceleration = -0.01 * dt * 60
            else:
                self.setShift(False)
                self.acceleration = 0

            sub_steps = 10
            sub_dt = dt / sub_steps
            DX_sub = DX / sub_steps
            DZ_sub = DZ / sub_steps
            for _ in range(sub_steps):
                self.move(sub_dt, DX_sub, 0, DZ_sub)

        else:
            self.move(dt, 0, 0, 0)

    def jump(self):
        if not self.dy:
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
        if self.position[0] != col[0] or self.position[2] != col[2]:
            if col2 in self.gl.cubes.cubes and self.shift <= 0:
                self.gl.blockSound.playStepSound(self.gl.cubes.cubes[col2].name, custom=15)

        if self.position[0] != col[0] or self.position[2] != col[2]:
            if self.gl.fov < FOV + 20:
                self.gl.fov += 0.2 * dt * 60
            else:
                self.gl.fov = FOV + 20
        else:
            if self.gl.fov > FOV:
                self.gl.fov -= 0.2 * dt * 60
            else:
                self.gl.fov = FOV
        self.gl.set3d()

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
        self.position = col

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