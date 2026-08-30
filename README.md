# Minecraft Python Edition
<img width="1518" height="633" alt="image" src="https://github.com/user-attachments/assets/ffbcd271-5f2a-4176-b17f-d795d6011783" />

![Python](https://img.shields.io/badge/python-%233670A0.svg?style=for-the-badge&logo=python&logoColor=ffdd54)
![NumPy](https://img.shields.io/badge/numpy-%23013243.svg?style=for-the-badge&logo=numpy&logoColor=white)
![OpenGL](https://img.shields.io/badge/opengl-%235586A4.svg?style=for-the-badge&logo=opengl&logoColor=white) 
### Minecraft Python Edition is a Minecraft-inspired voxel game written in Python, using Pygame, PyOpenGL, Pyglet, and NumPy. The project focuses on experimenting with voxel rendering, procedural terrain generation, game physics, entities, and Minecraft-style gameplay systems.

## ✨Features
- Dirty chunk loading

- zombie mob

- cow mob

- sheep mob

- simple zombie ai

- Better water texture

- Better grass texture

- Water physics (sort of)

- Fast terrain generation

- Player mining

- Spectator mode(sort of)

- tnt explosion


## 📸In game screenshots
<img width="1274" height="754" alt="屏幕截图 2026-08-26 075310" src="https://github.com/user-attachments/assets/161883b2-27c2-4fb7-a7f4-bc6a62de4260" />
<img width="1271" height="760" alt="屏幕截图 2026-08-26 075317" src="https://github.com/user-attachments/assets/78d54698-4012-43ab-be1e-e27055eb6f0d" />

### Pre Classic 0.48

<img width="1265" height="754" alt="屏幕截图 2026-08-28 233745" src="https://github.com/user-attachments/assets/fa05e708-d431-4c6c-b606-9b2d4af8ae3f" />
<img width="1264" height="751" alt="屏幕截图 2026-08-28 233627" src="https://github.com/user-attachments/assets/c4d50b3d-7c31-411c-95c0-48b45c18db4b" />
<img width="1268" height="743" alt="屏幕截图 2026-08-28 233757" src="https://github.com/user-attachments/assets/8c5ce4cb-9ace-45b5-8353-0079556be80f" />
<img width="1265" height="744" alt="屏幕截图 2026-08-28 233722" src="https://github.com/user-attachments/assets/a47b5cc4-0488-43b0-ab16-b7b0f77ef92c" />
<img width="1278" height="748" alt="屏幕截图 2026-08-28 233641" src="https://github.com/user-attachments/assets/26b4244f-e480-4553-bca3-ba6ad8ee2968" />

### pre Classic 0.67

<img width="1271" height="755" alt="屏幕截图 2026-08-30 050545" src="https://github.com/user-attachments/assets/0e086401-ed97-4d50-be79-7f2cae2c61e3" />
<img width="1267" height="751" alt="屏幕截图 2026-08-30 050552" src="https://github.com/user-attachments/assets/09338636-22b5-41b9-9896-74825c4e9567" />



## ⚙️ Technical Details

### Rendering
- OpenGL-based 3D rendering
- Textured voxel blocks
- First-person and third-person cameras
- Frustum/camera handling

### World
- Procedurally generated terrain
- Chunk-based world
- Multiple biomes
- Block placement and destruction

### Entities
- Custom mob system
- Zombie entity
- Basic zombie AI
- Entity collision

### Physics
- Player movement
- Gravity
- Jumping
- Sneaking
- Sprinting
- Water interaction

## 📈 Development Progress

- [x] Basic voxel rendering
- [x] Terrain generation
- [x] Block interaction
- [x] Inventory
- [x] Crafting
- [x] Water
- [x] TNT
- [x] Zombie
- [x] Basic mob AI
- [x] Spectator mode
- [x] grass blending 
- [ ] Third-person camera
- [ ] Improved chunk loading
- [ ] More entities
- [ ] Improved physics
- [ ] More world generation



## 🧱Blocks
```
Grass
Dirt
Stone
Bedrock
Sand
Sandstone
Gravel
Coal Ore
Iron Ore
Gold Ore
Redstone Ore
Diamond Ore
Emerald Ore
Oak Log
Oak Leaves
Birch Log (from debug inventory)
Taiga Leaves (mentioned in alpha textures)
Tall Grass (mentioned in alpha textures)
Sapling (drops from leaves)
Cactus (generated in deserts)
Cobblestone (drops from stone)
Oak Planks (crafted from logs)
Crafting Table (crafted from planks)
TNT (from debug inventory, can explode using Oak Log)
Ancient Debris (from debug inventory)
Debug Block (placeholder)
Clouds (rendered in the sky)
Water (fluid, but placed as a block)
```
## 🧟Mobs
- zombie

## 🎮Keyboard Controls (24 Keys)
### Movement & Actions
W	Move forward

S	Move backward

A	Strafe left

D	Strafe right

Space	Jump / Fly up (spectator)

LShift	Sneak (prevents falling off edges) / Fly down (spectator)

LCtrl	Sprint (run faster)
### Inventory & UI
E	Open/Close inventory

1 – 9	Select hotbar slot (1–9)

Esc	Pause game / Open game menu
### Debug & Tools
F3	Toggle debug HUD (shows coordinates, biome, FPS, etc.)

F5	Cycle camera view (1st person → 3rd person → etc.)

T	Open command input (type /clear or /exit)

P	Toggle spectator mode (free flight, no clipping)

L	Debug: Fill inventory with random blocks (grass, stone, TNT, etc.)

F11	Toggle fullscreen mode

### Mouse Controls (5 Interactions)

Left Click (hold)	Break / mine blocks

Right Click	Place blocks / Open crafting table / Interact

Scroll Up	Cycle to previous hotbar slot

Scroll Down	Cycle to next hotbar slot

Mouse Movement	Look around (camera rotation)

## 🖥️ Performance

Performance depends heavily on render distance, terrain complexity,
visible blocks, entities, and hardware.

The project is actively being optimized, with a focus on:

- Chunk loading
- Terrain generation
- OpenGL rendering
- Block rendering
- Entity rendering
- Frame-rate consistency

# REQUIREMENTS:

```pyopengl==3.1.5```

```pyglet==1.5.28```

```numpy==1.19.3```

```pygame==2.0.1```

## 🚀 Installation

### Requirements

* Python 3.8–3.12 recommended (This game is developed in python 3.12)
* Windows 10+ 
* OpenGL-compatible graphics hardware

Install the required Python packages:

```bash
pip install -r requirements.txt
```

Or install them manually:

```bash
pip install pyopengl==3.1.5 pyglet==1.5.28 numpy==1.19.3 pygame==2.0.1
```

### Running the Game

Clone the repository:

```bash
git clone https://github.com/happyleibniz2/Minecraft-Python-edition.git
cd Minecraft-Python-edition
```

Then start the game:

```bash
python start.py
```

Do not use the included `run.bat` on Windows.

---

## 📜 License

This project is licensed under the **MIT License**.

See the [`LICENSE`](LICENSE) file for the full license text.

Minecraft is a trademark of Mojang Studios. This project is an independent, fan-made Minecraft-inspired project and is not affiliated with or endorsed by Mojang Studios or Microsoft.


