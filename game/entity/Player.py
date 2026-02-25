import math
from random import randint

import pyglet
from OpenGL.GL import *

from game.blocks.BlockEvent import *
from functions import roundPos, flatten, cube_vertices
from game.blocks.DestroyBlock import DestroyBlock
from settings import *


class Player:
    def __init__(self, gl=None, x=0, y=0, z=0, rotation=[0, 0]):
        print("Init Player class...")
        self.is_spectator = False
        self.position, self.rotation = [x, y, z], rotation
        self.speed = 0.03
        self.gl = gl
        
        # Safely initialize allowEvents with collision setting
        if hasattr(self.gl, 'allowEvents') and self.gl.allowEvents is not None:
            self.gl.allowEvents.setdefault("collisions", True)
        elif self.gl is not None:
            # Initialize allowEvents if it doesn't exist
            if not hasattr(self.gl, 'allowEvents'):
                self.gl.allowEvents = {"collisions": True}
            else:
                self.gl.allowEvents.setdefault("collisions", True)
        
        self.gravity = 5.8
        self.tVel = 50
        self.dy = 0
        self.shift = 0
        self.cameraShake = [0, False]
        self.canShake = True
        self.acceleration = 0
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
    def setCameraShake(self):
        if not self.canShake or self.shift > 0:
            return

        if not self.cameraShake[1]:
            self.cameraShake[0] -= 0.007
            if self.cameraShake[0] < -0.1:
                self.cameraShake[1] = True
        else:
            self.cameraShake[0] += 0.007
            if self.cameraShake[0] > 0.1:
                self.cameraShake[1] = False

    def setShift(self, b):
        if b:
            if self.shift < 0.17:
                self.shift += 0.05
        else:
            if self.shift > 0:
                self.shift -= 0.05

    def updatePosition(self):
        # toggle spectator mode
        if pygame.key.get_pressed()[pygame.K_p]:
            self.is_spectator = not self.is_spectator

        if not self.gl.allowEvents["movePlayer"]:
            # still run a minimal move so gravity applies
            self.move(self.speed, 0, 0, 0)
            return

        # mouse look
        rdx, rdy = pygame.mouse.get_pos()
        rdx, rdy = rdx - self.gl.WIDTH // 2, rdy - self.gl.HEIGHT // 2
        rdx /= 8
        rdy /= 8
        self.rotation[0] += rdy
        self.rotation[1] += rdx
        # clamp pitch
        if self.rotation[0] > 90:
            self.rotation[0] = 90
        elif self.rotation[0] < -90:
            self.rotation[0] = -90

        # frame time in seconds
        from settings import clock
        dt = clock.get_time() / 1000.0
        if dt <= 0:
            dt = 0.001

        DX = DY = DZ = 0
        rotY = self.rotation[1] / 180 * math.pi
        sinY = math.sin(rotY)
        cosY = math.cos(rotY)

        key = pygame.key.get_pressed()
        if key[pygame.K_LCTRL]:
            self.acceleration = 0.009

        # movement keys
        if self.kW > 0 or key[pygame.K_w]:
            DX += sinY * (self.speed + self.acceleration) * dt
            DZ -= cosY * (self.speed + self.acceleration) * dt
            self.setCameraShake()
            if self.kW > 0:
                self.kW -= 0.08
        else:
            self.acceleration = 0
        if self.kS > 0 or key[pygame.K_s]:
            DX -= sinY * self.speed * dt
            DZ += cosY * self.speed * dt
            self.setCameraShake()
            self.acceleration = 0
            if self.kS > 0:
                self.kS -= 0.08
        if self.kA > 0 or key[pygame.K_a]:
            DX -= cosY * self.speed * dt
            DZ -= sinY * self.speed * dt
            self.setCameraShake()
            self.acceleration = 0
            if self.kA > 0:
                self.kA -= 0.08
        if self.kD > 0 or key[pygame.K_d]:
            DX += cosY * self.speed * dt
            DZ += sinY * self.speed * dt
            self.setCameraShake()
            self.acceleration = 0
            if self.kD > 0:
                self.kD -= 0.08

        # vertical movement / jumping
        if key[pygame.K_SPACE]:
            if self.is_spectator:
                self.position[1] += self.speed * dt
            else:
                self.jump()
                if key[pygame.K_w]:
                    self.kW = 1
                if key[pygame.K_a]:
                    self.kA = 1
                if key[pygame.K_s]:
                    self.kS = 1
                if key[pygame.K_d]:
                    self.kD = 1
        if key[pygame.K_LSHIFT]:
            if self.is_spectator:
                self.position[1] -= self.speed * dt
            else:
                self.setShift(True)
                self.acceleration = -0.01
        else:
            self.setShift(False)
            if self.acceleration == -0.01:
                self.acceleration = 0

        # prevent walking off edges while sneaking
        if self.shift > 0 and not self.is_spectator:
            future_x = self.position[0] + DX
            future_z = self.position[2] + DZ
            foot = roundPos((future_x, self.position[1] - 1, future_z))
            if foot not in self.gl.cubes.cubes:
                DX = DZ = 0

        # apply movement and physics
        self.move(dt, DX, DY, DZ)

        # apply camera transformation
        glPushMatrix()
        glRotatef(self.rotation[0], 1, 0, 0)
        glRotatef(self.rotation[1], 0, 1, 0)
        glTranslatef(-self.position[0],
                     -self.position[1] + self.shift + self.cameraShake[0],
                     -self.position[2])

    def jump(self):
        if not self.dy:
            self.dy = 4

    def move(self, dt, dx, dy, dz):
        # spectator mode ignores collisions and gravity completely
        if self.is_spectator:
            self.position = (self.position[0] + dx,
                             self.position[1] + dy,
                             self.position[2] + dz)
            return

        # apply gravity
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
                self.gl.blockSound.playStepSound(self.gl.cubes.cubes[col2].name)
        # Dynamic FOV
        # if self.position[0] != col[0] or self.position[2] != col[2]:
        #    if self.gl.fov < FOV + 20:
        #        self.gl.fov += 0.2
        #    else:
        #        self.gl.fov = FOV + 20
        # else:
        #    if self.gl.fov > FOV:
        #        self.gl.fov -= 0.2
        #    else:
        #        self.gl.fov = FOV
        #
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
                # self.gl.sound.playSound("oof", 0.8)
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
                # Player dead
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

    def mouseEvent(self, button):
        blockByVec = self.gl.cubes.hitTest(self.position, self.get_sight_vector())

        if button == 1 and blockByVec[0]:
            self.gl.destroy.destroy(self.gl.cubes.cubes[blockByVec[0]].name, blockByVec)
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
                    # Player dead
                    self.dead()

        p = list(pos)
        np = roundPos(pos)
        for face in ((-1, 0, 0), (1, 0, 0), (0, -1, 0), (0, 1, 0), (0, 0, -1), (0, 0, 1)):
            for i in (0, 1, 2):
                if not face[i]:
                    continue
                d = (p[i] - np[i]) * face[i]
                # smaller collision padding when sneaking so player hugs edges
                pad = 0.25
                if self.shift > 0:
                    pad = 0.125
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

    def update(self):
        self.updatePosition()
