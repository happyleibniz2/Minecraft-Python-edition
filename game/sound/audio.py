"""Silent audio stub.

The target environment (a restricted school/class machine) blocks or crashes
on audio initialisation, so ``pyglet.media`` is deliberately **not** imported
anywhere in this project.  No decoder, no audio driver, no ``Player`` and no
thread is ever created here.

Gameplay modules keep calling the same API they always used.  Every call in
this module is a no-op and every effect plays nothing, so code that inspects
the returned channel (``if chnl is not None: ...``) keeps working.

Removed from the old implementation:

* effect decoding through the WMF/OGG codecs (~150 ms per file, ~18 s for the
  whole bank, which used to freeze the logo screen);
* the background preloader thread that decoded deferred effects;
* channel sharing backed by a ``Player`` object;
* streaming music load/queue/stop.
"""

import logging


class SoundEffect:
    """Decode-free stand-in for a sound effect.

    ``play()`` always returns ``None`` because there is no mixer, and
    ``loaded``/``load()`` exist only so callers can keep their checks.
    """

    def __init__(self, source=None, path="", deferred=False):
        self.source = None
        self.path = path

    @property
    def loaded(self):
        """Always ``True``: a silent effect is trivially 'ready'."""
        return True

    def load(self):
        """No-op: nothing is decoded."""
        return None

    def play(self):
        """Always ``None``: no mixer channel exists."""
        return None

    def __repr__(self):
        return f"SoundEffect({self.path!r}, silent)"


class SoundChannel:
    """No-op mixer slot.  Every method returns ``None``."""

    def start(self, source=None):
        return None

    def set_volume(self, left, right=None):
        return None

    @property
    def busy(self):
        return False

    def stop(self):
        return None


class _Mixer:
    """Stub mixer; there are no channels, so nothing is ever played."""

    def play(self, source):
        return None

    def stop_all(self):
        return None


_MIXER = _Mixer()


def load_sound(path, deferred=False):
    """Return a silent effect for ``path``.

    No file is opened, decoded or verified.  ``deferred`` is accepted and
    ignored so existing call sites stay valid.
    """
    return SoundEffect(None, path, deferred=deferred)


def preload_sounds(effects, name="sound-preloader"):
    """Disabled.  Audio is off, so there is nothing to preload."""
    return None


class MusicPlayer:
    """No-op replacement for the pyglet music player."""

    def __init__(self):
        self._volume = 1.0

    def load(self, path):
        return None

    def queue(self, path):
        return None

    def play(self):
        return None

    def stop(self):
        return None

    def set_volume(self, volume):
        try:
            self._volume = max(0.0, min(1.0, float(volume)))
        except (TypeError, ValueError):
            self._volume = 1.0
        return None

    def close(self):
        return None


def shutdown_audio():
    """Nothing to stop: no channels, player or driver were ever created."""
    logging.debug("Audio is disabled in this build; nothing to shut down")
    return None