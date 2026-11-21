# pygame → pyglet migration map

This is the complete inventory of active `pygame` usage in the repository
before the host migration. Line numbers refer to the files at the time of the
baseline. Logs and `__pycache__` are excluded.

## Summary

| Category | Present? | Notes |
| --- | --- | --- |
| Window/display creation | **yes** | `set_mode`, `_sdl2.Window`, caption, fullscreen, resize |
| OpenGL context | **yes** | created by `pygame.display.set_mode(..., OPENGL)` |
| Event pump | **yes** | `pygame.event.get()` in the custom loop |
| Keyboard input | **yes** | polled state, key constants, modifiers, text keycodes |
| Mouse input | **yes** | position, buttons, relative motion, grab, focus, wheel |
| Clock/timing | **yes** | `pygame.time.Clock` |
| Image loading | no | already `pyglet.resource.image` / `pyglet.image` |
| Audio | **removed** | `pygame.mixer.Sound`, `pygame.mixer.music`, pre_init |
| Font/text | no | already `pyglet.font` / `pyglet.text` |
| Surface/draw/transform | no | no active usage |
| Clipboard/cursor/icon | cursor only | `pygame.mouse.set_visible`; no clipboard/icon |
| Other | **yes** | debug logging, unused imports, launcher/docs |

No `pygame.Surface`, `pygame.draw`, `pygame.transform`, `pygame.image.load`,
`pygame.font`, `pygame.display.update`, or partial-update code exists in the
active runtime. Audio is **disabled on purpose**: the target environment
restricts audio, so `pyglet.media` is never imported and `game/sound/*` is a
set of silent no-op classes with the same public surface as the old pygame
code (see "Audio" below).

## Inventory

### `minecraft_main_program.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 10 | `import pygame.time` | Clock/timing | remove; use `game.frame_clock.FrameClock` | Low |
| 12 | `from pygame._sdl2 import Window as SDLWindow` | Window/display creation | `pyglet.window.Window` owned by `game.host.PygletHost` | Medium |
| 48 | `pygame.display.gl_set_attribute(GL_DEPTH_SIZE, 24)` | OpenGL context | `pyglet.gl.Config(depth_size=24)` | Medium |
| 52-53 | `GL_MULTISAMPLEBUFFERS=1`, `GL_MULTISAMPLESAMPLES=4` | OpenGL context | `pyglet.gl.Config(sample_buffers=1, samples=4)` with no-MSAA fallback | Medium |
| 55, 63 | `pygame.display.set_mode(size, flags, vsync=1)` | Window/display creation | `pyglet.window.Window(..., resizable=True, vsync=True, config=...)` | Medium |
| 56 | `except pygame.error` | Window/display creation | catch `pyglet.window.NoSuchConfigException` / `pyglet.gl.ConfigException` | Medium |
| 60-61 | reset MSAA attributes | OpenGL context | fallback `Config(double_buffer=True, depth_size=24)` | Medium |
| 137, 263, 317, 374, 393, 411, 459, 511, 561, 605, 993 | `pygame.display.flip()` | Window/display creation (buffer flip) | `host.flip()` → `pyglet.window.Window.flip()` | Low |
| 258, 293, 327, 382, 401, 479, 523 | `pygame.mouse.get_pos()` | Mouse input | `host.mouse_pos` (tracked from `on_mouse_motion`/`on_mouse_drag`) | Low |
| 259 | `pygame.key.get_pressed()` | Keyboard input | `host.key_down(symbol)` / per-frame `keys` list | Medium (this call was the wrong type for `Editarea`; see 335) |
| 571-574 | `pygame.version`, `pygame.get_array_interface`, `pygame.display.get_driver/Info` | Other (diagnostics) | replace with pyglet/PyOpenGL diagnostics or remove | Low |
| 590 | `pygame.mixer.pre_init(44100, 16, 2, 4096)` | Audio | remove; audio is disabled, no mixer is initialised | Low |
| 592 | `pygame.DOUBLEBUF \| pygame.OPENGL \| pygame.RESIZABLE` | Window/display creation | `Config(double_buffer=True, depth_size=24)` + `resizable=True` | Medium |
| 634 | `pygame.mixer.Sound("sounds/pick.mp3")` | Audio | silent stub: `game.sound.audio.load_sound(...)` | Low |
| 643 | `pygame.mixer.Sound("sounds/step/" + i)` | Audio | silent stub: `load_sound(...)` | Low |
| 653 | `pygame.mixer.Sound("sounds/dig/" + i)` | Audio | silent stub: `load_sound(...)` | Low |
| 661 | `pygame.mixer.Sound("sounds/explode/" + i)` | Audio | silent stub: `load_sound(...)` | Low |
| 671 | `pygame.mixer.Sound("sounds/damage/" + i)` | Audio | silent stub: `load_sound(...)` | Low |
| 681 | `pygame.mixer.Sound("sounds/gui/" + i)` | Audio | silent stub: `load_sound(...)` | Low |
| 819 | `pygame.display.set_caption(...)` | Window/display creation | `host.set_caption(...)` | Low |
| 823 | `pygame.event.get()` | Event pump | `host.pump()` → `Window.dispatch_events()` + handler objects | High (ordering) |
| 828 | `event.type == pygame.MOUSEMOTION` | Event pump / Mouse input | `on_mouse_motion` + `on_mouse_drag` | Medium |
| 840 | `event.type == pygame.QUIT` | Event pump | `on_close` sets `host.closed`; loop exits and closes | Medium |
| 842, 867 | `event.type == pygame.KEYDOWN` | Event pump / Keyboard input | `on_key_press(symbol, modifiers)` | Medium |
| 844 | `pygame.K_F11` | Keyboard input | `pyglet.window.key.F11` | Low |
| 856 | `pygame.K_F10` | Keyboard input | `key.F10` | Low |
| 858 | `event.type == pygame.VIDEORESIZE` | Event pump | `on_resize(width, height)` → `host.resized` | Medium |
| 863, 912 | `event.type == pygame.MOUSEBUTTONDOWN` | Event pump / Mouse input | `on_mouse_press(x, y, button, modifiers)` | Medium |
| 864, 914 | `event.button` | Mouse input | explicit map: pyglet `mouse.LEFT=1`, `MIDDLE=2`, `RIGHT=4` → game buttons 1/2/3 | High (constants differ) |
| 868 | `pygame.K_ESCAPE` | Keyboard input | `key.ESCAPE` | Low |
| 870 | `pygame.K_e` | Keyboard input | `key.E` | Low |
| 872-888 | `pygame.K_1` … `pygame.K_9` | Keyboard input | `key._1` … `key._9` | Low |
| 890 | `pygame.K_F3` | Keyboard input | `key.F3` | Low |
| 892 | `pygame.key.get_pressed()[pygame.K_F3]` | Keyboard input | `host.key_down(key.F3)` | Low |
| 894 | `pygame.K_t` | Keyboard input | `key.T` | Low |
| 896 | `pygame.K_F5` | Keyboard input | `key.F5` | Low |
| 900 | `pygame.K_z` | Keyboard input | `key.Z` | Low |
| 902 | `pygame.K_c` | Keyboard input | `key.C` | Low |
| 904 | `pygame.K_v` | Keyboard input | `key.V` | Low |
| 906 | `pygame.K_p` | Keyboard input | `key.P` | Low |
| 908 | `pygame.K_l` | Keyboard input | `key.L` | Low |
| 910 | `pygame.K_q` | Keyboard input | `key.Q` | Low |
| 911 | `event.mod & pygame.KMOD_CTRL` | Keyboard input (modifiers) | `modifiers & key.MOD_CTRL` | Low |
| 915-926 | wheel buttons `4`/`5` | Mouse input | `on_mouse_scroll(x, y, scroll_x, scroll_y)`; `scroll_y > 0` = previous, `< 0` = next | Medium |
| 932 | `pygame.mouse.get_pressed(3)[0]` | Mouse input | `host.mouse_buttons[0]` | Low |
| 950 | `pygame.mouse.get_focused()` | Mouse input (focus) | `host.focused` from `on_activate`/`on_deactivate` | Medium |
| 951 | `pygame.event.set_grab(grab_mouse)` | Mouse input | `host.set_exclusive_mouse(grab_mouse)` | High (relative mode) |
| 956, 958 | `pygame.mouse.set_visible(...)` | Clipboard/cursor/icon | `host.set_mouse_visible(...)` | Low |
| 970 | `pygame.mouse.set_pos((WIDTH//2, HEIGHT//2))` | Mouse input | omit; pyglet exclusive mouse uses raw deltas and does not need recentering | Medium |
| 994 | `clock.tick(MAX_FPS)` | Clock/timing | `FrameClock.tick(MAX_FPS)` (monotonic, same 2000 FPS cap) | Low |

### `settings.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 3 | `import pygame` | Other | remove | Low |
| 27 | `pygame.init()` | Other (global init) | remove; pyglet initializes its display/audio lazily | Low |
| 140 | `monitor = pygame.display.Info()` | Window/display creation | remove; value was unused | Low |
| 149 | `clock = pygame.time.Clock()` | Clock/timing | `clock = game.frame_clock.FrameClock()` | Low |

### `game/entity/Player.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 44 | comment referencing `pygame.key.get_pressed()` | Other | update comment | Low |
| 147 | `pygame.key.get_pressed()` | Keyboard input | `self.gl.host.key_down(symbol)` | Medium |
| 150-151 | `pygame.K_w/K_s/K_d/K_a` | Keyboard input | `key.W`, `key.S`, `key.D`, `key.A` | Low |
| 162 | `pygame.K_SPACE` | Keyboard input | `key.SPACE` | Low |
| 163 | `pygame.K_LSHIFT` | Keyboard input | `key.LSHIFT` | Low |
| 164 | `pygame.K_LCTRL` | Keyboard input | `key.LCTRL` | Low |

### `game/GUI/ModalWindow.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 1 | `import pygame` | Other | remove | Low |
| 50 | `pygame.mouse.get_pos()` | Mouse input | `self.gl.host.mouse_pos` | Low |
| 51 | `pygame.mouse.get_pressed(3)` | Mouse input | `self.gl.host.mouse_buttons` | Low |
| 74 | `pygame.key.get_pressed()` | Keyboard input | `self.gl.host.key_down(...)` | Low |
| 75 | `pygame.K_ESCAPE` | Keyboard input | `pyglet.window.key.ESCAPE` | Low |

### `game/GUI/Sliderbox.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 31, 38 | `pygame.mouse.get_pressed(3)[0]` | Mouse input | `self.gl.host.mouse_buttons[0]` | Low |

### `game/GUI/Editarea.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 29 | `pygame.key.get_pressed()[pygame.K_LSHIFT]` | Keyboard input | `self.gl.host.key_down(key.LSHIFT)` / `key.RSHIFT` | Low |
| 32 | numeric `8` (Backspace) | Keyboard input | `key.BACKSPACE` | Medium (numeric keycodes differ) |
| 34 | numeric `13`/`27` (Enter/Escape) | Keyboard input | `key.ENTER` / `key.ESCAPE` | Medium |
| 38 | numeric `1073742049`/`1073742053` (Shift) | Keyboard input | `key.LSHIFT` / `key.RSHIFT` | Medium |
| 42 | `chr(i)` for keycodes | Keyboard input (text) | `chr(symbol)` for printable ASCII only; map `key.TAB` explicitly | Medium |

### `game/TouchControls.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 3, 14, 108, 118, 302 | docstrings/comments referencing pygame | Other | update comments | Low |
| 22 | `import pygame` | Other | remove; import `pyglet.window.key/mouse` | Low |
| 126, 139, 146 | `pygame.FINGERDOWN/MOTION/UP` | Event pump / Mouse input | **not available in pyglet 2.x on Windows**; replace with mouse-driven touch methods | **High** |
| 156-157 | `pygame.MOUSEBUTTONDOWN/UP`, `pygame.MOUSEMOTION` | Event pump / Mouse input | `on_mouse_press/release/motion/drag` | Medium |
| 165, 169 | `event.button == 1` | Mouse input | `button == mouse.LEFT` | Low |
| 418, 434, 498 | `pygame.K_SPACE` | Keyboard input | `key.SPACE` | Low |
| 468-471 | `pygame.K_w/K_s/K_d/K_a` | Keyboard input | `key.W`, `key.S`, `key.D`, `key.A` | Low |
| 480-481 | `pygame.event.post(pygame.event.Event(KEYDOWN/KEYUP, ...))` | Event pump | `host.dispatch_synthetic_key(symbol, pressed)` | Medium |
| 491 | `except pygame.error` | Other | remove; pyglet dispatch does not raise for this path | Low |

### `game/sound/*.py` (audio disabled)

The whole subsystem is kept for API compatibility but everything is a no-op,
because the target environment restricts audio and `pyglet.media` must not be
imported.

| Line | Pygame API | Category | Final replacement | Risk |
| --- | --- | --- | --- | --- |
| Sound 3 | `import pygame` | Other | remove | Low |
| Sound 16, 23 | `pygame.mixer.music` | Audio | `game.sound.audio.MusicPlayer`, a no-op stub | Low |
| Sound 42 | docstring "pygame returning no free channel" | Other | update docstring | Low |
| audio | `pygame.mixer.Sound` | Audio | `game.sound.audio.SoundEffect`: `play()` returns `None`, `load()` decodes nothing | Low |
| BlockSound | per-block `pygame.mixer.Sound` lookups | Audio | kept unchanged: it still selects a random table entry, but the entry is silent | Low |
| SoundPhysics 1 | docstring "Pygame's stereo mixer" | Other | kept; `apply()` short-circuits on the `None` channel a muted mixer returns | Low |

### `functions.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 5 | `import pygame.display` | Other (unused) | remove | Low |

### `game/entity/Inventory.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 6 | `import pygame` | Other (unused) | remove | Low |

### `start.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 20 | `pip install ... pygame ...` | Other (launcher/dependency) | remove `pygame` from the install list | Low |
| 23-24 | "already installed pygame" message | Other (launcher) | remove | Low |

### `README.md`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 205 | `pygame==2.0.1` requirement block | Other (docs) | remove | Low |
| 224 | manual `pip install ... pygame==2.0.1` | Other (docs) | remove `pygame` | Low |

### `game/world/gen_worker.py`

| Line | Pygame API | Category | Proposed pyglet replacement | Risk |
| --- | --- | --- | --- | --- |
| 4 | comment "settings (which initialises pygame)" | Other | update comment | Low |

## Migration plan

### Phase 0 — Baseline

Completed before the operator's no-window/no-sound instruction:
window size, flags, GL version, GLSL directives, close behavior and audio
loading were recorded in `docs/pygame-baseline.md`. FPS and a verified in-game
screenshot were not obtained.

### Phase 1 — Inventory

This document. No coding was done before the inventory was complete.

### Phase 2 — Pyglet host module

Create `game/host.py` with a thin `PygletHost` that owns exactly one
`pyglet.window.Window` and its GL context. It provides:

* window creation with a `pyglet.gl.Config` matching 854x480, resizable,
  double-buffered, 24-bit depth, 4x MSAA (fallback to no MSAA), VSync;
* `pump()` → `Window.dispatch_events()`;
* `flip()` → `Window.flip()`;
* maintained keyboard state (`keys_down`, `key_down()`);
* maintained mouse position/buttons (`mouse_pos`, `mouse_buttons`);
* exclusive mouse (`set_exclusive_mouse`) and cursor visibility;
* `on_resize`/`on_close`/focus tracking;
* `set_caption`, `set_fullscreen`;
* synthetic key dispatch for mods;
* `close()` that destroys the window/context and stops the platform event loop.

Create `game/frame_clock.py` with a monotonic `FrameClock` replacing
`pygame.time.Clock`. It preserves the 2000 FPS cap and the
`get_fps()`-in-caption behavior (0.0 until the first `tick`).

### Phase 3 — Entry point migration

Replace `create_opengl_display` with host creation. Keep the manual loop and
the existing order: pump events → update input state → update game state →
render → flip. Do not use `pyglet.app.run()`; that would introduce a second
update path.

### Phase 4 — Input migration

Map each category explicitly:

* keyboard symbols: `pygame.K_*` → `pyglet.window.key.*`;
* modifiers: `pygame.KMOD_CTRL` → `key.MOD_CTRL`;
* mouse position: tracked `on_mouse_motion` / `on_mouse_drag`;
* relative motion: `on_mouse_motion`/`on_mouse_drag` `dx,dy` queued into
  `Player.queue_look`;
* mouse buttons: `mouse.LEFT=1`, `mouse.MIDDLE=2`, `mouse.RIGHT=4` mapped to
  the game's 1/2/3;
* wheel: `on_mouse_scroll` mapped to the old hotbar cycling;
* grab: `set_exclusive_mouse`;
* cursor: `set_mouse_visible`;
* focus loss: `on_deactivate` clears held keys/buttons and `host.focused`
  disables grab;
* text input: printable ASCII only, Shift from host state, Enter/Escape/
  Backspace mapped explicitly.

### Phase 5 — Clock migration

Use `FrameClock` with `time.perf_counter()`. Preserve the variable timestep and
the `dt > 0.05` clamp. Do not introduce a fixed timestep.

### Phase 6 — Non-window pygame usage

* Audio: **removed, not migrated.**  The target environment blocks audio.  None
  of `pyglet.media` is imported anywhere; `game/sound/*.py` becomes silent
  no-op classes (`SoundEffect`, `SoundChannel`, `MusicPlayer`, `ShutdownAudio`)
  so all gameplay call sites keep working.  This also removes the whole
  WMF-decoding cost from startup — see the freeze regression below.
* Images/fonts: already pyglet; no change.
* Surface/draw/transform: none.

### Phase 7 — Remove pygame

After the code path is reviewed, remove all active `pygame` imports, remove
`pygame` from `requirements.txt`, `start.py` and `README.md`, and update
comments/docstrings. Do not delete assets.

## Startup freeze regression (2026-11-18)

### Symptom

The logo window stopped responding for tens of seconds, and the run log ended
at `Init Scene class...`.  The log was not the freeze location: `Scene.__init__`
only logged its first line, so every later step was invisible.

### Root cause

Startup decoded all 107 sound effects synchronously with
`pyglet.media.load(..., streaming=False)`.  On the baseline Windows machine
each OGG went through Windows Media Foundation and cost roughly 150 ms, for
about 17.7 s total.  `pyglet.options['audio'] = ('silent',)` only disables
playback; it does not skip decoding.  The main thread could not pump window
events during that time, so Windows marked the logo window as not responding.
A second hitch came from the first menu frame: `drawInfoLabel` assigned
`Label.text` every frame, which reruns pyglet 2.x's DirectWrite layout even
when the string is unchanged.

### Fix (history), then final state

Two fixes landed in order; the second one made the first one unnecessary.

1. **Deferred decoding (intermediate).**  `game/sound/audio.py` gained
   `load_sound(path, deferred=True)` plus `preload_sounds()`, which decoded on a
   daemon thread after calling `CoInitializeEx` on Windows (WMF needs COM per
   thread).  `SoundEffect.play()` returned `None` until the effect was ready, so
   gameplay never blocked on the decoder.  This cut startup to ~3 s and the
   background preload finished in ~20-25 s while the window stayed responsive.
2. **Audio removed (final).**  The target environment blocks audio, so the
   whole decode path was deleted instead of optimised: `pyglet.media` is no
   longer imported anywhere, `game/sound/*.py` is silent no-op classes, and
   startup only *registers* filenames.  With nothing to decode there is nothing
   left to freeze on.

Two smaller changes are still in place and matter on their own:

* Startup instrumentation: `Scene`, `GUI` and the main program now log every
  step (clouds, world generator, textures, panorama, cube handler, lighting,
  each sound-table registration, first-frame duration), so a future hang can be
  located from the log instead of ending invisibly at `Init Scene class...`.
* `functions._sync_info_label` only writes `text`, `font_size`, position and
  anchors when they change, and `drawInfoLabel` caches the style tuple.  pyglet
  2.x reruns the DirectWrite layout whenever `Label.text` is assigned, even for
  an identical string; the menu redraws those labels every frame, so this cut
  the first menu frame from several seconds to ~0.1-0.4 s.

### Measured verification

Environment: Windows 10, Python 3.12.0, pyglet 2.1.19, PyOpenGL 3.1.10,
Intel UHD Graphics 630, **no audio driver involved at all**.

* Synchronous decode benchmark (before removal): 107 files in 17.7 s, per file
  130-290 ms; `pyglet.resource` import of the bank was the entire startup cost.
* Startup to `Loading complete!`: **2.88 s**.  The old code did not reach this
  point within the 16 s controlled smoke-test window.
* First menu frame: **0.11 s** after the label-relayout guard.
* `pyglet.media` never enters `sys.modules`, verified by a zero-window import
  check that imports every game module and asserts no window is created.
* Live windowed smoke tests: Windows reported the window responsive at
  3.6/7.2/10.8 s, and no crash.
* Regression suite: 52 tests pass, including a scan that fails if any source
  file mentions `pyglet.media` or imports pyglet without the `shadow_window`
  guard set first.

Note: pyglet's periodic `faulthandler.dump_traceback_later()` crashes this
process with `0xC0000005` while the main thread is inside DirectWrite/OpenGL
on this machine.  The crash reproduces with the sound preloader disabled, so
it is a diagnostic-tool artifact rather than the game.  Use a Python-level
`sys._current_frames()` dump for long-running smoke tests instead.

## Known risks / limitations

1. **Raw touch events:** pyglet 2.x exposes no `on_touch_*` events on
   Windows. Touch mode becomes mouse-driven and must be enabled with F10 or
   `TOUCH_MODE=True`; multi-touch is limited to the primary pointer. This is a
   real feature limitation, not a stub.
2. **Audio:** disabled on purpose. The target environment restricts audio, so
   `pyglet.media` is never imported and no sound effect or music track is
   loaded, decoded or played. `game/sound/*.py` keeps the old class and method
   surface as silent no-ops: `SoundEffect.play()` returns `None`,
   `MusicPlayer.load/queue/play/stop` do nothing, and `SoundPhysics.apply()`
   short-circuits on the `None` channel. Gameplay logic (damage, random sound
   selection, pickup cooldowns) is unchanged; it just cannot be heard. There is
   no panning to approximate, so the old stereo-panning limitation is gone
   rather than hidden.
3. **OpenGL context version:** `pyglet.options['shadow_window'] = False`
   prevents pyglet 2.x from creating a hidden context. With a version-less
   `Config`, the first window uses the legacy PFD/`wglCreateContext` path,
   which exposes the driver's compatibility profile (4.6 on the baseline
   machine). That path cannot request multisampling, so MSAA is best-effort
   and AA is disabled when `host.msaa_samples == 0`. `settings.py` and
   `functions.py` also set the option before importing `pyglet.font`/`gl`,
   so importing either module on its own cannot create a shadow context.
   Unverified without a window.
4. **pyglet 2.x graphics:** `pyglet.graphics.vertex_list` and `Batch.add`
   were removed in 2.x, and its batch shader ignores fixed-function matrices.
   `game/graphics.py` now provides fixed-function client-array vertex lists
   and a disposable batch, including the lighting shader's generic
   `swayWeight` attribute.
5. **Text and image blits:** pyglet 2.x `TextLayout.draw` and
   `Texture.blit` are shader-based and use the window's projection/view
   uniforms. `game/graphics.py` installs fixed-function shims for both:
   text copies the current GL matrices into the shared `WindowBlock`, and
   texture blits draw an immediate-mode quad. This keeps UI icons, labels,
   rotation/scale, and the held item aligned with the fixed-function
   renderer, and avoids pyglet's throwaway VAO/VBO per blit.
6. **Texture state:** pyglet 2.x `TextureGroup.set_state` selects unit 0 and
   binds the texture, but no longer enables the texture target.
   `DisposableBatch.draw` binds first and then enables the group's target, and
   the celestial-sky, water-overlay and cloud paths select unit 0 and enable
   `GL_TEXTURE_2D` explicitly. The blit shim preserves pyglet 1.5's
   `GL_ENABLE_BIT` push/pop contract so UI blits cannot leak state.
7. **Event ordering:** the host attaches handlers in the order touch → host
   state → game handler so the old "touch first, then normal handling" order is
   preserved while key state is updated before the game handler reads it.
8. **Runtime verification:** controlled startup smoke tests now cover the logo
   screen, main-menu entry and window responsiveness with no audio at all
   (audio is removed, not merely muted). Visual parity, input feel and
   steady-state frame time still require an interactive session; MSAA reports
   0 samples on the legacy PFD path. Because audio is disabled, audio parity is
   out of scope rather than unverified.
