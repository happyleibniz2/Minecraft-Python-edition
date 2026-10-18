"""Vanilla-style chat box opened with T, with slash commands.

Minecraft behaviour: T opens the chat, Escape cancels it, Enter sends the
typed text. Text starting with "/" is a command, anything else is shown as a
chat message. While the chat is open the player keeps no control input and
the mouse is released, exactly like vanilla.

Commands: /help, /gamemode <creative|survival|spectator>,
/day set <day|night|midnight|0-24000>, /clear, /exit.
"""

import sys
import time

import pyglet
import pygame
from OpenGL.GL import *

from functions import drawInfoLabel


WHITE = (255, 255, 255)
YELLOW = (255, 255, 85)
RED = (255, 85, 85)

GAME_MODES = {
    "creative": ("creative", "c", "1"),
    "survival": ("survival", "s", "0"),
    "spectator": ("spectator", "sp", "3"),
}

DAY_TIMES = {
    "day": 1000,
    "noon": 6000,
    "night": 13000,
    "midnight": 18000,
}

HELP_LINES = (
    "/help - show this help",
    "/gamemode <creative|survival|spectator> - change game mode",
    "/day set <day|night|midnight|0-24000> - set the world time",
    "/clear - clear the chat history",
    "/exit - quit the game",
)

MAX_INPUT = 100
MAX_HISTORY = 100
VISIBLE_LINES = 10
LINE_HEIGHT = 15
MESSAGE_LIFETIME = 10.0
MARGIN = 4
INPUT_BASELINE = 12
FIRST_LINE_BASELINE = 34


class Chat:
    """Minecraft-style chat: T opens, Enter sends, Escape cancels."""

    def __init__(self, gl):
        self.gl = gl
        self.is_open = False
        self.input = ""
        self.history = []  # (text, color, timestamp)
        self._previous_move_player = True
        self._measure = None

    # ----------------------------------------------------------------- state
    def open(self, prefill=""):
        """Open the chat, optionally pre-filled (used by the "/" key)."""
        if self.is_open:
            return
        self.is_open = True
        self.input = prefill
        self._previous_move_player = self.gl.allowEvents.get("movePlayer", True)
        self.gl.allowEvents["movePlayer"] = False

    def close(self):
        """Close the chat and give the player back control."""
        if not self.is_open:
            return
        self.is_open = False
        self.input = ""
        self.gl.allowEvents["movePlayer"] = self._previous_move_player

    # ----------------------------------------------------------------- input
    def handle_keydown(self, event):
        if event.key == pygame.K_ESCAPE:
            self.close()
        elif event.key in (pygame.K_RETURN, pygame.K_KP_ENTER):
            self.submit()
        elif event.key == pygame.K_BACKSPACE:
            self.input = self.input[:-1]
        else:
            char = getattr(event, "unicode", "")
            if char and char.isprintable() and len(self.input) < MAX_INPUT:
                self.input += char

    def submit(self):
        text = self.input.strip()
        self.close()
        if text:
            self.run(text)

    # -------------------------------------------------------------- commands
    def run(self, text):
        """Dispatch one submitted line: command or chat message."""
        if not text.startswith("/"):
            self.add_message(f"<You> {text}")
            return

        parts = text.split()
        command = parts[0].lower()
        args = parts[1:]

        if command == "/help":
            for line in HELP_LINES:
                self.add_message(line)
        elif command == "/gamemode":
            self._command_gamemode(args)
        elif command == "/day":
            self._command_day(args)
        elif command == "/clear":
            self.history.clear()
        elif command == "/exit":
            sys.exit()
        else:
            self.add_message(f"Unknown command: {command} (type /help)", RED)

    def _command_gamemode(self, args):
        if not args:
            self.add_message(
                "Usage: /gamemode <creative|survival|spectator>", RED)
            return
        player = getattr(self.gl, "player", None)
        if player is None:
            self.add_message("No player to change the gamemode of", RED)
            return

        mode = args[0].lower()
        if mode in GAME_MODES["creative"]:
            player.is_creative = True
            player.is_spectator = False
            self.add_message("Gamemode set to Creative", YELLOW)
        elif mode in GAME_MODES["survival"]:
            player.is_creative = False
            player.is_spectator = False
            self.add_message("Gamemode set to Survival", YELLOW)
        elif mode in GAME_MODES["spectator"]:
            player.is_creative = False
            player.is_spectator = True
            self.add_message("Gamemode set to Spectator", YELLOW)
        else:
            self.add_message(f"Unknown gamemode: {args[0]}", RED)

    def _command_day(self, args):
        if len(args) < 2 or args[0].lower() != "set":
            self.add_message(
                "Usage: /day set <day|night|midnight|0-24000>", RED)
            return

        value = args[1].lower()
        if value in DAY_TIMES:
            ticks = DAY_TIMES[value]
        else:
            try:
                ticks = int(value)
            except ValueError:
                self.add_message(f"Unknown time: {args[1]}", RED)
                return
            if not 0 <= ticks <= 23999:
                self.add_message("Time must be between 0 and 24000", RED)
                return

        day_night = getattr(self.gl, "dayNight", None)
        if day_night is None:
            self.add_message("No world loaded", RED)
            return
        day_night.set_time(ticks)
        self.add_message(f"Set the time to {ticks}", YELLOW)

    # --------------------------------------------------------------- history
    def add_message(self, text, color=WHITE):
        self.history.append((text, color, time.time()))
        if len(self.history) > MAX_HISTORY:
            del self.history[:-MAX_HISTORY]

    # --------------------------------------------------------------- drawing
    def _text_width(self, text):
        if self._measure is None:
            self._measure = pyglet.text.Label(
                "", font_name="Minecraft Rus", font_size=12)
        self._measure.text = text or " "
        return self._measure.content_width

    def draw(self):
        """Draw history lines and, when open, the input box (2D mode only)."""
        now = time.time()
        if self.is_open:
            visible = self.history[-VISIBLE_LINES:]
        else:
            visible = [message for message in self.history[-VISIBLE_LINES:]
                       if now - message[2] < MESSAGE_LIFETIME]
        if not visible and not self.is_open:
            return

        # translucent black bars behind every line, like vanilla chat
        bars = []
        for index, (text, _color, _stamp) in enumerate(visible):
            baseline = FIRST_LINE_BASELINE + (len(visible) - 1 - index) * LINE_HEIGHT
            bars.append((MARGIN, baseline - 3,
                         MARGIN + self._text_width(text) + 6, baseline + 11))
        if self.is_open:
            width = max(self._text_width(self.input), 120)
            bars.append((MARGIN, 4, MARGIN + width + 10, 26))

        glPushAttrib(GL_ENABLE_BIT | GL_CURRENT_BIT)
        try:
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDisable(GL_TEXTURE_2D)
            glColor4f(0, 0, 0, 0.4)
            glBegin(GL_QUADS)
            for x0, y0, x1, y1 in bars:
                glVertex2f(x0, y0)
                glVertex2f(x1, y0)
                glVertex2f(x1, y1)
                glVertex2f(x0, y1)
            glEnd()
        finally:
            glPopAttrib()

        for index, (text, color, _stamp) in enumerate(visible):
            baseline = FIRST_LINE_BASELINE + (len(visible) - 1 - index) * LINE_HEIGHT
            drawInfoLabel(self.gl, text, xx=MARGIN + 2, yy=baseline,
                          style=[("", "")], size=12, label_color=color)

        if self.is_open:
            cursor = "_" if (now % 1.0) < 0.5 else ""
            drawInfoLabel(self.gl, self.input + cursor,
                          xx=MARGIN + 2, yy=INPUT_BASELINE,
                          style=[("", "")], size=12)
