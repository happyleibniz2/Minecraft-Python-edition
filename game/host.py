"""Thin pyglet window/event host.

This module owns the only ``pyglet.window.Window`` and therefore the only
OpenGL context.  It deliberately does not use ``pyglet.app.run()`` or
``pyglet.graphics``: the game keeps its existing manual loop and raw PyOpenGL
rendering, and calls:

    host.pump()   # pump OS events
    ... update game ...
    host.flip()   # swap buffers

The host maintains the polled input state that the game previously read from
``pygame.key.get_pressed()`` and ``pygame.mouse.get_pressed()``.  Mouse
coordinates are exposed in pygame's top-left, y-down convention; motion
deltas are exposed in pygame's ``event.rel`` convention (positive y = down).
"""

import logging

# Must be set before pyglet.gl/pyglet.window are imported: pyglet 2.x
# otherwise creates a hidden 1x1 shadow window and GL context at import time.
import pyglet
pyglet.options['shadow_window'] = False

from pyglet import app as pyglet_app
from pyglet import clock as pyglet_clock
from pyglet.event import EVENT_HANDLED
from pyglet.gl import Config, ConfigException
from pyglet.window import NoSuchConfigException, Window, mouse


# pyglet uses LEFT=1, MIDDLE=2, RIGHT=4.  The game's original pygame handlers
# used 1/2/3 for left/middle/right and 4/5 for the wheel.
_BUTTON_TO_GAME = {
    mouse.LEFT: 1,
    mouse.MIDDLE: 2,
    mouse.RIGHT: 3,
    mouse.MOUSE4: 4,
    mouse.MOUSE5: 5,
}
_BUTTON_TO_INDEX = {
    mouse.LEFT: 0,
    mouse.MIDDLE: 1,
    mouse.RIGHT: 2,
}


class PygletHost:
    """Owns one pyglet window and forwards normalized events to the game."""

    def __init__(self, width, height, caption="", vsync=True, resizable=True):
        self.closed = False
        self.focused = True
        self.keys_down = set()
        self.modifiers = 0
        self.mouse_pos = (int(width) // 2, int(height) // 2)
        self.mouse_buttons = (False, False, False)

        self.event_handler = None
        self.touch_controls = None
        self.resize_callback = None

        self._mouse_visible = True
        self._exclusive = False
        self._exclusive_broken = False
        self._scroll_accum = 0.0

        self.window = self._create_window(
            int(width), int(height), caption, vsync, resizable
        )
        self.msaa_samples = self._sample_count(self.window.config)
        self.window.push_handlers(self)
        self.window.set_caption(caption)

    # ------------------------------------------------------------------
    # Window creation
    # ------------------------------------------------------------------
    @staticmethod
    def _sample_count(config):
        try:
            if config.sample_buffers and config.samples:
                return int(config.samples)
        except (AttributeError, TypeError):
            pass
        return 0

    @staticmethod
    def _create_window(width, height, caption, vsync, resizable):
        # Match the old pygame request: double buffer, 24-bit depth, 4x MSAA,
        # vsync, resizable.
        #
        # A template Config with no major/minor version is matched against the
        # platform's pixel formats.  With the shadow window disabled the first
        # window uses the legacy PFD/wglCreateContext path, which yields the
        # compatibility context the fixed-function renderer and GLSL 1.20
        # lighting shader require.  pyglet 2.x's implicit Window default asks
        # for OpenGL 3.3 instead, so a Config must always be passed.
        #
        # The legacy PFD path cannot express multisampling; PygletHost reports
        # the actual sample count and Scene disables AA when it is zero.
        msaa_config = Config(
            double_buffer=True,
            depth_size=24,
            sample_buffers=1,
            samples=4,
        )
        try:
            return Window(
                width,
                height,
                caption=caption,
                resizable=resizable,
                vsync=vsync,
                config=msaa_config,
            )
        except (NoSuchConfigException, ConfigException):
            logging.warning(
                "4x MSAA context unavailable; retrying without multisampling"
            )
            fallback = Config(double_buffer=True, depth_size=24)
            return Window(
                width,
                height,
                caption=caption,
                resizable=resizable,
                vsync=vsync,
                config=fallback,
            )

    # ------------------------------------------------------------------
    # Frame plumbing
    # ------------------------------------------------------------------
    def pump(self):
        """Pump OS events and scheduled pyglet callbacks.

        Audio is disabled in this build, so there are no media events to drain;
        the platform event loop and clock are still ticked so pyglet stays
        healthy.
        """
        if self.closed or self.window is None:
            return
        self.window.dispatch_events()
        # Keeps pyglet's own platform event loop drained.  Nothing is queued
        # here in a no-audio build, but the call is harmless and cheap.
        pyglet_app.platform_event_loop.dispatch_posted_events()
        # Drives pyglet.clock callbacks.  It does not touch the game's own
        # clock.
        pyglet_clock.tick()

    def flip(self):
        if self.window is not None:
            self.window.flip()

    def close(self):
        self.closed = True
        window = self.window
        self.window = None
        if window is not None:
            try:
                window.close()
            except Exception:
                logging.exception("Error while closing the pyglet window")

    # ------------------------------------------------------------------
    # Window properties / commands
    # ------------------------------------------------------------------
    @property
    def size(self):
        if self.window is None:
            return (0, 0)
        return (self.window.width, self.window.height)

    @property
    def width(self):
        return self.size[0]

    @property
    def height(self):
        return self.size[1]

    def set_caption(self, caption):
        if self.window is not None:
            self.window.set_caption(caption)

    def set_fullscreen(self, fullscreen):
        if self.window is not None:
            self.window.set_fullscreen(bool(fullscreen))

    def set_size(self, width, height):
        if self.window is not None:
            self.window.set_size(int(width), int(height))

    def set_mouse_visible(self, visible):
        visible = bool(visible)
        if visible == self._mouse_visible or self.window is None:
            return
        self._mouse_visible = visible
        self.window.set_mouse_visible(visible)

    def set_exclusive_mouse(self, exclusive):
        """Request exclusive mouse and return the state actually in effect."""
        exclusive = bool(exclusive)
        if exclusive == self._exclusive or self.window is None:
            return self._exclusive
        if exclusive and self._exclusive_broken:
            return self._exclusive
        try:
            self.window.set_exclusive_mouse(exclusive)
            self._exclusive = exclusive
            # pyglet re-applies the platform cursor whenever exclusive mode
            # toggles, so the cached visibility decision has to be re-sent.
            self._mouse_visible = None
        except Exception as exc:
            # Raw input can be unavailable in some remote/VM sessions.  The
            # game remains playable with the normal cursor; do not crash.
            self._exclusive = False
            if exclusive:
                self._exclusive_broken = True
                logging.warning("Cannot enter pyglet exclusive mouse mode: %s", exc)
        return self._exclusive

    # ------------------------------------------------------------------
    # Polled input state
    # ------------------------------------------------------------------
    def key_down(self, symbol):
        return symbol in self.keys_down

    def dispatch_synthetic_key(self, symbol, pressed):
        """Notify event listeners without changing the polled key state.

        TouchControls uses this for its W/A/S/D/Space transitions.  The old
        ``pygame.event.post`` path also left ``pygame.key.get_pressed()``
        unchanged, so Player must keep reading TouchInputState instead.
        """
        if self.event_handler is None:
            return
        if pressed:
            self.event_handler.on_key_press(symbol, self.modifiers)
        else:
            self.event_handler.on_key_release(symbol, self.modifiers)

    def _set_mouse_button(self, button, pressed):
        index = _BUTTON_TO_INDEX.get(button)
        if index is None:
            return
        state = list(self.mouse_buttons)
        state[index] = bool(pressed)
        self.mouse_buttons = tuple(state)

    def _update_mouse_pos(self, x, y):
        if self._exclusive:
            # Raw exclusive motion reports (0, 0) as the position; keep the
            # last real window position so menus do not jump when grab ends.
            return
        self.mouse_pos = (int(x), int(self.height - y))

    # ------------------------------------------------------------------
    # pyglet event handlers
    # ------------------------------------------------------------------
    def on_close(self):
        self.closed = True
        return EVENT_HANDLED

    def on_resize(self, width, height):
        if self.resize_callback is not None:
            self.resize_callback(width, height)
        # Skip BaseWindow.on_resize: the game owns its projections and will
        # restore them on the next set2d()/set3d() call.
        return EVENT_HANDLED

    def on_activate(self):
        self.focused = True
        # A transient raw-input failure may be fixed by the new focus/session.
        self._exclusive_broken = False

    def on_deactivate(self):
        self.focused = False
        self.keys_down.clear()
        self.mouse_buttons = (False, False, False)
        self.set_exclusive_mouse(False)

    def on_key_press(self, symbol, modifiers):
        self.modifiers = modifiers
        self.keys_down.add(symbol)
        if self.event_handler is not None:
            self.event_handler.on_key_press(symbol, modifiers)

    def on_key_release(self, symbol, modifiers):
        self.modifiers = modifiers
        self.keys_down.discard(symbol)
        if self.event_handler is not None:
            self.event_handler.on_key_release(symbol, modifiers)

    def on_mouse_motion(self, x, y, dx, dy):
        self._update_mouse_pos(x, y)
        if self.touch_controls is not None:
            self.touch_controls.handle_mouse_motion(
                x, self.height - y, self.mouse_buttons[0]
            )
        if self.event_handler is not None:
            # pyglet's y axis points up; pygame's event.rel.y points down.
            self.event_handler.on_mouse_motion(x, y, dx, -dy)

    def on_mouse_drag(self, x, y, dx, dy, buttons, modifiers):
        self.modifiers = modifiers
        self.mouse_buttons = (
            bool(buttons & mouse.LEFT),
            bool(buttons & mouse.MIDDLE),
            bool(buttons & mouse.RIGHT),
        )
        self._update_mouse_pos(x, y)
        if self.touch_controls is not None:
            self.touch_controls.handle_mouse_motion(
                x, self.height - y, self.mouse_buttons[0]
            )
        if self.event_handler is not None:
            self.event_handler.on_mouse_motion(x, y, dx, -dy)

    def on_mouse_press(self, x, y, button, modifiers):
        self.modifiers = modifiers
        self._update_mouse_pos(x, y)
        self._set_mouse_button(button, True)
        game_button = _BUTTON_TO_GAME.get(button, button)
        if self.touch_controls is not None:
            self.touch_controls.handle_mouse_press(
                x, self.height - y, game_button
            )
        if self.event_handler is not None:
            self.event_handler.on_mouse_press(x, y, game_button, modifiers)

    def on_mouse_release(self, x, y, button, modifiers):
        self.modifiers = modifiers
        self._update_mouse_pos(x, y)
        self._set_mouse_button(button, False)
        game_button = _BUTTON_TO_GAME.get(button, button)
        if self.touch_controls is not None:
            self.touch_controls.handle_mouse_release(
                x, self.height - y, game_button
            )
        if self.event_handler is not None:
            self.event_handler.on_mouse_release(x, y, game_button, modifiers)

    def on_mouse_scroll(self, x, y, scroll_x, scroll_y):
        self._update_mouse_pos(x, y)
        # pyglet reports whole wheel notches as +/-1.  Trackpads may report
        # fractions; accumulate them so the hotbar still advances one slot per
        # physical notch, matching pygame's discrete wheel buttons 4/5.
        self._scroll_accum += scroll_y
        while abs(self._scroll_accum) >= 1.0:
            step = 1.0 if self._scroll_accum > 0 else -1.0
            self._scroll_accum -= step
            if self.event_handler is not None:
                self.event_handler.on_mouse_scroll(x, y, 0, step)
