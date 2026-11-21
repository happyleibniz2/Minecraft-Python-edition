"""Fixed-function compatibility helpers for the pyglet 2.x host.

The renderer deliberately uses the OpenGL compatibility profile: world
geometry is transformed by the fixed-function matrix stack and the lighting
shader is GLSL 1.20.  pyglet 2.x's ``Batch``/``vertex_list``/``Texture.blit``
and text layout draw through shaders that use the window's projection/view
uniforms, so they cannot participate in that pipeline unchanged.

This module provides:

* ``FixedFunctionVertexList`` - the client-array replacement for pyglet 1.5's
  ``vertex_list``.
* ``DisposableBatch`` - the matching replacement for ``Batch.add``.
* a small compatibility shim that routes pyglet 2.x texture blits and text
  layout draws through the current fixed-function matrices.  UI and label
  drawing keep the same coordinates, rotation and scale as the pyglet 1.5
  renderer.
"""

from array import array as _array
from ctypes import c_float

# Must run before pyglet.gl/pyglet.image/pyglet.text import.  pyglet 2.x
# otherwise creates a hidden 1x1 shadow window and GL context at import time,
# and the game must own exactly one window/context.
import pyglet
pyglet.options['shadow_window'] = False

import pyglet.image
import pyglet.text.layout
from pyglet import app as pyglet_app
from pyglet.math import Mat4

from OpenGL.GL import (
    GL_CLIENT_VERTEX_ARRAY_BIT,
    GL_COLOR_ARRAY,
    GL_ENABLE_BIT,
    GL_FALSE,
    GL_FLOAT,
    GL_MODELVIEW_MATRIX,
    GL_PROJECTION_MATRIX,
    GL_QUADS,
    GL_TEXTURE0,
    GL_TEXTURE_COORD_ARRAY,
    GL_VERTEX_ARRAY,
    glActiveTexture,
    glBegin,
    glBindTexture,
    glColorPointer,
    glDisableClientState,
    glDisableVertexAttribArray,
    glDrawArrays,
    glEnable,
    glEnableClientState,
    glEnableVertexAttribArray,
    glEnd,
    glGetFloatv,
    glPopAttrib,
    glPopClientAttrib,
    glPushAttrib,
    glPushClientAttrib,
    glTexCoord3f,
    glTexCoordPointer,
    glVertex3f,
    glVertexAttribPointer,
    glVertexPointer,
)


def _float_array(values, expected):
    """Copy a flat sequence into a ctypes float array of known length."""
    data = _array("f", values)
    if len(data) != expected:
        raise ValueError(
            f"vertex data has {len(data)} floats, expected {expected}"
        )
    return (c_float * expected).from_buffer_copy(data.tobytes())


def _parse_format(fmt):
    """Split a pyglet 1.x format string into a semantic attribute.

    ``v3f`` -> position, 3 components
    ``c4f`` -> color, 4 components
    ``t2f`` -> texture coordinate, 2 components
    ``3g1f`` -> generic attribute location 3, 1 component

    The ``/static`` and ``/dynamic`` usage suffixes are accepted and ignored;
    client arrays are updated in place when a ``colors`` assignment is made.
    """
    base = fmt.split("/", 1)[0]
    if "g" in base:
        location, rest = base.split("g", 1)
        if not location.isdigit() or not rest.endswith("f") or not rest[:-1].isdigit():
            raise ValueError(f"unsupported vertex format: {fmt!r}")
        return "generic", int(location), int(rest[:-1])
    if (len(base) < 3 or base[0] not in "vct"
            or base[-1] != "f" or not base[1:-1].isdigit()):
        raise ValueError(f"unsupported vertex format: {fmt!r}")
    return {"v": "position", "c": "color", "t": "texcoord"}[base[0]], int(base[1:-1])


class FixedFunctionVertexList:
    """A small replacement for ``pyglet.graphics.vertex_list``.

    The constructor mirrors the pyglet 1.x call shape:
    ``FixedFunctionVertexList(count, ('v3f', data), ('c3f', data), ...)``.
    ``draw(mode)`` enables only the arrays this list owns, draws, and restores
    the previous client-array state.
    """

    def __init__(self, count, *attributes):
        self.count = int(count)
        self._position = None
        self._position_size = 0
        self._color = None
        self._color_size = 0
        self._texcoord = None
        self._texcoord_size = 0
        self._generic = []

        for fmt, values in attributes:
            parsed = _parse_format(fmt)
            kind = parsed[0]
            if kind == "position":
                self._position_size = parsed[1]
                self._position = _float_array(values, self.count * self._position_size)
            elif kind == "color":
                self._color_size = parsed[1]
                self._color = _float_array(values, self.count * self._color_size)
            elif kind == "texcoord":
                self._texcoord_size = parsed[1]
                self._texcoord = _float_array(values, self.count * self._texcoord_size)
            else:
                _, location, size = parsed
                self._generic.append(
                    (location, size, _float_array(values, self.count * size))
                )

    @property
    def colors(self):
        """The color array, if this list has one."""
        return self._color

    @colors.setter
    def colors(self, values):
        if self._color is None:
            raise AttributeError("vertex list has no color attribute")
        self._color = _float_array(values, self.count * self._color_size)

    def draw(self, mode):
        if self._position is None:
            return
        glPushClientAttrib(GL_CLIENT_VERTEX_ARRAY_BIT)
        try:
            glEnableClientState(GL_VERTEX_ARRAY)
            glVertexPointer(self._position_size, GL_FLOAT, 0, self._position)
            if self._color is not None:
                glEnableClientState(GL_COLOR_ARRAY)
                glColorPointer(self._color_size, GL_FLOAT, 0, self._color)
            else:
                glDisableClientState(GL_COLOR_ARRAY)
            if self._texcoord is not None:
                glEnableClientState(GL_TEXTURE_COORD_ARRAY)
                glTexCoordPointer(self._texcoord_size, GL_FLOAT, 0, self._texcoord)
            else:
                glDisableClientState(GL_TEXTURE_COORD_ARRAY)
            for location, size, data in self._generic:
                glEnableVertexAttribArray(location)
                glVertexAttribPointer(location, size, GL_FLOAT, GL_FALSE, 0, data)
            glDrawArrays(mode, 0, self.count)
        finally:
            # GL_CLIENT_VERTEX_ARRAY_BIT covers generic arrays too, but an
            # explicit disable keeps a driver quirk from leaking location
            # state into the next draw.
            for location, _size, _data in self._generic:
                glDisableVertexAttribArray(location)
            glPopClientAttrib()

    def delete(self):
        self._position = None
        self._color = None
        self._texcoord = None
        self._generic = []


def draw_vertices(mode, vertices, components=3):
    """Draw a flat vertex sequence immediately with the current GL state."""
    count = len(vertices) // components
    FixedFunctionVertexList(count, (f"v{components}f", vertices)).draw(mode)


class DisposableBatch:
    """A tiny fixed-function replacement for ``pyglet.graphics.Batch``.

    ``add`` accepts the pyglet 1.x signature used throughout the game:
    ``add(count, mode, texture_group, ('v3f', data), ('t2f', data), ...)``.
    ``reset`` drops this frame's lists while keeping the batch reusable;
    ``dispose`` does the same for a batch that is being discarded.
    """

    def __init__(self):
        self.vertex_lists = []
        self._entries = []

    def add(self, count, mode, group, *attributes):
        vertex_list = FixedFunctionVertexList(count, *attributes)
        self.vertex_lists.append(vertex_list)
        self._entries.append((mode, group, vertex_list))
        return vertex_list

    def draw(self):
        for mode, group, vertex_list in self._entries:
            if group is not None:
                # Bind first: pyglet's TextureGroup.set_state selects texture
                # unit 0.  Enabling the target before that could enable the
                # wrong unit if the lighting pass left unit 1 active.
                group.set_state()
                # pyglet 1.5's TextureGroup also enabled the texture target;
                # pyglet 2.x only binds it.  Other render passes (touch
                # overlay, celestial sky) can leave GL_TEXTURE_2D disabled, so
                # restore the enable here or world geometry draws untextured.
                texture = getattr(group, "texture", None)
                if texture is not None:
                    glEnable(texture.target)
            try:
                vertex_list.draw(mode)
            finally:
                if group is not None:
                    group.unset_state()

    def reset(self):
        """Delete this frame's vertex lists, keep the batch reusable."""
        lists, self.vertex_lists = self.vertex_lists, []
        self._entries = []
        for vertex_list in lists:
            vertex_list.delete()

    def dispose(self):
        """Release a batch that is being discarded."""
        self.reset()


def active_window():
    """Return the game's single pyglet window, or ``None`` before creation."""
    windows = getattr(pyglet_app, "windows", None)
    if not windows:
        return None
    return next(iter(windows), None)


def sync_window_matrices():
    """Copy the fixed-function matrices into pyglet's shared WindowBlock.

    pyglet 2.x text layouts and image blits use shader uniforms instead of the
    fixed-function matrix stack.  Updating the window matrices keeps those
    drawables aligned with the renderer's glOrtho/gluPerspective/glRotatef
    state.  Safe to call before a window or GL context exists.
    """
    window = active_window()
    if window is None:
        return
    try:
        window.projection = Mat4(*glGetFloatv(GL_PROJECTION_MATRIX))
        window.view = Mat4(*glGetFloatv(GL_MODELVIEW_MATRIX))
    except Exception:
        # A label or blit must never take the game down if the backend lacks
        # the window matrix uniforms; it simply uses the last known values.
        pass


def _fixed_function_blit(self, x, y, z=0, width=None, height=None):
    """Draw a texture with the fixed-function pipeline.

    This replaces pyglet 2.x's shader/VAO-based ``Texture.blit``.  The old
    renderer drew UI icons and the held item through the fixed-function
    matrices, and the shader path also creates a throwaway VAO/VBO per call.
    """
    if self.id is None:
        return
    x1 = x - self.anchor_x
    y1 = y - self.anchor_y
    x2 = x1 + (self.width if width is None else width)
    y2 = y1 + (self.height if height is None else height)
    tex = self.tex_coords

    # pyglet 1.5's Texture.blit pushed/popped GL_ENABLE_BIT.  Keep the same
    # contract so UI blits cannot leak texture/blend state into later draws.
    glPushAttrib(GL_ENABLE_BIT)
    try:
        glActiveTexture(GL_TEXTURE0)
        glEnable(self.target)
        glBindTexture(self.target, self.id)
        glBegin(GL_QUADS)
        glTexCoord3f(tex[0], tex[1], tex[2])
        glVertex3f(x1, y1, z)
        glTexCoord3f(tex[3], tex[4], tex[5])
        glVertex3f(x2, y1, z)
        glTexCoord3f(tex[6], tex[7], tex[8])
        glVertex3f(x2, y2, z)
        glTexCoord3f(tex[9], tex[10], tex[11])
        glVertex3f(x1, y2, z)
        glEnd()
    finally:
        glPopAttrib()


_ORIGINAL_TEXT_DRAW = None


def _synced_text_draw(self):
    """TextLayout.draw wrapper that refreshes the window matrix uniforms."""
    sync_window_matrices()
    return _ORIGINAL_TEXT_DRAW(self)


def install_pyglet_compat():
    """Install the fixed-function shims for pyglet 2.x drawables.

    ``pyglet.text.Label`` inherits ``TextLayout.draw``, so one patch covers
    labels drawn directly (inventory slots, tooltips, touch buttons) as well
    as labels drawn through ``drawInfoLabel``.
    """
    global _ORIGINAL_TEXT_DRAW

    blit = pyglet.image.Texture.blit
    if not getattr(blit, "_fixed_function_blit", False):
        _fixed_function_blit._fixed_function_blit = True
        pyglet.image.Texture.blit = _fixed_function_blit

    text_draw = pyglet.text.layout.TextLayout.draw
    if not getattr(text_draw, "_fixed_function_sync", False):
        _ORIGINAL_TEXT_DRAW = text_draw
        _synced_text_draw._fixed_function_sync = True
        pyglet.text.layout.TextLayout.draw = _synced_text_draw


install_pyglet_compat()
