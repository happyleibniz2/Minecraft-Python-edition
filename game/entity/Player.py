import math
from random import randint
import pyglet
from OpenGL.GL import *
from game.blocks.BlockEvent import *
from functions import roundPos
from game.blocks.DestroyBlock import DestroyBlock
from game.Items import attack_damage, attack_speed, is_item, is_tool
from settings import *

class Player:
    WALK_SPEED = 4.317
    SPRINT_MULTIPLIER = 1.3
    SNEAK_MULTIPLIER = 0.3
    WIDTH = 0.6
    HEIGHT = 1.8
    FEET_OFFSET = PLAYER_EYE_HEIGHT
    JUMP_VELOCITY = 3.8

    def __init__(self, x=0, y=0, z=0, rotation=None, gl=None):
        if rotation is None:
            rotation = [0, 0]
        print("Init Player class...")
        self.is_spectator = False
        self.in_water = False
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
        self.attack_cooldown = 999.0
        self.hurt_cooldown = 0.0
        self.last_damage = 0.0
        self.hurt_time = 0.0
        self.spawn_protection = 3.0
        self.fall_distance = 0.0
        self.velocity_x = 0.0
        self.velocity_z = 0.0
        self.hand_swing = 0.0
        self.hp = -1
        self.bInAir = False
        self.playerDead = False
        self.inventory = None

        self.lastPlayerPosOnGround = [0, 0, 0]
        self.playerFallY = 0

        self.gl.allowEvents["collisions"] = True

    def reset_for_world(self, position=(0, -90, 0)):
        """Clear state that must not leak from one world into the next."""
        self.position = list(position)
        self.rotation = [0, 0]
        self.is_spectator = False
        self.in_water = False
        self.speed = self.WALK_SPEED
        self.dy = 0
        self.shift = 0
        self.cameraShake = [0, False]
        self.canShake = True
        self.lastShiftPos = self.position.copy()
        self.cameraType = 1
        self.is_sprinting = False
        self._mouse_dx = 0.0
        self._mouse_dy = 0.0
        self.attack_cooldown = 999.0
        self.hurt_cooldown = 0.0
        self.last_damage = 0.0
        self.hurt_time = 0.0
        self.spawn_protection = 3.0
        self.fall_distance = 0.0
        self.velocity_x = 0.0
        self.velocity_z = 0.0
        self.hand_swing = 0.0
        self.hp = -1
        self.bInAir = False
        self.playerDead = False
        self.lastPlayerPosOnGround = self.position.copy()
        self.playerFallY = 0
        self.gl.allowEvents["collisions"] = True
        self.gl.fov = FOV

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
        self.attack_cooldown += max(0.0, dt)
        self.hand_swing = max(0.0, self.hand_swing - max(0.0, dt) * 3.5)
        self._tick_damage(dt)
        if not self.gl.allowEvents["movePlayer"]:
            self.clear_look()
            self.is_sprinting = False
            self._update_fov(dt)
            self.move(dt, 0, 0, 0)
            return

        self._apply_mouse_look()
        key = pygame.key.get_pressed()
        self.in_water = self._is_in_water()
        forward = int(key[pygame.K_w]) - int(key[pygame.K_s])
        strafe = int(key[pygame.K_d]) - int(key[pygame.K_a])
        input_length = math.hypot(forward, strafe)
        if input_length:
            forward /= input_length
            strafe /= input_length

        sneaking = key[pygame.K_LSHIFT] and not self.is_spectator and not self.in_water
        sprinting = key[pygame.K_LCTRL] and forward > 0 and not sneaking
        move_speed = self.speed
        if sprinting:
            move_speed *= self.SPRINT_MULTIPLIER
        elif sneaking:
            move_speed *= self.SNEAK_MULTIPLIER
        if self.in_water:
            move_speed *= 0.5

        rot_y = math.radians(self.rotation[1])
        direction_x = forward * math.sin(rot_y) + strafe * math.cos(rot_y)
        direction_z = -forward * math.cos(rot_y) + strafe * math.sin(rot_y)
        desired_x = direction_x * move_speed
        desired_z = direction_z * move_speed
        grounded = self.dy <= 0 and self._has_support(
            self.position[0], self.position[1], self.position[2])

        if self.is_spectator or grounded:
            self.velocity_x = desired_x
            self.velocity_z = desired_z
        elif self.in_water:
            self.velocity_x = desired_x
            self.velocity_z = desired_z
        else:
            # Minecraft air control: retain momentum, add only a small input
            # acceleration, then apply the per-tick 0.91 horizontal drag.
            air_acceleration = 8.0
            self.velocity_x += direction_x * air_acceleration * dt
            self.velocity_z += direction_z * air_acceleration * dt
            drag = 0.91 ** (dt * 20)
            self.velocity_x *= drag
            self.velocity_z *= drag
            speed = math.hypot(self.velocity_x, self.velocity_z)
            max_air_speed = self.speed * self.SPRINT_MULTIPLIER
            if speed > max_air_speed and speed > 0:
                scale = max_air_speed / speed
                self.velocity_x *= scale
                self.velocity_z *= scale

        if self.in_water and not self.is_spectator:
            current_x, current_z = self.gl.cubes.get_water_current(self.position)
            self.velocity_x += current_x * 1.39
            self.velocity_z += current_z * 1.39

        dx = self.velocity_x * dt
        dz = self.velocity_z * dt

        if self.is_spectator:
            vertical = int(key[pygame.K_SPACE]) - int(key[pygame.K_LSHIFT])
            self.position = [
                self.position[0],
                self.position[1] + vertical * self.speed * dt,
                self.position[2],
            ]
            # flying is not falling; clear fall state so leaving spectator
            # never applies phantom fall damage
            self.dy = 0
            self.velocity_x = desired_x
            self.velocity_z = desired_z
            self.playerFallY = 0
            self.bInAir = False
            self.lastPlayerPosOnGround = list(self.position)
            self.setShift(False, dt)
        else:
            self.setShift(sneaking, dt)
            if self.in_water:
                if key[pygame.K_SPACE]:
                    self.dy = min(2.4, self.dy + 8 * dt)
                if key[pygame.K_LSHIFT]:
                    self.dy = max(-2.4, self.dy - 8 * dt)
            elif key[pygame.K_SPACE]:
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

        actual_x = self.position[0] - start_x
        actual_z = self.position[2] - start_z
        if abs(dx) > 1e-6 and abs(actual_x) < abs(dx) * 0.5:
            self.velocity_x = 0.0
        if abs(dz) > 1e-6 and abs(actual_z) < abs(dz) * 0.5:
            self.velocity_z = 0.0
        moved = abs(actual_x) > 1e-6 or abs(actual_z) > 1e-6
        self.is_sprinting = sprinting and moved
        if moved and not self.is_spectator and not self.in_water:
            self.setCameraShake(dt)
            ground = roundPos((self.position[0],
                               self.position[1] - self.FEET_OFFSET - 0.5,
                               self.position[2]))
            if ground in self.gl.cubes.cubes and not sneaking:
                self.gl.blockSound.playStepSound(self.gl.cubes.cubes[ground].name,
                                                 custom=15, position=self.position)
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

    def _tick_damage(self, dt):
        previous = self.hurt_cooldown
        self.hurt_cooldown = max(0.0, self.hurt_cooldown - max(0.0, dt))
        self.hurt_time = max(0.0, self.hurt_time - max(0.0, dt))
        self.spawn_protection = max(0.0, getattr(self, "spawn_protection", 0.0) - max(0.0, dt))
        if previous > 0 and self.hurt_cooldown == 0:
            self.last_damage = 0.0

    def hurt(self, amount, source="generic", attacker=None):
        """Minecraft-style damage with ten ticks of invulnerability."""
        source = str(source)
        if ((self.is_spectator and source != "void") or self.playerDead or self.hp <= 0
                or (getattr(self, "spawn_protection", 0.0) > 0 and source != "void")):
            return False
        amount = max(0.0, float(amount))
        if amount <= 0:
            return False

        if self.hurt_cooldown > 0:
            if amount <= self.last_damage:
                return False
            applied = amount - self.last_damage
            self.last_damage = amount
            self.hp = max(0, self.hp - applied)
            if float(self.hp).is_integer():
                self.hp = int(self.hp)
            if self.hp <= 0:
                self.dead()
            return True
        else:
            applied = amount

        self.last_damage = amount
        self.hurt_cooldown = 0.5
        self.hurt_time = 0.5
        self.cameraShake[0] = -0.08
        self.hp = max(0, self.hp - applied)
        if float(self.hp).is_integer():
            self.hp = int(self.hp)

        if attacker is not None:
            dx = self.position[0] - attacker.position[0]
            dz = self.position[2] - attacker.position[2]
            distance = math.hypot(dx, dz)
            if distance > 1e-6:
                self.velocity_x += dx / distance * 2.6
                self.velocity_z += dz / distance * 2.6
                self.dy = max(self.dy, 2.0)

        self.gl.blockSound.damageByBlock(source, self.hp)
        if self.hp <= 0:
            self.dead()
        return True

    def give_debug_items(self):
        items = [
            "grass", "stone", "log_birch", "cactus", "water_bucket",
            "crafting_table", "debug", "ancient_debris", "tnt", "log_oak", "torch",
        ]
        # every wooden tool that has a texture loaded
        items += [name for name in (
            "wooden_pickaxe", "wooden_axe", "wooden_shovel",
            "wooden_hoe", "wooden_sword",
        ) if name in self.gl.inventory_textures]
        # spawn eggs for every registered entity, like Minecraft's creative tab
        items += sorted(getattr(self.gl, "spawn_egg_items", {}))
        for item in items:
            self.inventory.addBlock(item)

    def dropSelectedItem(self, drop_stack=False):
        """Throw one item with Q, or the whole stack with Ctrl+Q."""
        slot = self.inventory.activeInventory
        stack = self.inventory.inventory.get(slot, ["", 0])
        if not stack[0] or stack[1] <= 0:
            return False

        count = stack[1] if drop_stack else 1
        sight = self.get_sight_vector()
        origin = (
            self.position[0] + sight[0] * 0.7,
            self.position[1] - 0.35 + sight[1] * 0.7,
            self.position[2] + sight[2] * 0.7,
        )
        velocity = (
            sight[0] * 5.0,
            1.5 + sight[1] * 5.0,
            sight[2] * 5.0,
        )
        self.gl.droppedBlock.addBlock(
            origin, stack[0], velocity=velocity, pickup_delay=1.0, count=count,
        )

        remaining = stack[1] - count
        self.inventory.inventory[slot] = [stack[0], remaining] if remaining > 0 else ["", 0]
        return True

    def renderHeldItem(self):
        """Render the selected item/hand in first person, Minecraft-style."""
        if (self.playerDead or self.cameraType != 1
                or not self.gl.allowEvents.get("showCrosshair", True)):
            return

        stack = self.inventory.inventory.get(self.inventory.activeInventory, ["", 0])
        name = stack[0] if stack[1] > 0 else ""
        swing = math.sin((1.0 - self.hand_swing) * math.pi) if self.hand_swing > 0 else 0.0
        bob = self.cameraShake[0] * 35

        glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT | GL_COLOR_BUFFER_BIT)
        glPushMatrix()
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glTranslatef(self.gl.WIDTH - 74 + swing * 18, 42 - swing * 28 + bob, 0)
            glRotatef(-24 - swing * 32, 0, 0, 1)
            glColor4f(1, 1, 1, 1)

            image = self.gl.inventory_textures.get(name)
            if image is not None:
                image.blit(-48, -20, width=96, height=96)
            else:
                # Empty-hand fallback; no player-arm texture exists yet.
                glDisable(GL_TEXTURE_2D)
                glColor4f(0.72, 0.47, 0.30, 1)
                glBegin(GL_QUADS)
                glVertex2f(-18, -55)
                glVertex2f(30, -55)
                glVertex2f(24, 45)
                glVertex2f(-8, 38)
                glEnd()
        finally:
            glPopMatrix()
            glPopAttrib()

    def _has_support(self, x, y, z):
        standing_offset = self.FEET_OFFSET + 0.5
        support_y = round(y - standing_offset)
        if abs(y - (support_y + standing_offset)) > 0.1:
            return False

        edge = self.WIDTH / 2 - 0.01
        for offset_x in (-edge, edge):
            for offset_z in (-edge, edge):
                if roundPos((x + offset_x, support_y, z + offset_z)) in self.gl.cubes.collidable:
                    return True
        return False

    def _is_in_water(self):
        return self._position_in_water(self.position)

    def _position_in_water(self, position):
        bounds = self._player_bounds(position)
        ranges = [
            range(math.floor(bounds[0][axis] - 0.5),
                  math.ceil(bounds[1][axis] + 0.5) + 1)
            for axis in range(3)
        ]
        for x in ranges[0]:
            for y in ranges[1]:
                for z in ranges[2]:
                    if (x, y, z) not in self.gl.cubes.fluids:
                        continue
                    block_min = (x - 0.5, y - 0.5, z - 0.5)
                    block_max = (x + 0.5, y + 0.5, z + 0.5)
                    if all(bounds[1][axis] > block_min[axis] + 1e-9
                           and bounds[0][axis] < block_max[axis] - 1e-9
                           for axis in range(3)):
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
        if (self.dy <= 0 and not getattr(self, "bInAir", False)
                and self._has_support(self.position[0], self.position[1], self.position[2])):
            self.dy = self.JUMP_VELOCITY

    def move(self, dt, dx, dy, dz):
        if self.is_spectator:
            dt = 0
        if self.in_water:
            self.dy = max(-3, min(3, self.dy - dt * self.gravity * 0.2))
            self.dy *= 0.8 ** (dt * 20)
        else:
            self.dy -= dt * self.gravity
            self.dy = max(self.dy, -self.tVel)
        dy += self.dy * dt
        vertical_step = dy

        if self.dy > 19.8:
            self.dy = 19.8

        x, y, z = self.position
        if self.is_spectator:
            self.position = [x + dx, y + dy, z + dz]
            return

        target = (x + dx, y + dy, z + dz)
        col = self.collide(target)
        col2 = roundPos((col[0], col[1] - 2, col[2]))
        landed = vertical_step < 0 and col[1] > target[1] + 1e-6
        self.canShake = landed
        water_contact = self.in_water or self._position_in_water(col)
        if water_contact:
            self.in_water = True
            self.bInAir = False
            self.playerFallY = 0
            self.fall_distance = 0.0
            self.lastPlayerPosOnGround = list(col)
            self.position = list(col)
            return

        if vertical_step < 0 and not landed:
            self.fall_distance += -vertical_step
            self.playerFallY = round(self.fall_distance)

        if landed:
            impact_distance = self.fall_distance
            damage = self.fall_damage(impact_distance)
            if damage > 0:
                self.hurt(damage, "fall")
            self.fall_distance = 0.0
            self.playerFallY = 0
            self.bInAir = False
            self.lastPlayerPosOnGround = list(col)
            if impact_distance > 3.0 and col2 in self.gl.cubes.cubes:
                particle_count = min(24, max(6, round(impact_distance * 2)))
                self.gl.particles.addParticle((col[0], col[1] - 1, col[2]),
                                              self.gl.cubes.cubes[col2],
                                              direction="down", count=particle_count)
        else:
            self.bInAir = not self._has_support(col[0], col[1], col[2])
        self.position = list(col)

    @staticmethod
    def fall_damage(distance):
        return math.ceil(max(0.0, float(distance) - 3.0))

    def dead(self):
        self.playerDead = True
        if hasattr(self.gl.gui, "hideText"):
            self.gl.gui.hideText()
        self.gl.deathScreen()
        # only real storage drops; the crafting grid is returned separately
        droppable = list(self.inventory.HOTBAR_SLOTS) + list(self.inventory.STORAGE_SLOTS)
        for slot in droppable:
            name, count = self.inventory.inventory.get(slot, ["", 0])
            for _ in range(count):
                if not name:
                    continue
                self.gl.droppedBlock.addBlock((
                    self.position[0] + randint(-2, 2), self.position[1], self.position[2] + randint(-2, 2)
                ), name)
            self.inventory.inventory[slot] = ["", 0]
        self.inventory.clearCraftingSlots()

    def mouseEvent(self, button, dt):
        sight = self.get_sight_vector()
        blockByVec = self.gl.cubes.hitTest(self.position, sight)

        if button == 1:
            if self.hand_swing == 0:
                self.hand_swing = 1.0
            hit_test = getattr(self.gl, "hitTestEntity", None)
            entity = hit_test(self.position, sight, 3.0) if hit_test else None
            if entity is not None:
                self.gl.destroy.destroyStage = -1
                self.attackEntity(entity)
                return
            if blockByVec[0]:
                self.gl.destroy.destroy(self.gl.cubes.cubes[blockByVec[0]].name, blockByVec, dt)
            else:
                self.gl.destroy.destroyStage = -1
        else:
            self.gl.destroy.destroyStage = -1

        if button == 2 and blockByVec[0]:
            # "pick block": swap a matching stack into the selected hotbar slot
            if self.inventory.inventory[self.inventory.activeInventory][1] == 0:
                target = self.gl.cubes.cubes[blockByVec[0]].name
                searchable = (list(self.inventory.HOTBAR_SLOTS) +
                              list(self.inventory.STORAGE_SLOTS))
                for slot in searchable:
                    stack = self.inventory.inventory.get(slot, ["", 0])
                    if stack[0] == target and stack[1] != 0:
                        self.inventory.inventory[self.inventory.activeInventory] = [stack[0], stack[1]]
                        self.inventory.inventory[slot] = ["", 0]
                        self.gl.gui.showText(target)
                        break
        if button == 3:
            self.hand_swing = 1.0
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
            selected = self.inventory.inventory[self.inventory.activeInventory]
            spawn_eggs = getattr(self.gl, "spawn_egg_items", {})
            if selected[0] in spawn_eggs and selected[1]:
                anchor = blockByVec[1] or blockByVec[0]
                if anchor:
                    # Minecraft spawns the mob against the clicked face
                    spawn_pos = [anchor[0], anchor[1] + 1.75, anchor[2]]
                    entity = self.gl.spawn_entity_by_id(spawn_eggs[selected[0]], spawn_pos)
                    if entity is not None:
                        self.inventory.inventory[self.inventory.activeInventory][1] -= 1
                        if self.inventory.inventory[self.inventory.activeInventory][1] <= 0:
                            self.inventory.inventory[self.inventory.activeInventory] = ["", 0]
                return

            if selected[0] == "water_bucket" and selected[1] and blockByVec[1]:
                water_pos = tuple(blockByVec[1])
                player_pos = tuple(roundPos((self.position[0], self.position[1] - 1, self.position[2])))
                player_head = tuple(roundPos(self.position))
                if water_pos not in (player_pos, player_head):
                    self.gl.cubes.place_water_source(water_pos)
                return
            placement = blockByVec[1]
            if placement is None:
                fluid_hit = self.gl.cubes.hitTest(self.position, self.get_sight_vector(), include_fluids=True)
                if fluid_hit[0] in self.gl.cubes.fluids:
                    placement = fluid_hit[0]
            if placement:
                blockByVec = placement[0], placement[1], placement[2]
                held_name = self.inventory.inventory[self.inventory.activeInventory][0]
                if held_name in self.gl.block and not is_item(held_name) and \
                        self.inventory.inventory[self.inventory.activeInventory][1] and \
                        not self.intersects_block(blockByVec):
                    placed = self.gl.cubes.add(blockByVec, held_name, now=True)
                    if placed:
                        self.gl.blockSound.playBlockSound(self.gl.cubes.cubes[blockByVec].name,
                                                         position=blockByVec)
                        self.inventory.inventory[self.inventory.activeInventory][1] -= 1

    def attackEntity(self, entity):
        """Perform a full-strength Minecraft melee attack when cooled down."""
        if self.is_spectator or self.playerDead or entity is None:
            return False
        stack = self.inventory.inventory.get(self.inventory.activeInventory, ["", 0])
        held = stack[0] if stack[1] else ""
        cooldown = 1.0 / attack_speed(held)
        if self.attack_cooldown < cooldown:
            return False

        self.attack_cooldown = 0.0
        damaged = entity.hurt(attack_damage(held), self)
        if damaged and is_tool(held):
            self.inventory.damage_tool(self.inventory.activeInventory, 1)
        return damaged

    def collide(self, pos):
        if pos[1] < WORLD_MIN_Y - 64 and not self.playerDead:
            self.hurt(4, "void")

        resolved = list(self.position)
        movement = [pos[index] - resolved[index] for index in range(3)]
        for axis in (1, 0, 2):
            allowed = self._resolve_axis(resolved, movement[axis], axis)
            resolved[axis] += allowed
            if axis == 1 and abs(allowed - movement[axis]) > 1e-9:
                self.dy = 0
        return tuple(resolved)

    def _resolve_axis(self, position, amount, axis):
        if abs(amount) <= 1e-12:
            return 0.0
        bounds = self._player_bounds(position)
        moved = position.copy()
        moved[axis] += amount
        moved_bounds = self._player_bounds(moved)
        sweep_min = tuple(min(bounds[0][i], moved_bounds[0][i]) for i in range(3))
        sweep_max = tuple(max(bounds[1][i], moved_bounds[1][i]) for i in range(3))
        allowed = amount

        ranges = [
            range(math.floor(sweep_min[i] - 0.5), math.ceil(sweep_max[i] + 0.5) + 1)
            for i in range(3)
        ]
        for block_x in ranges[0]:
            for block_y in ranges[1]:
                for block_z in ranges[2]:
                    if (block_x, block_y, block_z) not in self.gl.cubes.collidable:
                        continue
                    block_min = (block_x - 0.5, block_y - 0.5, block_z - 0.5)
                    block_max = (block_x + 0.5, block_y + 0.5, block_z + 0.5)
                    if any(bounds[1][other] <= block_min[other] + 1e-9
                           or bounds[0][other] >= block_max[other] - 1e-9
                           for other in range(3) if other != axis):
                        continue
                    overlapping = (bounds[0][axis] < block_max[axis] - 1e-9
                                   and bounds[1][axis] > block_min[axis] + 1e-9)
                    if overlapping:
                        block_center = (block_min[axis] + block_max[axis]) / 2
                        moving_deeper = (abs(position[axis] + amount - block_center)
                                         <= abs(position[axis] - block_center))
                        if moving_deeper:
                            allowed = 0.0
                        continue
                    if amount > 0 and bounds[1][axis] <= block_min[axis] + 1e-9:
                        allowed = min(allowed, block_min[axis] - bounds[1][axis])
                    elif amount < 0 and bounds[0][axis] >= block_max[axis] - 1e-9:
                        allowed = max(allowed, block_max[axis] - bounds[0][axis])
        return allowed

    def intersects_block(self, block_position):
        bounds = self._player_bounds(self.position)
        block_min = tuple(value - 0.5 for value in block_position)
        block_max = tuple(value + 0.5 for value in block_position)
        return all(bounds[1][axis] > block_min[axis] + 1e-9
                   and bounds[0][axis] < block_max[axis] - 1e-9
                   for axis in range(3))

    @classmethod
    def _player_bounds(cls, position):
        half_width = cls.WIDTH / 2
        return (
            (position[0] - half_width, position[1] - cls.FEET_OFFSET,
             position[2] - half_width),
            (position[0] + half_width,
             position[1] - cls.FEET_OFFSET + cls.HEIGHT,
             position[2] + half_width),
        )

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
