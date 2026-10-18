import unittest
from types import SimpleNamespace

from game.entity.CreativeInventory import CreativeInventory


def make_creative(items=("stone", "torch", "wooden_pickaxe")):
    inventory = SimpleNamespace(
        inventory={0: ["", 0]}, activeInventory=0, draggingItem=[],
        windowClickEvent=lambda button, cell: None,
        giveItem=lambda name, count: None,
    )
    gl = SimpleNamespace(
        player=SimpleNamespace(inventory=inventory),
        inventory_textures={name: None for name in items},
        WIDTH=854, HEIGHT=480,
    )
    window = CreativeInventory(gl)
    window.items = list(items)
    return window


LEFT = (1, 0, 0)
RIGHT = (0, 0, 1)


class CreativeInventoryTests(unittest.TestCase):
    def test_left_click_takes_a_full_stack(self):
        window = make_creative()
        window.windowClickEvent(LEFT, CreativeInventory.PALETTE_BASE + 0)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["stone", 64])

    def test_left_click_tops_up_the_same_item(self):
        window = make_creative()
        window.gl.player.inventory.draggingItem = ["torch", 5]
        window.windowClickEvent(LEFT, CreativeInventory.PALETTE_BASE + 1)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["torch", 64])

    def test_left_click_replaces_a_different_stack(self):
        window = make_creative()
        window.gl.player.inventory.draggingItem = ["stone", 12]
        window.windowClickEvent(LEFT, CreativeInventory.PALETTE_BASE + 1)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["torch", 64])

    def test_right_click_picks_one(self):
        window = make_creative()
        window.windowClickEvent(RIGHT, CreativeInventory.PALETTE_BASE + 2)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["wooden_pickaxe", 1])
        # tools do not stack: a second right click stays at one
        window.windowClickEvent(RIGHT, CreativeInventory.PALETTE_BASE + 2)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["wooden_pickaxe", 1])
        # stackable items accumulate one by one
        window.windowClickEvent(RIGHT, CreativeInventory.PALETTE_BASE + 0)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["stone", 1])
        window.windowClickEvent(RIGHT, CreativeInventory.PALETTE_BASE + 0)
        self.assertEqual(window.gl.player.inventory.draggingItem,
                         ["stone", 2])

    def test_hotbar_cells_delegate_to_the_survival_inventory(self):
        window = make_creative()
        calls = []
        window.gl.player.inventory.windowClickEvent = (
            lambda button, cell: calls.append((tuple(button), cell)))
        window.windowClickEvent(LEFT, 3)
        self.assertEqual(calls, [((1, 0, 0), 3)])

    def test_pages_wrap_around(self):
        window = make_creative([f"item{i}" for i in range(100)])
        self.assertEqual(len(window.page_items()), CreativeInventory.PAGE_SIZE)
        self.assertEqual(window.page, 0)
        window.cycle_page(1)
        self.assertEqual(window.page, 1)
        window.cycle_page(1)
        self.assertEqual(window.page, 2)
        window.cycle_page(1)  # wraps to 0 (ceil(100/45) = 3 pages)
        self.assertEqual(window.page, 0)
        window.cycle_page(-1)  # wraps backwards
        self.assertEqual(window.page, 2)

    def test_release_cursor_returns_the_dragged_stack(self):
        window = make_creative()
        inventory = window.gl.player.inventory
        inventory.draggingItem = ["stone", 7]
        given = []
        inventory.giveItem = lambda name, count: given.append((name, count))
        window.release_cursor()
        self.assertEqual(given, [("stone", 7)])
        self.assertEqual(inventory.draggingItem, [])

    def test_window_metrics_match_the_vanilla_atlas_layout(self):
        """Probed from tab_items.png: slot borders at logical y=18/36/54/72/90
        (five grid rows) and the hotbar row at logical y=112."""
        self.assertEqual(CreativeInventory.GRID_X, 16)     # 8 logical * 2
        self.assertEqual(CreativeInventory.GRID_Y, 36)     # 18 logical * 2
        self.assertEqual(CreativeInventory.SLOT_PITCH, 36)
        self.assertEqual(CreativeInventory.SLOT_SIZE, 32)
        self.assertEqual(CreativeInventory.HOTBAR_Y, 224)  # 112 logical * 2


if __name__ == "__main__":
    unittest.main()
