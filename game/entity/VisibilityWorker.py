"""Background line-of-sight visibility for entities.

The render thread never blocks on occlusion probing: each frame it submits a
cheap snapshot (entity ids + bounds + camera) to this worker, which runs the
expensive DDA "path-trace" (``Scene._prove_entity_occluded``) on another CPU
core and hands back the set of hidden entity ids.  A two-pass hysteresis
keeps borderline entities from flickering, mirroring the confirmation logic
the synchronous path used before.

The worker reads only cube dictionaries (GIL-safe key lookups), never GL,
and replaces its results atomically so the render thread can consume them
without locks.
"""

import logging
import threading


class VisibilityWorker(threading.Thread):
    """Computes entity occlusion off the render thread."""

    STREAK_REQUIRED = 2  # consecutive occluded passes before reporting hidden

    def __init__(self, scene):
        super().__init__(daemon=True, name="VisibilityWorker")
        self.scene = scene
        self._stop_event = threading.Event()
        self._wake = threading.Event()
        self._busy = False
        self._snapshot = None          # (tick, camera, [(id, bounds)])
        self._streaks = {}             # id -> consecutive occluded passes
        self.results = set()           # ids reported hidden (after hysteresis)
        self.results_tick = -1
        self.results_camera = None

    @property
    def busy(self):
        return self._busy

    def submit(self, tick, camera, items):
        """Hand the newest view to the worker; ignored while it is busy.

        ``items`` is a list of ``(id(entity), visibility_bounds)`` pairs for
        frustum-visible entities only, so the worker never wastes probes.
        """
        if self._busy or self._stop_event.is_set():
            return False
        self._snapshot = (tick, tuple(camera), items)
        self._busy = True
        self._wake.set()
        return True

    def close(self):
        self._stop_event.set()
        self._wake.set()

    def run(self):
        while not self._stop_event.is_set():
            self._wake.wait(1.0)
            self._wake.clear()
            snapshot = self._snapshot
            if snapshot is None:
                self._busy = False
                continue
            self.process(snapshot)

    def process(self, snapshot):
        """One visibility pass over a submitted snapshot (testable)."""
        prove = self.scene._prove_entity_occluded
        tick, camera, items = snapshot
        occluded = set()
        for key, bounds in items:
            try:
                if prove(camera, bounds) is not None:
                    occluded.add(key)
            except Exception as error:
                # a cube dict mutated mid-probe; retry next pass
                logging.debug("visibility probe failed: %s", error)
                continue
        self._apply_hysteresis(occluded)
        self.results = occluded & {
            key for key in self._streaks
            if self._streaks[key] >= self.STREAK_REQUIRED
        }
        self.results_tick = tick
        self.results_camera = camera
        self._busy = False

    def _apply_hysteresis(self, occluded):
        streaks = self._streaks
        for key in occluded:
            streaks[key] = streaks.get(key, 0) + 1
        for key in [key for key in streaks if key not in occluded]:
            streaks.pop(key, None)
        # keep the map bounded across entity churn
        if len(streaks) > 512:
            for key in list(streaks)[:len(streaks) - 512]:
                streaks.pop(key, None)

