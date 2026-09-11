"""Small lifecycle helpers for Pyglet 1.5 graphics resources."""

import pyglet


class DisposableBatch(pyglet.graphics.Batch):
    """A Batch with a cheap per-frame reset and an explicit disposal.

    ``reset`` frees only the vertex lists added since the last call and clears
    the per-batch group map, keeping Pyglet's shared GPU vertex domains alive.
    ``dispose`` performs a full teardown and should only be used when the
    batch itself is being discarded (scene reset, chunk rebuild that swaps in
    a new batch).
    """

    def __init__(self):
        super().__init__()
        self.vertex_lists = []

    def add(self, *args, **kwargs):
        vertex_list = super().add(*args, **kwargs)
        self.vertex_lists.append(vertex_list)
        return vertex_list

    def reset(self):
        """Delete this frame's vertex lists, keep the batch reusable."""
        lists, self.vertex_lists = self.vertex_lists, []
        for vertex_list in lists:
            try:
                vertex_list.delete()
            except Exception:
                pass
        # Pyglet's group_map still references the deleted vertex lists, which
        # would make the next draw call touch freed GL buffers.
        self.group_map.clear()

    def dispose(self):
        """Full teardown. Only call when the batch is being thrown away."""
        self.reset()