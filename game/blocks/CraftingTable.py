from game.GUI.ModalWindow import ModalWindow
from game.crafting import getCraftingItem
from game.SlotMechanics import MAX_STACK, is_empty, left_click, right_click
from settings import *
import pyglet


class CraftingTable:
    """A 3x3 crafting table sharing the player's real inventory."""

    GRID_SLOTS = range(0, 9)
    RESULT_SLOT = 9
    HOTBAR_OFFSET = 100      # grid ids must not collide with inventory ids

    def __init__(self, plClass, blClass, glClass):
        self.pc = plClass
        self.bc = blClass
        self.gl = self.pc.gl
        self.playerInventory = plClass.inventory
        self.grid = {slot: ["", 0] for slot in self.GRID_SLOTS}
        self.grid[self.RESULT_SLOT] = ["", 0]
        self.blocksLabel = {}

        self.window = ModalWindow(self.gl)
        self.window.setWindow(self.gl.gui.GUI_TEXTURES["crafting_table"])
        self.window.clickEvent = self.windowClickEvent
        self.window.closeEvent = self.returnGridItems
        self.window.updateFunctions.append(self.update)

        # 3x3 crafting grid
        self.window.cellPositions = {
            0: [(60, 34), None],
            1: [(96, 34), None],
            2: [(132, 34), None],
            3: [(60, 70), None],
            4: [(96, 70), None],
            5: [(132, 70), None],
            6: [(60, 106), None],
            7: [(96, 106), None],
            8: [(132, 106), None],
            self.RESULT_SLOT: [(240, 62, 48, 48), None],
        }

        # player hotbar, offset so ids never overwrite the grid
        x = 16
        for slot in self.playerInventory.HOTBAR_SLOTS:
            self.window.cellPositions[self.HOTBAR_OFFSET + slot] = [(x, 284), None]
            x += 36

        # player storage rows
        x, y = 16, 168
        for slot in self.playerInventory.STORAGE_SLOTS:
            self.window.cellPositions[self.HOTBAR_OFFSET + slot] = [(x, y), None]
            x += 36
            if x > 304:
                x = 16
                y += 36

        for slot in self.window.cellPositions:
            self.blocksLabel[slot] = pyglet.text.Label(
                "0",
                font_name='Minecraft Rus',
                color=(255, 255, 255, 255),
                font_size=10,
                x=self.gl.WIDTH // 2,
                y=60,
            )

        self.window.show()

    @property
    def draggingItem(self):
        return self.playerInventory.draggingItem

    @draggingItem.setter
    def draggingItem(self, value):
        self.playerInventory.draggingItem = value

    def _resolve(self, cell):
        """Map a cell id to its backing store and slot index."""
        if cell >= self.HOTBAR_OFFSET:
            return self.playerInventory.inventory, cell - self.HOTBAR_OFFSET
        return self.grid, cell

    def consumeIngredients(self):
        for slot in self.GRID_SLOTS:
            stack = self.grid.get(slot, ["", 0])
            if stack[1] > 0:
                remaining = stack[1] - 1
                self.grid[slot] = [stack[0], remaining] if remaining > 0 else ["", 0]
        self.grid[self.RESULT_SLOT] = ["", 0]

    def returnGridItems(self):
        """Give grid and held items back when the window closes."""
        for slot in self.GRID_SLOTS:
            stack = self.grid.get(slot, ["", 0])
            if not is_empty(stack):
                self.playerInventory.giveItem(stack[0], stack[1])
            self.grid[slot] = ["", 0]
        self.grid[self.RESULT_SLOT] = ["", 0]

        held = self.draggingItem
        if not is_empty(held):
            self.playerInventory.giveItem(held[0], held[1])
        self.draggingItem = []

    def takeResult(self):
        result = self.grid.get(self.RESULT_SLOT, ["", 0])
        if is_empty(result):
            return

        held = self.draggingItem
        if is_empty(held):
            self.draggingItem = [result[0], result[1]]
            self.consumeIngredients()
            return

        if held[0] != result[0] or held[1] + result[1] > MAX_STACK:
            return

        self.draggingItem = [held[0], held[1] + result[1]]
        self.consumeIngredients()

    def windowClickEvent(self, button, cell):
        if cell not in self.window.cellPositions:
            return

        if cell == self.RESULT_SLOT:
            self.takeResult()
            return

        store, index = self._resolve(cell)
        if index not in store:
            return

        if button[0]:
            slot, held = left_click(store[index], self.draggingItem)
            store[index] = slot
            self.draggingItem = held
        elif button[2]:
            slot, held = right_click(store[index], self.draggingItem)
            store[index] = slot
            self.draggingItem = held

    def refreshResult(self):
        names = [self.grid[slot][0] if self.grid[slot][1] else "" for slot in self.GRID_SLOTS]
        counts = [self.grid[slot][1] for slot in self.GRID_SLOTS]
        result = getCraftingItem(names, tableType=False, numbers=counts)
        self.grid[self.RESULT_SLOT] = result if result and result[0] else ["", 0]

    def update(self, win, mousePos):
        if not hasattr(self.gl, 'player') or not hasattr(self.gl.player, 'inventory'):
            return

        self.refreshResult()

        for slot, position in self.window.cellPositions.items():
            if slot == self.RESULT_SLOT:
                inv = self.grid[self.RESULT_SLOT]
            else:
                store, index = self._resolve(slot)
                if index not in store:
                    continue
                inv = store[index]

            position[1] = inv
            if is_empty(inv):
                continue
            if inv[0] not in self.gl.inventory_textures:
                continue

            xx, yy = position[0][0], position[0][1]
            self.gl.inventory_textures[inv[0]].blit(
                (self.gl.WIDTH // 2 - (win.width // 2)) + xx + 5,
                (self.gl.HEIGHT // 2 + (win.height // 2)) - yy - 27,
            )
            if inv[1] > 1:
                pyglet.text.Label(
                    str(inv[1]),
                    font_name='Minecraft Rus',
                    color=(255, 255, 255, 255),
                    font_size=10,
                    x=(self.gl.WIDTH // 2 - (win.width // 2)) + xx + 15,
                    y=(self.gl.HEIGHT // 2 + (win.height // 2)) - yy - 32,
                ).draw()

        held = self.draggingItem
        if not is_empty(held) and held[0] in self.gl.inventory_textures:
            mp = list(mousePos)
            mp[0] -= 11
            mp[1] += 11
            self.gl.inventory_textures[held[0]].blit(mp[0], self.gl.HEIGHT - mp[1])
            pyglet.text.Label(
                str(held[1]),
                font_name='Minecraft Rus',
                color=(255, 255, 255, 255),
                font_size=10,
                x=mp[0] + 11,
                y=self.gl.HEIGHT - mp[1] - 5,
            ).draw()
