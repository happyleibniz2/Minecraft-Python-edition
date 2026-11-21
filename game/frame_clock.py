"""Monotonic frame limiter and FPS counter.

This replaces ``pygame.time.Clock``.  The game uses a variable timestep and
only calls ``tick(MAX_FPS)`` to cap the frame rate and ``get_fps()`` for the
window caption, so the same public surface is preserved:

``tick(fps)``
    Sleep just enough to keep the frame time at or above ``1 / fps`` and
    return the elapsed milliseconds since the previous call.
``get_fps()``
    Average FPS over the last ten ticks.  Returns ``0.0`` before the first
    completed tick, matching the old caption ``Minecraft 1 0.0``.

The old cap was ``MAX_FPS = 2000``, i.e. 0.5 ms per frame.  ``time.sleep``
cannot reliably honour sub-millisecond delays on every Windows build, so the
limiter intentionally skips waits shorter than one millisecond.  That keeps
the cap from turning into an accidental ~15 ms scheduler delay; it does not
change the variable-timestep physics.
"""

import time
from collections import deque


class FrameClock:
    def __init__(self):
        self._last = None
        self._durations = deque(maxlen=10)

    def tick(self, fps=0):
        """Limit to ``fps`` frames per second and return elapsed milliseconds."""
        now = time.perf_counter()
        if self._last is None:
            self._last = now
            return 0

        elapsed = now - self._last

        if fps:
            target = 1.0 / float(fps)
            remaining = target - elapsed
            # Sub-millisecond sleeps are unreliable on Windows and can add a
            # full scheduler quantum.  The old 2000 FPS cap never needed one.
            if remaining > 0.001:
                time.sleep(remaining)
                now = time.perf_counter()
                elapsed = now - self._last

        self._last = now
        self._durations.append(max(elapsed, 1e-9))
        return int(elapsed * 1000)

    def get_fps(self):
        if not self._durations:
            return 0.0
        return len(self._durations) / sum(self._durations)

    def get_time(self):
        """Elapsed milliseconds of the most recent tick (0 before the first)."""
        if not self._durations:
            return 0
        return int(self._durations[-1] * 1000)
