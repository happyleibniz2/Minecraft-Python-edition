# pygame baseline

This file records the behavior of the game before the window/input/event/clock
host was migrated from `pygame` to `pyglet`.

> **Safety note:** the baseline run below was started before the operator's
> instruction "do not create any window or make any sound". The run was closed
> as soon as that instruction was received. No further game launches were made.
> Runtime verification of the migrated build is therefore **not performed** in
> this session; the migration is code-complete but runtime-unverified.

## Launch

Command:

```text
python minecraft_main_program.py
```

Working directory: repository root (all asset paths are relative to it).

The launcher `start.py` installs dependencies and then imports
`minecraft_main_program`; it was not used for the baseline because it also
runs `systeminfo` and a memory monitor.

## Window and display flags

Observed from the live process and from `minecraft_main_program.py`:

| Property | Value |
| --- | --- |
| Client size | **854 x 480** |
| Outer window size | 870 x 519 |
| Caption | `Minecraft 1 0.0` (the FPS suffix is 0.0 at the menu because `clock.tick` is only called in gameplay/menu loops that call it) |
| Resizable | yes |
| Display flags | `pygame.DOUBLEBUF \| pygame.OPENGL \| pygame.RESIZABLE` |
| Depth buffer | 24 bits |
| Multisampling | 4x requested (`GL_MULTISAMPLEBUFFERS=1`, `GL_MULTISAMPLESAMPLES=4`) with a no-MSAA fallback |
| VSync | requested with `set_mode(..., vsync=1)` |
| Fullscreen | toggled with F11 through `pygame._sdl2.Window.set_fullscreen(desktop=True)` |
| Close | SDL `WM_CLOSE` / `pygame.QUIT`; process exited with code 0 in the harness |

## OpenGL and GLSL

From the baseline log (`logs/2026-11-17_18-30-51.log`):

```text
PyOpenGL renderer: b'Intel(R) UHD Graphics 630'
PyOpenGL vendor:   b'Intel'
PyOpenGL GL version: b'4.6.0 - Build 27.20.100.8190'
Pygame display driver: windows
Pyglet version: 1.5.28
```

> The baseline was recorded before the pyglet upgrade. The project now pins
> `pyglet==2.1.19`; the context and shader requirements are unchanged.

The renderer uses a **compatibility** context: it calls fixed-function OpenGL
(`glMatrixMode`, `glBegin`, `glOrtho`, `gluPerspective`, ...) *and* compiles
GLSL shaders. The shader sources embedded in Python use:

| File | Line | Directive |
| --- | --- | --- |
| `game/Lighting/Light.py` | 13 | `#version 120` |
| `game/Lighting/Light.py` | 52 | `#version 120` |
| `game/world/Clouds.py` | 32 | `#version 330 core` |
| `game/world/Clouds.py` | 46 | `#version 330 core` |

The 4.6 compatibility context supports both. No shader files or GLSL versions
were changed by the migration.

## Frame time / FPS

**Not measured.** The baseline process was closed before a representative
world could be loaded, and the operator's no-window/no-sound instruction
prevents launching the migrated build for a comparison. The game uses a
variable timestep:

```python
dt = time.time() - last_time
last_time = current_time
if dt > 0.05:
    dt = 0.05
```

and caps frames with `pygame.time.Clock().tick(MAX_FPS)` where
`MAX_FPS = 2000`. The main menu does not call `clock.tick`, which is why the
caption showed `0.0` there.

## Screenshot

`docs/baseline_menu.png` was captured by a helper that foregrounded the
`Minecraft 1 0.0` window and grabbed its client rectangle. The resulting image
shows the OpenCode window instead of the game: Windows refused the foreground
switch and the grab used the target rectangle while another window was on top.
**There is no verified in-game screenshot.** The image is retained only as
evidence of the attempted capture, not as visual parity evidence.

## Input behavior (from code inspection)

The baseline game polls input inside a custom `while True` loop:

1. Compute `dt`, clamp it to 0.05 s.
2. `pygame.event.get()`.
3. Feed every event to `scene.touchControls.handle_event(event)`.
4. Handle mouse motion for camera look (`player.queue_look(*event.rel)`) when
   gameplay is active and the pointer is not at the window center.
5. Handle `QUIT`, `KEYDOWN`, `VIDEORESIZE`, `MOUSEBUTTONDOWN`.
6. Update gameplay left-mouse state with `pygame.mouse.get_pressed(3)[0]`.
7. Set mouse grab/visibility.
8. Update/render the menu or scene.
9. `pygame.display.flip()` and `clock.tick(MAX_FPS)`.

Bindings in the baseline:

| Input | Action |
| --- | --- |
| W / A / S / D | forward / left / back / right (polled) |
| Space | jump / swim up (polled) |
| Left Shift | sneak / swim down (polled) |
| Left Ctrl | sprint (polled) |
| Mouse motion | camera look, sensitivity `MOUSE_SENSITIVITY = 0.5` |
| Left mouse | break/attack (held) |
| Middle mouse | pick block |
| Right mouse | place/use |
| Wheel up/down | previous/next hotbar slot |
| 1-9 | select hotbar slot |
| E | inventory |
| Escape | pause |
| F3 | debug info |
| F3 + B | toggle hitboxes |
| F5 | cycle camera type |
| F10 | toggle touch controls |
| F11 | toggle fullscreen |
| T | command input |
| Q | drop item (Ctrl+Q drops the stack) |
| Z / C / V | spawn random entity / cow / sheep |
| P | toggle spectator |
| L | give debug items |

Text input (`Editarea`) used `pygame.key.get_pressed()` for Shift and numeric
`KEYDOWN` keycodes. The command input path passed `pygame.key.get_pressed()`
(a boolean sequence) to `Editarea.update`, so it did not receive keycodes; the
migration passes the per-frame key-symbol list instead, restoring the intended
text entry. This is the one intentional input-behavior correction.

## Audio, fonts, images

* **Audio:** `pygame.mixer.pre_init(44100, 16, 2, 4096)` was called before
  display creation. All SFX were loaded with `pygame.mixer.Sound`; music was
  loaded/queued through `pygame.mixer.music`. The baseline log confirms all
  step, dig, explode, damage, GUI and music files loaded. No playback was
  verified. `SoundPhysics` applies distance gain and per-ear stereo pan through
  `channel.set_volume(left, right)`.
* **Fonts:** already `pyglet.font` (`gui/main.ttf`, `gui/MinecraftAE.ttf`,
  `pyglet.text.Label`). No `pygame.font` usage.
* **Images:** already `pyglet.resource.image` / `pyglet.image`. No
  `pygame.image.load` usage.
* **Surfaces/draw/transform:** no active `pygame.Surface`, `pygame.draw`,
  `pygame.transform`, `pygame.display.update`, or partial-update usage.
* **Touch:** `TouchControls` consumed raw `pygame.FINGER*` events and SDL's
  touch-to-mouse events. pyglet 2.x on Windows exposes no raw finger events;
  the migrated touch mode is mouse-driven and must be enabled manually (F10 or
  `TOUCH_MODE=True`).

## Close behavior

The baseline harness sent `WM_CLOSE` to the window; the game exited with code
0. No traceback was written to stdout or the log. This is the expected
`pygame.QUIT` path.
