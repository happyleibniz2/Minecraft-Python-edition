"""Touch controls for Windows touchscreens (mouse-driven fallback).

The game normally reads movement from ``PygletHost.keys_down`` and look from
relative mouse motion.  That is a *polled* state, so simply dispatching
synthetic key events is not enough to drive the player.  This module therefore
does two things:

* It owns a small analog ``TouchInputState`` which ``Player.updatePosition``
  reads in addition to the keyboard.  That gives the joystick true analog
  movement instead of an on/off key press.
* It translates primary-mouse presses/drags into the exact same calls the
  mouse handlers use (``player.mouseEvent``, ``player.look``,
  ``player.inventory.showWindow``).

pyglet 2.x on Windows exposes no raw ``FINGER*`` events, so touch mode is
mouse-driven and must be enabled explicitly: set ``TOUCH_MODE = True`` in
settings, or press F10 at runtime.  Multi-touch is limited to the primary
pointer.  While touch mode is active the cursor stays visible and the game
does not grab the mouse, so the on-screen controls remain usable.
"""

import math
import time

# Must run before pyglet.window is imported: pyglet 2.x otherwise creates a
# hidden 1x1 shadow window and a second GL context, and the game must own
# exactly one window/context.
import pyglet
pyglet.options['shadow_window'] = False
from pyglet.window import key
from OpenGL.GL import *

import settings as game_settings


class TouchInputState:
    """Analog input consumed by :meth:`Player.updatePosition`."""

    __slots__ = ("forward", "strafe", "jump", "sneak", "sprint")

    def __init__(self):
        self.reset()

    def reset(self):
        self.forward = 0.0
        self.strafe = 0.0
        self.jump = False
        self.sneak = False
        self.sprint = False


class TouchButton:
    __slots__ = ("name", "label", "x", "y", "radius", "color")

    def __init__(self, name, label, x, y, radius, color):
        self.name = name
        self.label = label
        self.x = x
        self.y = y
        self.radius = radius
        self.color = color


class TouchControls:
    """Virtual joystick, drag-to-look and on-screen action buttons."""

    JOYSTICK_DEADZONE = 0.12
    JOYSTICK_ACTIVATION = 1.35   # touch a little outside the base still works
    BUTTON_ACTIVATION = 1.18
    MOUSE_GRACE_SECONDS = 0.20   # ignore mouse motion right after touch

    def __init__(self, scene, player, is_gameplay=None, pause_callback=None,
                 enabled=None):
        self.scene = scene
        self.player = player
        self.is_gameplay = is_gameplay
        self.pause_callback = pause_callback

        if enabled is None:
            enabled = bool(getattr(game_settings, "TOUCH_MODE", False))
        self.enabled = bool(enabled)
        self.look_sensitivity = float(
            getattr(game_settings, "TOUCH_LOOK_SENSITIVITY", 0.22)
        )

        self.input = TouchInputState()
        # Player.updatePosition() looks for this attribute.  Keeping the hook
        # here means the touch module owns all touch state.
        self.player.touch_input = self.input

        self.buttons = []
        self.inventory_button = None
        self.pause_button = None
        self.close_button = None
        self._labels = {}
        self._last_layout = None

        self._pointers = {}
        self._role_owner = {}
        self._pressed = set()

        self.break_held = False
        self._place_requested = False
        self._inventory_requested = False
        self._pause_requested = False
        self._close_requested = False

        self._joystick_knob = (0.0, 0.0)
        self._joystick_active = False
        self._last_touch_time = 0.0

        # Dispatch W/A/S/D and Space transitions for mods that listen to
        # events.  The core player movement still comes from TouchInputState
        # because the host's polled key state is intentionally not changed by
        # synthetic events.
        self.emit_key_events = True
        self._key_state = {}

        self._update_layout()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def handle_mouse_press(self, x, y, button):
        """Feed a primary mouse press to the touch layer.

        Coordinates are OpenGL-style (origin bottom-left, y up), matching the
        overlay layout.  Only button 1 is treated as a finger.
        """
        if not self.enabled or button != 1:
            return False
        self._touch()
        pointer = "sdl-touch"
        if pointer not in self._pointers:
            self._pointer_down(pointer, float(x), float(y))
            return True
        return False

    def handle_mouse_release(self, x, y, button):
        if not self.enabled or button != 1:
            return False
        pointer = "sdl-touch"
        if pointer in self._pointers:
            self._touch()
            self._pointer_up(pointer)
            return True
        return False

    def handle_mouse_motion(self, x, y, left_down):
        if not self.enabled:
            return False
        pointer = "sdl-touch"
        x, y = float(x), float(y)
        if pointer in self._pointers:
            self._touch()
            self._pointer_move(pointer, x, y)
            return True
        if left_down:
            # Some platforms omit the initial press; emulate it.
            self._touch()
            self._pointer_down(pointer, x, y)
            self._pointer_move(pointer, x, y)
            return True
        return False

    def update(self, dt):
        """Apply queued one-shot actions.  Call once per game tick."""
        self._update_layout()

        if not self.enabled:
            self._reset_inputs()
            return

        if self.gui_open:
            self._reset_inputs(clear_pointers=True)
            if self._close_requested:
                self._close_requested = False
                window = self._inventory_window()
                if window is not None and getattr(window, "visible", False):
                    window.destroyWindow()
            return

        if not self._gameplay_active():
            self._reset_inputs(clear_pointers=True)
            return

        if self._place_requested:
            self._place_requested = False
            # Button 3 is the engine's right-click / place-block path.
            self.player.mouseEvent(3, dt)

        if self._inventory_requested:
            self._inventory_requested = False
            self.player.inventory.showWindow()

        if self._pause_requested:
            self._pause_requested = False
            if self.pause_callback is not None:
                self.pause_callback()

    def render(self):
        """Draw the overlay.  Call after the normal HUD has been drawn."""
        if not self.enabled:
            return

        if self.gui_open:
            # Keep a single touch close button available for the inventory,
            # whose ModalWindow otherwise only closes on the Escape key.
            if self._inventory_window() is not None:
                self._render_close_button()
            return

        if not self._gameplay_active():
            return

        self._update_layout()
        self.scene.set2d()

        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT |
                     GL_CURRENT_BIT | GL_TEXTURE_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)

            self._draw_joystick()
            active_buttons = self._active_buttons()
            for button in active_buttons:
                self._draw_button_shape(button)
            # Labels last: pyglet enables texturing while drawing.
            for button in active_buttons:
                self._draw_button_label(button)
        finally:
            glPopAttrib()

    def toggle(self):
        """Enable/disable touch mode (bound to F10 in the main loop)."""
        self.enabled = not self.enabled
        if not self.enabled:
            self._reset_inputs(clear_pointers=True)

    def reset(self):
        """Clear all held touch state, e.g. when a world is unloaded."""
        self._reset_inputs(clear_pointers=True)
        self._close_requested = False

    @property
    def gui_open(self):
        """True while the inventory or any mod modal window is open."""
        return self._inventory_window() is not None or bool(
            getattr(self.scene, "updateEvents", ())
        )

    @property
    def pointer_active(self):
        return bool(self._pointers)

    @property
    def blocks_mouse(self):
        """True while the mouse pointer belongs to a touch gesture."""
        if not self.enabled:
            return False
        if self._pointers:
            return True
        return (time.monotonic() - self._last_touch_time) < self.MOUSE_GRACE_SECONDS

    # ------------------------------------------------------------------
    # Event helpers
    # ------------------------------------------------------------------
    def _touch(self):
        self._last_touch_time = time.monotonic()

    def _pointer_down(self, pointer, x, y):
        if pointer in self._pointers:
            return

        if self.gui_open:
            self._gui_pointer_down(pointer, x, y)
            return

        if not self._gameplay_active():
            return

        # Buttons take priority over the look area.
        for button in self._active_buttons():
            if self._hit(button, x, y):
                if button.name in self._role_owner:
                    return
                self._pointers[pointer] = {
                    "role": "button", "name": button.name, "x": x, "y": y,
                }
                self._role_owner[button.name] = pointer
                self._button_down(button.name)
                return

        # Virtual joystick, bottom-left.
        if self._distance(x, y, *self.joy_center) <= (
                self.joy_radius * self.JOYSTICK_ACTIVATION):
            if "joystick" in self._role_owner:
                return
            self._pointers[pointer] = {
                "role": "joystick", "x": x, "y": y,
            }
            self._role_owner["joystick"] = pointer
            self._joystick_active = True
            self._update_joystick(x, y)
            return

        # Look area: the right half of the screen.
        if x >= self.scene.WIDTH * 0.5:
            if "look" in self._role_owner:
                return
            self._pointers[pointer] = {"role": "look", "x": x, "y": y}
            self._role_owner["look"] = pointer

    def _gui_pointer_down(self, pointer, x, y):
        """Only the close button is handled while a modal GUI is open."""
        if self._inventory_window() is None:
            return
        if not self._hit(self.close_button, x, y):
            # Everything else is left to the modal window / normal mouse path.
            return
        if "close" in self._role_owner:
            return
        self._pointers[pointer] = {
            "role": "button", "name": "close", "x": x, "y": y,
        }
        self._role_owner["close"] = pointer
        self._close_requested = True

    def _pointer_move(self, pointer, x, y):
        data = self._pointers.get(pointer)
        if data is None:
            return
        self._touch()

        role = data["role"]
        if role == "joystick":
            self._update_joystick(x, y)
        elif role == "look":
            dx = x - data["x"]
            # Finger positions are stored with OpenGL's y-up axis, while the
            # mouse path (and Player.look) uses screen y-down deltas.  Flip
            # the sign so dragging down looks down.
            dy = data["y"] - y
            data["x"], data["y"] = x, y
            if self._gameplay_active():
                self.player.look(dx * self.look_sensitivity,
                                 dy * self.look_sensitivity)
        # Button fingers stay held even if they slide off the button, which is
        # what players expect from a physical controller.

    def _pointer_up(self, pointer):
        data = self._pointers.pop(pointer, None)
        if data is None:
            return

        role = data["role"]
        if role == "joystick":
            if self._role_owner.get("joystick") == pointer:
                self._role_owner.pop("joystick", None)
            self._joystick_active = False
            self._joystick_knob = (0.0, 0.0)
            self._set_move(0.0, 0.0)
        elif role == "look":
            if self._role_owner.get("look") == pointer:
                self._role_owner.pop("look", None)
        elif role == "button":
            name = data["name"]
            if self._role_owner.get(name) == pointer:
                self._role_owner.pop(name, None)
                self._button_up(name)

    def _button_down(self, name):
        self._pressed.add(name)
        if name == "jump":
            self.input.jump = True
            self._emit_key(key.SPACE, True)
        elif name == "break":
            self.break_held = True
        elif name == "place":
            self._place_requested = True
        elif name == "inventory":
            self._inventory_requested = True
        elif name == "pause":
            self._pause_requested = True
        elif name == "close":
            self._close_requested = True

    def _button_up(self, name):
        self._pressed.discard(name)
        if name == "jump":
            self.input.jump = False
            self._emit_key(key.SPACE, False)
        elif name == "break":
            self.break_held = False

    def _update_joystick(self, x, y):
        dx = x - self.joy_center[0]
        dy = y - self.joy_center[1]
        distance = math.hypot(dx, dy)
        radius = self.joy_radius

        if distance > radius and distance > 1e-9:
            dx = dx / distance * radius
            dy = dy / distance * radius
            distance = radius

        self._joystick_knob = (dx, dy)
        magnitude = min(1.0, distance / radius)

        if magnitude <= self.JOYSTICK_DEADZONE:
            self._set_move(0.0, 0.0)
            return

        # Rescale the post-deadzone range so small movements are not lost.
        scale = min(1.0, (magnitude - self.JOYSTICK_DEADZONE) /
                    (1.0 - self.JOYSTICK_DEADZONE))
        nx = dx / max(distance, 1e-9)
        ny = dy / max(distance, 1e-9)
        self._set_move(ny * scale, nx * scale)

    def _set_move(self, forward, strafe):
        self.input.forward = forward
        self.input.strafe = strafe
        # Keep mods that listen for key events in sync.  This is cosmetic for
        # the vanilla engine; Player reads TouchInputState directly.
        self._emit_key(key.W, forward > 0.35)
        self._emit_key(key.S, forward < -0.35)
        self._emit_key(key.D, strafe > 0.35)
        self._emit_key(key.A, strafe < -0.35)

    def _emit_key(self, symbol, pressed):
        if not self.emit_key_events:
            return
        if self._key_state.get(symbol) == pressed:
            return
        self._key_state[symbol] = pressed
        host = getattr(self.scene, "host", None)
        if host is not None:
            host.dispatch_synthetic_key(symbol, pressed)

    def _reset_inputs(self, clear_pointers=False):
        if self.input.forward or self.input.strafe:
            self._set_move(0.0, 0.0)
        if self.input.jump:
            self._emit_key(key.SPACE, False)
        self.input.jump = False
        self.input.sneak = False
        self.input.sprint = False
        self.break_held = False
        self._joystick_active = False
        self._joystick_knob = (0.0, 0.0)
        self._place_requested = False
        self._inventory_requested = False
        self._pause_requested = False
        if clear_pointers:
            self._pointers.clear()
            self._role_owner.clear()
            self._pressed.clear()

    # ------------------------------------------------------------------
    # Layout
    # ------------------------------------------------------------------
    def _update_layout(self):
        width = max(1, int(self.scene.WIDTH))
        height = max(1, int(self.scene.HEIGHT))
        if (width, height) == self._last_layout:
            return
        self._last_layout = (width, height)

        short = min(width, height)
        margin = max(16.0, short * 0.05)

        self.joy_radius = max(48.0, min(84.0, short * 0.15))
        self.joy_center = (self.joy_radius + margin,
                           self.joy_radius + margin)

        button_radius = max(26.0, min(44.0, short * 0.085))
        column_x = width - button_radius - margin
        jump_y = margin + button_radius + max(4.0, short * 0.012)
        break_radius = button_radius * 0.88
        break_y = jump_y + button_radius + break_radius + max(10.0, short * 0.035)
        place_y = break_y + break_radius * 2 + max(8.0, short * 0.025)

        self.buttons = [
            TouchButton("jump", "JUMP", column_x, jump_y,
                        button_radius, (0.28, 0.78, 0.47, 0.38)),
            TouchButton("break", "BREAK", column_x, break_y,
                        break_radius, (0.92, 0.43, 0.31, 0.36)),
            TouchButton("place", "PLACE", column_x, place_y,
                        break_radius, (0.35, 0.59, 0.92, 0.36)),
        ]

        small = max(18.0, min(26.0, short * 0.052))
        self.inventory_button = TouchButton(
            "inventory", "INV", width - small - margin,
            height - small - margin, small, (0.78, 0.78, 0.82, 0.34),
        )
        self.pause_button = TouchButton(
            "pause", "II", width - small * 3.0 - margin * 1.5,
            height - small - margin, small * 0.85, (0.78, 0.78, 0.82, 0.30),
        )
        self.close_button = TouchButton(
            "close", "X", width - small - margin,
            height - small - margin, small, (0.92, 0.35, 0.35, 0.48),
        )

    def _active_buttons(self):
        return self.buttons + [self.inventory_button, self.pause_button]

    @staticmethod
    def _distance(x, y, cx, cy):
        return math.hypot(x - cx, y - cy)

    def _hit(self, button, x, y):
        return self._distance(x, y, button.x, button.y) <= (
            button.radius * self.BUTTON_ACTIVATION)

    # ------------------------------------------------------------------
    # Rendering
    # ------------------------------------------------------------------
    def _draw_joystick(self):
        cx, cy = self.joy_center
        active = self._joystick_active

        self._draw_circle(cx, cy, self.joy_radius,
                          (1.0, 1.0, 1.0, 0.10 if active else 0.06))
        self._draw_ring(cx, cy, self.joy_radius,
                        (1.0, 1.0, 1.0, 0.55 if active else 0.32))

        knob_radius = self.joy_radius * 0.42
        knob_x = cx + self._joystick_knob[0] * 0.72
        knob_y = cy + self._joystick_knob[1] * 0.72
        self._draw_circle(knob_x, knob_y, knob_radius,
                          (0.62, 0.84, 1.0, 0.42 if active else 0.26))
        self._draw_ring(knob_x, knob_y, knob_radius, (1.0, 1.0, 1.0, 0.62))

    def _draw_button_shape(self, button):
        pressed = button.name in self._pressed
        red, green, blue, alpha = button.color
        if pressed:
            alpha = min(1.0, alpha + 0.28)
        self._draw_circle(button.x, button.y, button.radius,
                          (red, green, blue, alpha))
        self._draw_ring(button.x, button.y, button.radius,
                        (1.0, 1.0, 1.0, 0.65 if pressed else 0.42))

    def _draw_button_label(self, button):
        label = self._label_for(button.label)
        label.x = button.x
        label.y = button.y
        font_size = max(7, int(button.radius * 0.52))
        if label.font_size != font_size:
            label.font_size = font_size
        label.draw()

    def _render_close_button(self):
        self.scene.set2d()
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_LINE_BIT |
                     GL_CURRENT_BIT | GL_TEXTURE_BIT)
        try:
            glDisable(GL_TEXTURE_2D)
            glDisable(GL_DEPTH_TEST)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            self._draw_button_shape(self.close_button)
            self._draw_button_label(self.close_button)
        finally:
            glPopAttrib()

    def _label_for(self, text):
        label = self._labels.get(text)
        if label is None:
            label = pyglet.text.Label(
                text,
                font_name="Minecraft Rus",
                font_size=10,
                color=(255, 255, 255, 235),
                anchor_x="center",
                anchor_y="center",
            )
            self._labels[text] = label
        return label

    def _draw_circle(self, cx, cy, radius, color, segments=40):
        glDisable(GL_TEXTURE_2D)
        glColor4f(*color)
        glBegin(GL_TRIANGLE_FAN)
        glVertex2f(cx, cy)
        for index in range(segments + 1):
            angle = math.tau * index / segments
            glVertex2f(cx + math.cos(angle) * radius,
                       cy + math.sin(angle) * radius)
        glEnd()

    def _draw_ring(self, cx, cy, radius, color, segments=40):
        glDisable(GL_TEXTURE_2D)
        glLineWidth(max(1.0, radius * 0.055))
        glColor4f(*color)
        glBegin(GL_LINE_LOOP)
        for index in range(segments):
            angle = math.tau * index / segments
            glVertex2f(cx + math.cos(angle) * radius,
                       cy + math.sin(angle) * radius)
        glEnd()

    # ------------------------------------------------------------------
    # State helpers
    # ------------------------------------------------------------------
    def _gameplay_active(self):
        if not self.enabled:
            return False
        if self.is_gameplay is not None and not self.is_gameplay():
            return False
        events = getattr(self.scene, "allowEvents", {})
        return bool(events.get("keyboardAndMouse", True) and
                    events.get("movePlayer", True) and
                    events.get("grabMouse", True))

    def _inventory_window(self):
        inventory = getattr(self.player, "inventory", None)
        window = getattr(inventory, "window", None)
        if window is not None and getattr(window, "visible", False):
            return window
        return None
