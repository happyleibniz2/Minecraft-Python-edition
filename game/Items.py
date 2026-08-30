"""Minecraft 1.20.1 item definitions: tools, materials and stack sizes.

Central registry so the inventory, mining and placement code all agree on what
an item is. Anything not listed here is treated as a placeable block.
"""

# ---------------------------------------------------------------- tool tiers
# tier -> (mining speed multiplier, durability, mining level)
TOOL_TIERS = {
    "wooden": (2.0, 59, 1),
    "stone": (4.0, 131, 2),
    "iron": (6.0, 250, 3),
    "golden": (12.0, 32, 1),
    "diamond": (8.0, 1561, 4),
    "netherite": (9.0, 2031, 5),
}

TOOL_KINDS = ("pickaxe", "axe", "shovel", "hoe", "sword")

# Java Edition 1.20.1 attack attributes. Damage includes the player's base
# attack damage, matching the number shown in the item tooltip.
SWORD_DAMAGE = {
    "wooden": 4.0,
    "stone": 5.0,
    "iron": 6.0,
    "golden": 4.0,
    "diamond": 7.0,
    "netherite": 8.0,
}
SWORD_ATTACK_SPEED = 1.6

# which tool each block category needs, and the level required to drop it
PICKAXE_BLOCKS = {
    "stone": 1, "cobblestone": 1, "sandstone": 1, "brick": 1,
    "coal_ore": 1, "glowstone": 1, "nocolor": 1,
    "iron_ore": 2, "lapis_ore": 2, "iron_block": 2,
    "gold_ore": 3, "diamond_ore": 3, "emerald_ore": 3, "redstone_ore": 3,
    "ancient_debris": 4,
}
AXE_BLOCKS = ("log_oak", "log_birch", "log_acacia", "planks_oak",
              "crafting_table", "bone_block")
SHOVEL_BLOCKS = ("dirt", "grass", "sand", "gravel", "clay")
SHEARS_BLOCKS = ("leaves_oak", "leaves_taiga", "tall_grass")

# items that are never placeable as blocks
NON_BLOCK_ITEMS = {"water_bucket", "bucket"}

# internal texture layers that must never appear as usable items
INTERNAL_TEXTURES = {"spawn_egg", "spawn_egg_overlay"}


def tool_name(tier, kind):
    return f"{tier}_{kind}"


def all_tools():
    for tier in TOOL_TIERS:
        for kind in TOOL_KINDS:
            yield tool_name(tier, kind)


def parse_tool(name):
    """Return ``(tier, kind)`` for a tool name, or ``None``."""
    if not name:
        return None
    for kind in TOOL_KINDS:
        suffix = "_" + kind
        if name.endswith(suffix):
            tier = name[:-len(suffix)]
            if tier in TOOL_TIERS:
                return tier, kind
    return None


def is_tool(name):
    return parse_tool(name) is not None


def is_spawn_egg(name):
    return bool(name) and name.endswith("_spawn_egg")


def is_item(name):
    """True when the name is an item rather than a placeable block."""
    if not name:
        return False
    return (is_tool(name) or is_spawn_egg(name)
            or name in NON_BLOCK_ITEMS or name in INTERNAL_TEXTURES)


def max_stack_size(name):
    """Tools are unstackable in Minecraft; everything else stacks to 64."""
    return 1 if is_tool(name) else 64


def max_durability(name):
    parsed = parse_tool(name)
    if parsed is None:
        return 0
    return TOOL_TIERS[parsed[0]][1]


def tool_level(name):
    parsed = parse_tool(name)
    if parsed is None:
        return 0
    return TOOL_TIERS[parsed[0]][2]


def required_tool(block_name):
    """Return the tool kind a block needs, or ``None`` if hands suffice."""
    if block_name in PICKAXE_BLOCKS:
        return "pickaxe"
    if block_name in AXE_BLOCKS:
        return "axe"
    if block_name in SHOVEL_BLOCKS:
        return "shovel"
    return None


def required_level(block_name):
    """Mining level needed to actually drop the block."""
    return PICKAXE_BLOCKS.get(block_name, 0)


def needs_tool_to_drop(block_name):
    """Only pickaxe blocks require the correct tool to yield a drop."""
    return block_name in PICKAXE_BLOCKS


def mining_speed(tool, block_name):
    """Speed multiplier the tool applies to a block, like Minecraft.

    Tools only speed up the blocks they are meant for; using an axe on stone
    gives no bonus. Swords are a special case for leaves.
    """
    parsed = parse_tool(tool)
    if parsed is None:
        return 1.0

    tier, kind = parsed
    speed = TOOL_TIERS[tier][0]

    if kind == "pickaxe" and block_name in PICKAXE_BLOCKS:
        return speed
    if kind == "axe" and block_name in AXE_BLOCKS:
        return speed
    if kind == "shovel" and block_name in SHOVEL_BLOCKS:
        return speed
    if kind == "sword":
        # swords break leaves faster and cobwebs fastest
        if block_name in ("leaves_oak", "leaves_taiga"):
            return 15.0
        return 1.5
    return 1.0


def can_harvest(tool, block_name):
    """Whether mining with ``tool`` yields a drop, as in Minecraft."""
    if not needs_tool_to_drop(block_name):
        return True
    parsed = parse_tool(tool)
    if parsed is None:
        return False
    _, kind = parsed
    if kind != "pickaxe":
        return False
    return tool_level(tool) >= required_level(block_name)


def attack_damage(item_name):
    parsed = parse_tool(item_name)
    if parsed is None:
        return 1.0
    tier, kind = parsed
    if kind == "sword":
        return SWORD_DAMAGE[tier]
    return 1.0


def attack_speed(item_name):
    parsed = parse_tool(item_name)
    if parsed is not None and parsed[1] == "sword":
        return SWORD_ATTACK_SPEED
    return 4.0
