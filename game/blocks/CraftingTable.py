from game.GUI.ModalWindow import ModalWindow
from game.crafting import getCraftingItem
from settings import *
import pyglet


class CraftingTable:
    def __init__(self, plClass, blClass, glClass):
        self.draggingItem = []
        self.inventory = {} if not hasattr(plClass.inventory, "get_inventory_blocks") else plClass.inventory.get_inventory_blocks().copy()
        self.blocksLabel = {}
        self.pc = plClass
        self.bc = blClass
        self.gl = self.pc.gl

        self.window = ModalWindow(self.gl)
        self.window.setWindow(self.gl.gui.GUI_TEXTURES["crafting_table"])
        self.window.clickEvent = self.windowClickEvent
        self.window.updateFunctions.append(self.update)

        self.window.cellPositions = {
            0: [(20, 34), None],
            1: [(96, 34), None],
            2: [(132, 34), None],
            3: [(60, 70), None],
            4: [(96, 70), None],
            5: [(132, 70), None],
            6: [(60, 106), None],
            7: [(96, 106), None],
            8: [(132, 106), None],
            9: [(240, 62, 48, 48), None],
        }

        x = 16
        for i in range(9):
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
        self.window.cellPositions[41] = [(308, 56), None]

        x, y = 16, 168
        for i in range(9 * 3, 0, -1):
            self.window.cellPositions[9 + i] = [(x, y), None]
            x += 36
            if x > 304:
                x = 16
                y += 36

        for slot in range(42):
            self.inventory.setdefault(slot, ["", 0])
            self.blocksLabel[slot] = pyglet.text.Label(
                "0",
                font_name='Minecraft Rus',
                color=(255, 255, 255, 255),
                font_size=10,
                x=self.gl.WIDTH // 2,
                y=60,
            )

        self.window.show()

    def consumeIngredients(self):
        for slot in range(4):
            if self.inventory.get(slot, ["", 0])[1] > 0:
                self.inventory[slot][1] -= 1
                if self.inventory[slot][1] <= 0:
                    self.inventory[slot] = ["", 0]
        self.inventory[9] = ["", 0]

    def windowClickEvent(self, button, cell):
        if button[0]:
            if cell == 9 and self.inventory.get(9, ["", 0])[0]:
                if not self.draggingItem:
                    self.draggingItem = [self.inventory[9][0], self.inventory[9][1]]
                    self.consumeIngredients()
                return

            if self.draggingItem:
                if cell in self.inventory and self.inventory[cell][1] == 0:
                    self.inventory[cell] = self.draggingItem
                    self.draggingItem = []
                elif cell in self.inventory:
                    safe = [self.inventory[cell][0], self.inventory[cell][1]]
                    self.inventory[cell] = self.draggingItem
                    self.draggingItem = safe
            elif cell in self.inventory and self.inventory[cell][1] != 0:
                self.draggingItem = [self.inventory[cell][0], self.inventory[cell][1]]
                self.inventory[cell] = [self.inventory[cell][0], 0]

        if button[2] and self.draggingItem and cell in self.inventory:
            if self.inventory[cell][0] == self.draggingItem[0] and self.draggingItem[1]:
                self.inventory[cell][1] += 1
                self.draggingItem[1] -= 1
            elif self.inventory[cell][1] == 0 and self.draggingItem[1]:
                self.inventory[cell][0] = self.draggingItem[0]
                self.inventory[cell][1] += 1
                self.draggingItem[1] -= 1

    def update(self, win, mousePos):
        if not hasattr(self.gl, 'player') or not hasattr(self.gl.player, 'inventory'):
            return

        inventory = self.gl.player.inventory.inventory
        for slot in range(42):
            self.inventory.setdefault(slot, ["", 0])
            if slot < 37:
                self.inventory[slot] = inventory.get(slot, ["", 0])

        recipe_slots = [
            self.inventory.get(0, ["", 0])[0] if self.inventory.get(0, ["", 0])[1] else "",
            self.inventory.get(1, ["", 0])[0] if self.inventory.get(1, ["", 0])[1] else "",
            self.inventory.get(3, ["", 0])[0] if self.inventory.get(3, ["", 0])[1] else "",
            self.inventory.get(4, ["", 0])[0] if self.inventory.get(4, ["", 0])[1] else "",
        ]
        recipe_counts = [
            self.inventory.get(0, ["", 0])[1] if self.inventory.get(0, ["", 0])[1] else 0,
            self.inventory.get(1, ["", 0])[1] if self.inventory.get(1, ["", 0])[1] else 0,
            self.inventory.get(3, ["", 0])[1] if self.inventory.get(3, ["", 0])[1] else 0,
            self.inventory.get(4, ["", 0])[1] if self.inventory.get(4, ["", 0])[1] else 0,
        ]
        result = getCraftingItem(recipe_slots, numbers=recipe_counts)
        self.inventory[9] = result if result and result[0] else ["", 0]

        for slot, position in self.window.cellPositions.items():
            if slot not in self.inventory:
                continue
            inv = self.inventory[slot]
            position[1] = inv
            if inv[1] == 0 or not inv[0]:
                continue
            if inv[0] in self.gl.inventory_textures:
                xx, yy = position[0][0], position[0][1]
                self.gl.inventory_textures[inv[0]].blit(
                    (self.gl.WIDTH // 2 - (win.width // 2)) + xx + 5,
                    (self.gl.HEIGHT // 2 + (win.height // 2)) - yy - 27,
                )

        if self.draggingItem and self.draggingItem[1]:
            mp = list(mousePos)
            mp[0] -= 11
            mp[1] += 11
            self.gl.inventory_textures[self.draggingItem[0]].blit(mp[0], self.gl.HEIGHT - mp[1])
