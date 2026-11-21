"""Repository regression tests."""

# Tests import game modules that touch pyglet.gl; never let pyglet 2.x create
# its hidden shadow window during collection.
import pyglet
pyglet.options['shadow_window'] = False
