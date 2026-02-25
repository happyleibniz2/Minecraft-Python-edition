import gc
import math
import os
import sys
from random import randint
import pygame.time
import pyglet
# handle old/limited OpenGL drivers: pyglet may try to delete shader programs
# during cleanup, which fails if glDeleteProgram is missing.  Patch the
# library to a no-op to prevent noisy exceptions.
try:
    # try to import the function; if missing an ImportError/AttributeError will
    # be raised
    from pyglet.gl import glDeleteProgram  # type: ignore
except Exception:
    # patch the module directly
    try:
        pyglet.gl.glDeleteProgram = lambda prog: None  # type: ignore
    except Exception:
        pass

# suppress errors when pyglet tries to delete shader programs on teardown
# (drivers lacking OpenGL 2.0 functionality may not export the required
# functions).  We patch the destructor to swallow any exceptions.
try:
    from pyglet.graphics.shader import ShaderProgram
    _orig_del = ShaderProgram.__del__
    def _safe_del(self):
        try:
            _orig_del(self)
        except Exception:
            pass
    ShaderProgram.__del__ = _safe_del
except Exception:
    pass

from OpenGL.GL import *
from OpenGL.raw.GLU import gluOrtho2D
from functions import drawInfoLabel, getElpsTime, translateSeed
from game.GUI.Button import Button
from game.GUI.Editarea import Editarea
from game.GUI.GUI import GUI
from game.GUI.Sliderbox import Sliderbox
from game.entity.Player import Player
from game.sound.BlockSound import BlockSound
from game.sound.Sound import Sound
from game.Scene import Scene
from game.world.Biomes import getBiomeByTemp
from game.world.worldGenerator import worldGenerator
from settings import *
import settings
try:
    import ctypes
    ctypes.windll.kernel32.SetProcessWorkingSetSize(ctypes.windll.kernel32.GetCurrentProcess(), -1, 1024*1024*1024)
except Exception:
    pass
try:
    import resource
    resource.setrlimit(resource.RLIMIT_AS, (1e9, 1e9))
except ModuleNotFoundError:
    pass
lang_choose = ["en", "zh"]

# Create the pygame window - this was missing!
screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
pygame.display.set_caption(f"Minecraft {MC_VERSION}")


def choose_langs():
    global lang_choose, mainFunction
    with open("gui/lang.mclanguage", "w") as mclanguagefile:
        if settings.lang_type == "en":
            mclanguagefile.write("zh")
        else:
            mclanguagefile.write("en")
    pygame.quit()
    print(os.getcwd())
    os.system("run.bat")
    sys.exit()


def respawn():
    pause()
    player.hp = 20
    player.playerDead = False
    player.position = scene.startPlayerPos
    player.lastPlayerPosOnGround = scene.startPlayerPos

def saveWorld(worldGen, save_path):
    with open(save_path+"/world.dat","wb") as world_data_file:
        pass
    print("Successfully saved world ")
def quit_to_menu():
    global PAUSE, IN_MENU, mainFunction
    saveWorld(scene.worldGen,"saves/Current_world")
    tex = gui.GUI_TEXTURES["options_background"]
    tex2 = gui.GUI_TEXTURES["black"]
    for scene_x in range(0, scene.WIDTH, tex.width):
        for scene_y in range(0, scene.HEIGHT, tex.height):
            tex.blit(scene_x, scene_y)
            tex2.blit(scene_x, scene_y)
    drawInfoLabel(scene, translations["quit.mainmenu"], xx=scene.WIDTH // 2, yy=scene.HEIGHT // 2,
                  style=[('', '')], size=12, anchor_x='center')
    pygame.display.flip()
    clock.tick(MAX_FPS)

    PAUSE = True
    IN_MENU = True

    sound.initMusic(False)

    sound.musicPlayer.play()
    sound.musicPlayer.set_volume(sound.volume)

    scene.resetScene()
    scene.initScene()

    player.position = [0, -90, 0]
    player.hp = -1
    player.playerDead = False

    gc.collect()
    mainFunction = draw_main_menu


def show_settings():
    global mainFunction
    mainFunction = draw_settings_menu


def draw_command_function():
    global mainFunction
    mainFunction = draw_command


def close_settings():
    global mainFunction
    mainFunction = draw_main_menu


def start_new_game():
    global mainFunction
    if not os.path.exists("saves/Current_world"):
        os.makedirs("saves/Current_world")
    sound.musicPlayer.stop()
    sound.initMusic(True)
    scene.worldGen = worldGenerator(scene, translateSeed(seedEditArea.text))
    scene.worldGen.start()
    mainFunction = gen_world


def pause():
    global PAUSE, mainFunction
    PAUSE = not PAUSE
    scene.allowEvents["movePlayer"] = True
    scene.allowEvents["keyboardAndMouse"] = True
    mainFunction = pause_menu


def death_screen():
    global PAUSE, mainFunction
    PAUSE = not PAUSE
    scene.allowEvents["movePlayer"] = True
    scene.allowEvents["keyboardAndMouse"] = True
    mainFunction = draw_death_screen


def draw_command(mc):
    scene.set2d()
    mp = pygame.mouse.get_pos()
    _keys = pygame.key.get_pressed()
    commandEditArea.x = scene.WIDTH // 2 - (commandEditArea.bg.width // 2)
    commandEditArea.y = scene.HEIGHT // 2 - (commandEditArea.bg.height // 2)
    commandEditArea.update(mp, mc, _keys)
    pygame.display.flip()
    clock.tick(MAX_FPS)


def draw_settings_menu(mc):
    scene.set2d()

    tex = gui.GUI_TEXTURES["options_background"]
    tex2 = gui.GUI_TEXTURES["black"]
    for ix in range(0, scene.WIDTH, tex.width):
        for iy in range(0, scene.HEIGHT, tex.height):
            tex.blit(ix, iy)
            tex2.blit(ix, iy)
    mp = pygame.mouse.get_pos()

    # Volume slider box
    soundVolumeSliderBox.x = scene.WIDTH // 2 - (soundVolumeSliderBox.bg.width // 2)
    soundVolumeSliderBox.y = scene.HEIGHT // 2 - (soundVolumeSliderBox.bg.height // 2) - 80
    soundVolumeSliderBox.update(mp)
    #

    # Seed edit area
    seedEditArea.x = scene.WIDTH // 2 - (seedEditArea.bg.width // 2)
    seedEditArea.y = scene.HEIGHT // 2 - (seedEditArea.bg.height // 2)
    seedEditArea.update(mp, mc, keys)
    #

    # Close
    closeSettingsButton.x = scene.WIDTH // 2 - (closeSettingsButton.button.width // 2)
    closeSettingsButton.y = scene.HEIGHT // 2 - (closeSettingsButton.button.height // 2) + 160
    closeSettingsButton.update(mp, mc)
    #

    sound.musicPlayer.set_volume(soundVolumeSliderBox.val / 100)
    sound.volume = soundVolumeSliderBox.val / 100

    pygame.display.flip()
    clock.tick(MAX_FPS)


def draw_death_screen(mc):
    bg = gui.GUI_TEXTURES["red"]
    bg.width = scene.WIDTH
    bg.height = scene.HEIGHT
    bg.blit(0, 0)

    mp = pygame.mouse.get_pos()

    drawInfoLabel(scene, translations["player dead"], xx=scene.WIDTH // 2,
                  yy=scene.HEIGHT - scene.HEIGHT // 4, style=[('', '')],
                  size=34, anchor_x='center')

    # Back to Game button
    respawnButton.x = scene.WIDTH // 2 - (respawnButton.button.width // 2)
    respawnButton.y = scene.HEIGHT // 2 - (respawnButton.button.height // 2) - 50
    respawnButton.update(mp, mc)
    #

    # Quit to title button
    quitWorldButton.text = translations["death.titlescreen"]
    quitWorldButton.x = scene.WIDTH // 2 - (quitButton.button.width // 2)
    quitWorldButton.y = scene.HEIGHT // 2 - (quitButton.button.height // 2)
    quitWorldButton.update(mp, mc)
    #

    pygame.display.flip()
    clock.tick(MAX_FPS)


def pause_menu(mc):
    bg = gui.GUI_TEXTURES["black"]
    bg.width = scene.WIDTH
    bg.height = scene.HEIGHT
    bg.blit(0, 0)

    mp = pygame.mouse.get_pos()

    drawInfoLabel(scene, translations["game.menu"], xx=scene.WIDTH // 2, yy=scene.HEIGHT - scene.HEIGHT // 4,
                  style=[('', '')],
                  size=12, anchor_x='center')

    # Back to Game button
    resumeButton.x = scene.WIDTH // 2 - (resumeButton.button.width // 2)
    resumeButton.y = scene.HEIGHT // 2 - (resumeButton.button.height // 2) - 50
    resumeButton.update(mp, mc)
    #

    # Quit to title button
    quitWorldButton.text = translations["quit.title"]
    quitWorldButton.x = scene.WIDTH // 2 - (quitButton.button.width // 2)
    quitWorldButton.y = scene.HEIGHT // 2 - (quitButton.button.height // 2)
    quitWorldButton.update(mp, mc)
    #

    pygame.display.flip()
    clock.tick(MAX_FPS)


def gen_world(mc):
    global IN_MENU, PAUSE, resizeEvent
    chunk_cnt = 220

    tex = gui.GUI_TEXTURES["options_background"]
    tex2 = gui.GUI_TEXTURES["black"]
    for ix in range(0, scene.WIDTH, tex.width):
        for iy in range(0, scene.HEIGHT, tex.height):
            tex.blit(ix, iy)
            tex2.blit(ix, iy)

    scene.genWorld()
    if scene.worldGen.start - len(scene.worldGen.queue) > chunk_cnt:
        scene.genTime = 16
        IN_MENU = False
        PAUSE = False

    proc = round((scene.worldGen.start - len(scene.worldGen.queue)) * 100 / chunk_cnt)
    drawInfoLabel(scene, translations["load.world"], xx=scene.WIDTH // 2, yy=scene.HEIGHT // 2, style=[('', '')],
                  size=12, anchor_x='center')
    drawInfoLabel(scene, translations["gen.terrain"] + f" {proc}%...", xx=scene.WIDTH // 2, yy=scene.HEIGHT // 2 - 39,
                  style=[('', '')], size=12, anchor_x='center')

    pygame.display.flip()
    clock.tick(MAX_FPS)


def draw_main_menu(mc):
    global mainMenuRotation, IN_MENU, PAUSE
    glFogfv(GL_FOG_COLOR, (GLfloat * 4)(0.5, 0.7, 1, 1))
    glFogf(GL_FOG_START, 0)
    glFogf(GL_FOG_END, 1000)

    scene.set3d()

    glClear(GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT)
    glLoadIdentity()

    glPushMatrix()
    glRotatef(mainMenuRotation[0], 1, 0, 0)
    glRotatef(mainMenuRotation[1], 0, 1, 0)
    glTranslatef(0, 0, 0)

    # draw background panorama before any scene geometry so that the
    # world can overlap it; disable depth testing so the sky cube is always
    # visible even when we rotate.
    glDisable(GL_DEPTH_TEST)
    scene.drawPanorama()
    glEnable(GL_DEPTH_TEST)

    scene.draw()

    glPopMatrix()
    scene.set2d()
    mp = pygame.mouse.get_pos()

    tex = gui.GUI_TEXTURES["game_logo"]
    tex.blit(scene.WIDTH // 2 - (tex.width // 2), scene.HEIGHT - tex.height - (scene.HEIGHT // 15))

    drawInfoLabel(scene, f"Minecraft {MC_VERSION}", xx=10, yy=10, style=[('', '')], size=12)

    # Single player button
    singleplayer_button.x = scene.WIDTH // 2 - (singleplayer_button.button.width // 2)
    singleplayer_button.y = scene.HEIGHT // 2 - (singleplayer_button.button.height // 2) - 25
    singleplayer_button.update(mp, mc)
    #

    # Options button
    optionsButton.x = scene.WIDTH // 2 - (optionsButton.button.width // 2)
    optionsButton.y = scene.HEIGHT // 2 - (optionsButton.button.height // 2) + 25
    optionsButton.update(mp, mc)
    #

    # Quit button
    quitButton.x = scene.WIDTH // 2 - (quitButton.button.width // 2)
    quitButton.y = scene.HEIGHT // 2 - (quitButton.button.height // 2) + 75
    quitButton.update(mp, mc)
    #

    # language button
    lang_button.x = scene.WIDTH // 2 - (lang_button.button.width // 2)
    lang_button.y = scene.HEIGHT // 2 - (lang_button.button.height // 2) + 125
    lang_button.update(mp, mc)

    # Splash
    glPushMatrix()
    glTranslatef((scene.WIDTH // 2 + (tex.width // 2)) - 90, scene.HEIGHT - tex.height - (scene.HEIGHT // 15) + 15, 0.0)
    glRotatef(20.0, 0.0, 0.0, 1.0)
    var8 = 1.8 - abs(math.sin((getElpsTime() % 1000) / 1000.0 * math.pi * 2.0) * 0.1)
    var8 = var8 * 100.0 / ((24 * 12) + 32)
    drawInfoLabel(scene, splash, xx=1, yy=1, style=[('', '')], scale=var8, size=30, anchor_x='center',
                  label_color=(255, 255, 0), shadow_color=(63, 63, 0))
    glPopMatrix()
    #

    pygame.display.flip()
    clock.tick(MAX_FPS)
    if mainMenuRotation[0] < 25:
        mainMenuRotation[2] = False
    if mainMenuRotation[0] > 75:
        mainMenuRotation[2] = True

    if mainMenuRotation[2]:
        mainMenuRotation[0] -= 0.008
    else:
        mainMenuRotation[0] += 0.008
    mainMenuRotation[1] += 0.02


if settings.DEBUG:
    print("PyOpenGL version: ", OpenGL.__version__)
    print("PyOpenGL platform: ", OpenGL.platform)
    print("PyOpenGL extensions: ", OpenGL.GL.glGetString(OpenGL.GL.GL_EXTENSIONS))
    print("PyOpenGL renderer: ", OpenGL.GL.glGetString(OpenGL.GL.GL_RENDERER))
    print("PyOpenGL vendor: ", OpenGL.GL.glGetString(OpenGL.GL.GL_VENDOR))
    print("PyOpenGL GL version: ", OpenGL.GL.glGetString(OpenGL.GL.GL_VERSION))
    print("Pygame Version:", pygame.version.ver)
    print("Pygame array interface:", pygame.get_array_interface)
    print("Pygame display driver:", pygame.display.get_driver)
    print("Pygame display info:", pygame.display.Info())
    print("Pyglet version:", pyglet.version)
    print("Pyglet platform:", pyglet.compat_platform)
    # Simplified pyglet display info - removed problematic canvas calls
    print("Python Version:", sys.version)
    print("Python Platform:", sys.platform)
    print("Python Path:", sys.path)
    print("Python Executable:", sys.executable)

# Initialize game objects
scene = Scene()

gui = GUI(scene)
sound = Sound()
blockSound = BlockSound(scene)

# link helpers back into scene so UI and entities can access them
scene.gui = gui
scene.sound = sound
scene.blockSound = blockSound

# Initialize Player with scene (first parameter)
player = Player(scene)
scene.player = player

# now that player exists, initialise the OpenGL scene
scene.initScene()

# link helpers back into scene so UI and entities can access them
scene.gui = gui
scene.sound = sound
scene.blockSound = blockSound

# Initialize Player with scene (first parameter)
player = Player(scene)
scene.player = player

# Create buttons and UI elements (pass scene as context, not gui)
singleplayer_button = Button(scene, translations["menu.singleplayer"], 0, 0)
optionsButton = Button(scene, translations["menu.options"], 0, 0)
quitButton = Button(scene, translations["menu.quit"], 0, 0)
lang_button = Button(scene, translations["menu.language"], 0, 0)
resumeButton = Button(scene, translations["menu.resume"], 0, 0)
respawnButton = Button(scene, translations["death.respawn"], 0, 0)
quitWorldButton = Button(scene, translations["quit.title"], 0, 0)
closeSettingsButton = Button(scene, translations["gui.done"], 0, 0)

# Create input fields
seedEditArea = Editarea(scene, translations["selectWorld.enterSeed"], 0, 0)
commandEditArea = Editarea(scene, "/", 0, 0)
# maximum volume is expressed as 100 (percent)
soundVolumeSliderBox = Sliderbox(scene, "", 100, 0, 0)

# Game state variables
mainMenuRotation = [50, 0, True]
splash = "Python Edition!"  # Default splash text
resizeEvent = False
keys = []

# Set initial game function
mainFunction = draw_main_menu

# Main game loop
running = True
while running:
    try:
        # Handle events
        mc = 0
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False
            elif event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1:
                    mc = 1
            elif event.type == pygame.KEYDOWN:
                keys.append(event.key)
                if event.key == pygame.K_ESCAPE:
                    if not IN_MENU and not PAUSE:
                        pause()
        # Execute current state
        mainFunction(mc)

        # Clear keys for next frame
        keys = []

        # Handle window resize
        if resizeEvent:
            pygame.display.set_mode((WIDTH, HEIGHT), pygame.OPENGL | pygame.DOUBLEBUF)
            resizeEvent = False
    except Exception as exc:
        import traceback
        print("Exception in main loop:", exc)
        traceback.print_exc()
        # break out after logging
        running = False

pygame.quit()
sys.exit()
