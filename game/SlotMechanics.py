"""Minecraft-accurate container slot mechanics.

Slots are stored as ``[name, count]`` pairs. An empty slot is ``["", 0]``.
The held (cursor) stack uses the same representation, or ``[]`` when empty.
"""

MAX_STACK = 64


def is_empty(stack):
    return not stack or not stack[0] or stack[1] <= 0


def normalize(stack):
    if is_empty(stack):
        return ["", 0]
    return [stack[0], stack[1]]


def same_item(a, b):
    return not is_empty(a) and not is_empty(b) and a[0] == b[0]


def max_stack_size(name):
    """Per-item stack limit; tools are unstackable like in Minecraft."""
    from game.Items import max_stack_size as item_stack_size

    return item_stack_size(name)


def left_click(slot, held, take_only=False, place_only=False):
    """Resolve a left click. Returns ``(slot, held)``.

    Minecraft rules:
      * empty hand on a filled slot picks up the whole stack
      * matching items merge up to the stack limit, keeping the remainder held
      * differing items swap
      * clicking an empty slot places the whole held stack
    """
    slot = normalize(slot)
    held = normalize(held) if held else ["", 0]

    if is_empty(held):
        if is_empty(slot):
            return ["", 0], []
        return ["", 0], [slot[0], slot[1]]

    if take_only:
        return slot, held if not is_empty(held) else []

    if is_empty(slot):
        return [held[0], held[1]], []

    if same_item(slot, held):
        limit = max_stack_size(slot[0])
        space = limit - slot[1]
        if space <= 0:
            if place_only:
                return slot, held
            return [held[0], held[1]], [slot[0], slot[1]]
        moved = min(space, held[1])
        slot = [slot[0], slot[1] + moved]
        remaining = held[1] - moved
        return slot, ([held[0], remaining] if remaining > 0 else [])

    if place_only:
        return slot, held

    return [held[0], held[1]], [slot[0], slot[1]]


def right_click(slot, held):
    """Resolve a right click. Returns ``(slot, held)``.

    Minecraft rules:
      * empty hand takes half of the slot, rounded up
      * holding a stack places one item onto an empty or matching slot
    """
    slot = normalize(slot)
    held = normalize(held) if held else ["", 0]

    if is_empty(held):
        if is_empty(slot):
            return ["", 0], []
        taken = (slot[1] + 1) // 2
        remaining = slot[1] - taken
        return ([slot[0], remaining] if remaining > 0 else ["", 0]), [slot[0], taken]

    if is_empty(slot):
        remaining = held[1] - 1
        return [held[0], 1], ([held[0], remaining] if remaining > 0 else [])

    if same_item(slot, held) and slot[1] < max_stack_size(slot[0]):
        remaining = held[1] - 1
        return [slot[0], slot[1] + 1], ([held[0], remaining] if remaining > 0 else [])

    return slot, held


def insert_stack(slots, order, name, count=1, limit=None):
    """Insert items following Minecraft's merge-then-fill priority.

    Existing matching stacks are topped up first, then the first empty slot is
    used. Returns the number of items that could not be inserted.
    """
    if not name or count <= 0:
        return 0

    stack_limit = limit or max_stack_size(name)

    for index in order:
        slot = slots.get(index)
        if slot is None or is_empty(slot):
            continue
        if slot[0] != name or slot[1] >= stack_limit:
            continue
        moved = min(stack_limit - slot[1], count)
        slots[index] = [name, slot[1] + moved]
        count -= moved
        if count <= 0:
            return 0

    for index in order:
        slot = slots.get(index)
        if slot is not None and not is_empty(slot):
            continue
        moved = min(stack_limit, count)
        slots[index] = [name, moved]
        count -= moved
        if count <= 0:
            return 0

    return count
