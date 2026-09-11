import math
from random import randint

import pyglet
from pyglet.gl import GL_QUADS
import pygame
from game.GUI.ModalWindow import ModalWindow
from game.crafting import getCraftingItem
from game.SlotMechanics import (
    MAX_STACK,
    insert_stack,
    is_empty,
    left_click,
    right_click,
)
from settings import *


class Inventory:
    HOTBAR_SLOTS = range(0, 9)
    STORAGE_SLOTS = range(9, 36)
    GRID_SLOTS = range(37, 41)
    RESULT_SLOT = 41

    def __init__(self, glClass):
        self.gl = glClass
        self.inventory = {}
        self.blocksLabel = {}
        self.activeInventory = 0
        self.heartAnimation = []
        self.draggingItem = []
        self.window = None
        self.durability = {}

        # Persistent label used for the cursor stack count. Reusing a single
        # label removes the per-frame pyglet.text.Label allocation that the
        # old updateWindow path made every time the cursor held more than one
        # item.
        self._held_label = pyglet.text.Label(
            "", font_name='Minecraft Rus',
            color=(255, 255, 255, 255), font_size=10)

        old = False
        for i in range(10):
            old = not old
            self.heartAnimation.append([0, '-' if old else '+', randint(3, 8) / 10])
        for i in range(42):
            self.inventory[i] = ["", 0]
            self.blocksLabel[i] = pyglet.text.Label("0",
                                                    font_name='Minecraft Rus',
                                                    color=(255, 255, 255, 255),
                                                    font_size=10,
                                                    x=self.gl.WIDTH // 2, y=60)

    @property
    def insert_order(self):
        """Minecraft fills the hotbar first, then main storage."""
        return list(self.HOTBAR_SLOTS) + list(self.STORAGE_SLOTS)

    def clearCraftingSlots(self):
        """Return grid contents to the inventory, then clear the grid."""
        for slot in self.GRID_SLOTS:
            stack = self.inventory.get(slot, ["", 0])
            if not is_empty(stack):
                self.giveItem(stack[0], stack[1])
            self.inventory[slot] = ["", 0]
        self.inventory[self.RESULT_SLOT] = ["", 0]

        if not is_empty(self.draggingItem):
            self.giveItem(self.draggingItem[0], self.draggingItem[1])
        self.draggingItem = []

    def consumeCraftingIngredients(self):
        for slot in self.GRID_SLOTS:
            stack = self.inventory.get(slot, ["", 0])
            if stack[1] > 0:
                remaining = stack[1] - 1
                self.inventory[slot] = [stack[0], remaining] if remaining > 0 else ["", 0]
        self.inventory[self.RESULT_SLOT] = ["", 0]

    def giveItem(self, name, count=1):
        """Insert items using Minecraft's merge-then-fill order."""
        from game.Items import max_stack_size

        return insert_stack(self.inventory, self.insert_order, name, count,
                            max_stack_size(name))

    def tool_durability(self, slot):
        """Remaining durability of the tool in ``slot``."""
        from game.Items import max_durability

        stack = self.inventory.get(slot, ["", 0])
        if is_empty(stack):
            return 0
        if slot not in self.durability:
            self.durability[slot] = max_durability(stack[0])
        return self.durability[slot]

    def damage_tool(self, slot, amount=1):
        """Spend durability; the tool breaks and vanishes when it runs out."""
        from game.Items import is_tool, max_durability

        stack = self.inventory.get(slot, ["", 0])
        if is_empty(stack) or not is_tool(stack[0]):
            return False

        remaining = self.durability.get(slot)
        if remaining is None:
            remaining = max_durability(stack[0])
        remaining -= amount

        if remaining <= 0:
            self.inventory[slot] = ["", 0]
            self.durability.pop(slot, None)
            return True

        self.durability[slot] = remaining
        return False

    def get_inventory_blocks(self):
        return self.inventory

    def initWindow(self):
        self.window = ModalWindow(self.gl)
        self.window.setWindow(self.gl.gui.GUI_TEXTURES["inventory_window"])
        self.window.clickEvent = self.windowClickEvent
        self.window.closeEvent = self.clearCraftingSlots
        self.window.updateFunctions.append(self.updateWindow)

        x = 16
        for i in self.HOTBAR_SLOTS:
            self.window.cellPositions[i] = [(x, 284), None]
            x += 36

        x, y = 196, 36
        self.window.cellPositions[37] = [(x, y), None]
        x += 36
        self.window.cellPositions[38] = [(x, y), None]
        x = 196
        y += 36
        self.window.cellPositions[39] = [(x, y), None]
        x += 36
        self.window.cellPositions[40] = [(x, y), None]

        self.window.cellPositions[self.RESULT_SLOT] = [(308, 56), None]

        x, y = 16, 168
        for slot in self.STORAGE_SLOTS:
            self.window.cellPositions[slot] = [(x, y), None]
            x += 36
            if x > 304:
                x = 16
                y += 36

    def showWindow(self):
        self.window.show()

    def windowClickEvent(self, button, cell):
        if cell not in self.inventory:
            return

        if cell == self.RESULT_SLOT:
            self.takeCraftingResult(button)
            return

        if button[0]:
            slot, held = left_click(self.inventory[cell], self.draggingItem)
            self.inventory[cell] = slot
            self.draggingItem = held
        elif button[2]:
            slot, held = right_click(self.inventory[cell], self.draggingItem)
            self.inventory[cell] = slot
            self.draggingItem = held

    def takeCraftingResult(self, button):
        """Craft one batch, merging into the held stack like Minecraft."""
        result = self.inventory.get(self.RESULT_SLOT, ["", 0])
        if is_empty(result):
            return

        if is_empty(self.draggingItem):
            self.draggingItem = [result[0], result[1]]
            self.consumeCraftingIngredients()
            return

        if self.draggingItem[0] != result[0]:
            return
        if self.draggingItem[1] + result[1] > MAX_STACK:
            return

        self.draggingItem = [self.draggingItem[0], self.draggingItem[1] + result[1]]
        self.consumeCraftingIngredients()

    def refreshCraftingResult(self):
        crafting_slots = [self.inventory[slot][0] if self.inventory[slot][1] else ""
                          for slot in self.GRID_SLOTS]
        crafting_counts = [self.inventory[slot][1] for slot in self.GRID_SLOTS]
        craftResult = getCraftingItem(crafting_slots, numbers=crafting_counts)

        if craftResult and craftResult[0]:
            self.inventory[self.RESULT_SLOT] = craftResult
        else:
            self.inventory[self.RESULT_SLOT] = ["", 0]

    def updateWindow(self, win, mousePos):
        self.refreshCraftingResult()

        for cell, position in self.window.cellPositions.items():
            xx, yy = position[0][0], position[0][1]
            inv = self.inventory[cell]
            position[1] = inv

            if inv[1] == 0 or inv[0] == 0:
                continue
            self.gl.inventory_textures[inv[0]].blit(
                (self.gl.WIDTH // 2 - (win.width // 2)) + xx + 5,
                (self.gl.HEIGHT // 2 + (win.height // 2)) - yy - 27)
            if inv[1] > 1:
                lbl = self.blocksLabel[cell]
                lbl.text = str(inv[1])
                lbl.x = (self.gl.WIDTH // 2 - (win.width // 2)) + xx + 15
                lbl.y = (self.gl.HEIGHT // 2 + (win.height // 2)) - yy - 32
                lbl.draw()

        if self.draggingItem and self.draggingItem[1]:
            drg = self.draggingItem
            mp = list(mousePos)
            mp[0] -= 11
            mp[1] += 11

            self.gl.inventory_textures[drg[0]].blit(mp[0], self.gl.HEIGHT - mp[1])

            self._held_label.text = str(drg[1])
            self._held_label.x = mp[0] + 11
            self._held_label.y = self.gl.HEIGHT - mp[1] - 5
            self._held_label.draw()

    def addBlock(self, name, count=1):
        """Pick up items: top up the selected slot and matching stacks first."""
        from game.Items import max_stack_size

        if not name or count <= 0:
            return 0

        limit = max_stack_size(name)
        selected = self.inventory.get(self.activeInventory, ["", 0])
        if not is_empty(selected) and selected[0] == name and selected[1] < limit:
            moved = min(limit - selected[1], count)
            self.inventory[self.activeInventory] = [name, selected[1] + moved]
            count -= moved
            if count <= 0:
                return 0
        elif is_empty(selected):
            moved = min(limit, count)
            self.inventory[self.activeInventory] = [name, moved]
            count -= moved
            if count <= 0:
                return 0

        return self.giveItem(name, count)

    def draw(self):
        # Modal inventory/crafting windows draw their own slots. Drawing the
        # HUD hotbar as well made every item appear twice in the same area.
        if not self.gl.allowEvents.get("showCrosshair", True):
            return
        inventory = self.gl.gui.GUI_TEXTURES["inventory"]
        sel_inventory = self.gl.gui.GUI_TEXTURES["sel_inventory"]

        fullheart = self.gl.gui.GUI_TEXTURES["fullheart"]
        halfheart = self.gl.gui.GUI_TEXTURES["halfheart"]
        heartbg = self.gl.gui.GUI_TEXTURES["heartbg"]

        inventory.blit(self.gl.WIDTH // 2 - (inventory.width // 2), 0)
        sel_inventory.blit((self.gl.WIDTH // 2 - (inventory.width // 2)) +
                           (40 * self.activeInventory), 0)

        if self.gl.inventory_textures:
            for i in range(9):
                if self.inventory[i][1] == 0 or self.inventory[i][0] == 0:
                    continue
                self.gl.inventory_textures[self.inventory[i][0]].blit(
                    (self.gl.WIDTH // 2 - (inventory.width // 2)) + (40 * i) + 11, 11)
                self.blocksLabel[i].x = (self.gl.WIDTH // 2 - (inventory.width // 2)) + (40 * i) + 22
                self.blocksLabel[i].y = 6
                self.blocksLabel[i].text = str(self.inventory[i][1])
                self.blocksLabel[i].draw()

        if self.gl.player.is_spectator:
            return

        for i in range(10):
            ay = 0
            if self.gl.player.hp <= 4:
                ay = self.heartAnimation[i][0]
                if self.heartAnimation[i][1] == "-":
                    self.heartAnimation[i][0] -= self.heartAnimation[i][2]
                else:
                    self.heartAnimation[i][0] += self.heartAnimation[i][2]

                if self.heartAnimation[i][0] > 1:
                    self.heartAnimation[i][1] = "-"
                elif self.heartAnimation[i][0] < -1:
                    self.heartAnimation[i][1] = "+"

            heartbg.blit((self.gl.WIDTH // 2 - (inventory.width // 2)) + ((heartbg.width - 2) * i),
                          inventory.height + 10 + ay)

        cntr = 0
        ch = 0
        x = (self.gl.WIDTH // 2 - (inventory.width // 2)) + 2
        for i in range(math.ceil(max(0, self.gl.player.hp))):
            ay = 0
            if self.gl.player.hp <= 4:
                ay = self.heartAnimation[ch][0]

            if cntr == 0:
                hrt = halfheart
                cntr = 1
            else:
                cntr = 0
                hrt = fullheart

            hrt.blit(x, inventory.height + 12 + ay)

            if hrt == fullheart:
                x += heartbg.width - 2
                ch += 1