"""Creative-mode item palette, vanilla 1.8-style.

The window uses ``tab_items.png`` from ``gui/container/creative_inventory``:
a 9x5 scrolling palette above the player's hotbar. Clicking a palette entry
picks up a full stack (right click picks one); clicking the hotbar uses the
survival slot mechanics. The mouse wheel pages through every registered
item, exactly like vanilla's creative items tab.

Only shown in creative mode; ``Player.is_creative`` routes the E key here.
"""

import math

import pyglet
import pygame
from OpenGL.GL import *
from functions import checkHover, drawInfoLabel
from game.GUI.ModalWindow import ModalWindow


class CreativeInventory:
    COLUMNS = 9
    ROWS = 5
    PAGE_SIZE = COLUMNS * ROWS

    # Window metrics in the 2x-scaled texture space (logical 195x136 window,
    # 16px slots at 18px pitch -> 32px cells at 36px pitch when scaled).
    # The hotbar row sits at logical y=112 (probed from the vanilla atlas:
    # slot borders at top-down y = 18/36/54/72/90 grid rows, 112 hotbar).
    SLOT_SIZE = 32
    SLOT_PITCH = 36
    GRID_X = 16          # 8 logical * 2
    GRID_Y = 36          # 18 logical * 2
    HOTBAR_Y = 224       # 112 logical * 2
    PALETTE_BASE = 1000  # palette cell ids; hotbar cells reuse 0..8

    def __init__(self, gl):
        self.gl = gl
        self.window = ModalWindow(gl)
        self.window.clickEvent = self.windowClickEvent
        self.window.closeEvent = self.release_cursor
        self.window.updateFunctions.append(self.updateWindow)
        self.page = 0
        self.items = []
        self._tooltip = ""

    # ------------------------------------------------------------- layout
    def initWindow(self):
        self.window.setWindow(self.gl.gui.GUI_TEXTURES["creative_items"])
        cell = self.window.cellPositions
        cell.clear()
        for row in range(self.ROWS):
            for column in range(self.COLUMNS):
                index = row * self.COLUMNS + column
                cell[self.PALETTE_BASE + index] = [
                    (self.GRID_X + column * self.SLOT_PITCH,
                     self.GRID_Y + row * self.SLOT_PITCH,
                     self.SLOT_SIZE, self.SLOT_SIZE),
                    None,
                ]
        for slot in range(self.COLUMNS):
            cell[slot] = [
                (self.GRID_X + slot * self.SLOT_PITCH,
                 self.HOTBAR_Y, self.SLOT_SIZE, self.SLOT_SIZE),
                None,
            ]

    # -------------------------------------------------------------- state
    @property
    def visible(self):
        return self.window.visible

    def show(self):
        if not self.items:
            self.items = sorted(
                name for name in self.gl.inventory_textures
                if isinstance(name, str) and name)
        self.page = 0
        self.window.show()

    def cycle_page(self, direction):
        """Mouse wheel: page through the palette like vanilla scrolling."""
        pages = max(1, math.ceil(len(self.items) / self.PAGE_SIZE))
        self.page = (self.page + direction) % pages

    def page_items(self):
        start = self.page * self.PAGE_SIZE
        return self.items[start:start + self.PAGE_SIZE]

    # ------------------------------------------------------------- clicks
    def windowClickEvent(self, button, cell):
        inventory = self.gl.player.inventory
        if cell >= self.PALETTE_BASE:
            index = cell - self.PALETTE_BASE
            items = self.page_items()
            if index >= len(items):
                return
            name = items[index]
            from game.Items import max_stack_size
            limit = max_stack_size(name)
            if button[2]:  # right click picks one, like vanilla
                if inventory.draggingItem and inventory.draggingItem[0] == name:
                    inventory.draggingItem[1] = min(
                        limit, inventory.draggingItem[1] + 1)
                else:
                    inventory.draggingItem = [name, 1]
                return
            if button[0]:  # left click takes a full stack
                if (inventory.draggingItem
                        and inventory.draggingItem[0] == name):
                    inventory.draggingItem[1] = limit
                else:
                    inventory.draggingItem = [name, limit]
            return
        inventory.windowClickEvent(button, cell)

    def release_cursor(self):
        """Return the dragged stack to the inventory when the window closes."""
        inventory = self.gl.player.inventory
        dragging = getattr(inventory, "draggingItem", [])
        if dragging and dragging[1] > 0:
            inventory.giveItem(dragging[0], dragging[1])
        inventory.draggingItem = []

    # -------------------------------------------------------------- draw
    def updateWindow(self, win, mouse):
        inventory = self.gl.player.inventory
        left = self.gl.WIDTH // 2 - (win.width // 2)
        window_top = self.gl.HEIGHT // 2 - (win.height // 2)
        # pyglet draws bottom-up; the inventory blit formula wants the
        # window's top edge in pyglet coordinates
        top_pyglet = self.gl.HEIGHT // 2 + (win.height // 2)

        self._tooltip = ""
        items = self.page_items()
        for index, name in enumerate(items):
            cell = self.window.cellPositions[self.PALETTE_BASE + index]
            x, y = cell[0][0], cell[0][1]
            self.gl.inventory_textures[name].blit(
                left + x + 5, top_pyglet - y - 27)
            if checkHover(left + x, window_top + y,
                          self.SLOT_SIZE, self.SLOT_SIZE,
                          mouse[0], mouse[1]):
                self._tooltip = name

        for slot in range(self.COLUMNS):
            stack = inventory.inventory.get(slot, ["", 0])
            cell = self.window.cellPositions[slot]
            x, y = cell[0][0], cell[0][1]
            if stack[1] > 0 and stack[0]:
                self.gl.inventory_textures[stack[0]].blit(
                    left + x + 5, top_pyglet - y - 27)
            # mark the selected hotbar slot
            if slot == inventory.activeInventory:
                drawInfoLabel(self.gl, ">", xx=left + x - 6,
                              yy=top_pyglet - y - 24,
                              style=[("", "")], size=12)

        dragging = getattr(inventory, "draggingItem", [])
        if dragging and dragging[1]:
            mp = list(mouse)
            mp[0] -= 11
            mp[1] += 11
            self.gl.inventory_textures[dragging[0]].blit(
                mp[0], self.gl.HEIGHT - mp[1])
            drawInfoLabel(self.gl, str(dragging[1]), xx=mp[0] + 11,
                          yy=self.gl.HEIGHT - mp[1] - 5, style=[("", "")],
                          size=10)

        if self._tooltip:
            pages = max(1, math.ceil(len(self.items) / self.PAGE_SIZE))
            drawInfoLabel(
                self.gl,
                f"{self._tooltip}  ({self.page + 1}/{pages})",
                xx=mouse[0] + 12, yy=self.gl.HEIGHT - mouse[1] - 4,
                style=[("", "")], size=12, label_color=(255, 255, 255))
