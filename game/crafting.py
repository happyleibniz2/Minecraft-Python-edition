def getCraftingItem(objects, tableType=False, numbers=None):
    if numbers is None:
        numbers = [1, 1, 1, 1]

    if not isinstance(objects, (list, tuple)) or len(objects) != 4:
        return ["", 0]

    if tableType:
        return ["", 0]

    slots = [str(slot) for slot in objects]
    counts = [int(n) if str(n).isdigit() else 1 for n in numbers[:4]]

    if objects == ["log_oak", "", "", ""]:
        return ["planks_oak", counts[0] or 1]
    if objects == ["planks_oak", "planks_oak", "planks_oak", "planks_oak"]:
        return ["crafting_table", counts[0] or 1]

    return ["", 0]
