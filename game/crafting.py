"""Minecraft-style recipe matching.

A recipe result is independent of how large the ingredient stacks are: putting
64 logs into the grid still yields one craft (4 planks), exactly like Minecraft.
"""

# Shapeless recipes: (sorted ingredient tuple) -> (result name, result count)
SHAPELESS_RECIPES = {
    ("log_oak",): ("planks_oak", 4),
    ("log_birch",): ("planks_oak", 4),
    ("log_acacia",): ("planks_oak", 4),
    ("planks_oak",) * 4: ("crafting_table", 1),
}


def _ingredient_key(objects, numbers):
    ingredients = []
    for index, name in enumerate(objects):
        count = 0
        if index < len(numbers):
            try:
                count = int(numbers[index])
            except (TypeError, ValueError):
                count = 0
        if name and count > 0:
            ingredients.append(str(name))
    return tuple(sorted(ingredients))


def getCraftingItem(objects, tableType=False, numbers=None):
    """Return ``[name, count]`` for the recipe formed by ``objects``.

    ``objects`` is a flat list of slot contents and ``numbers`` the matching
    stack sizes. Matching is shapeless, so ingredient placement inside the grid
    does not matter.
    """
    if not isinstance(objects, (list, tuple)):
        return ["", 0]

    if numbers is None:
        numbers = [1] * len(objects)

    key = _ingredient_key(objects, numbers)
    if not key:
        return ["", 0]

    recipe = SHAPELESS_RECIPES.get(key)
    if recipe is None:
        return ["", 0]

    name, count = recipe
    return [name, count]
