"""Small lifecycle helpers for Pyglet 1.5 graphics resources."""

import pyglet


class DisposableBatch(pyglet.graphics.Batch):
    """A Batch that can explicitly release its vertex-domain reference cycles."""

    def __init__(self):
        super().__init__()
        self.vertex_lists = []

    def add(self, *args, **kwargs):
        vertex_list = super().add(*args, **kwargs)
        self.vertex_lists.append(vertex_list)
        return vertex_list

    def dispose(self):
        domains = {
            domain
            for domain_map in self.group_map.values()
            for domain in domain_map.values()
        }
        for vertex_list in self.vertex_lists:
            try:
                vertex_list.delete()
            except Exception:
                pass
        self.vertex_lists.clear()

        # Pyglet 1.5's domain buffers and attributes reference each other.
        # Break that cycle now instead of waiting for an unpredictable GC frame.
        for domain in domains:
            try:
                domain.__del__()
            except Exception:
                pass
        try:
            self.invalidate()
            self._update_draw_list()
        except Exception:
            pass
