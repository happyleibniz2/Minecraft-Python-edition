# Minecraft Python Edition
<img width="1518" height="633" alt="image" src="https://github.com/user-attachments/assets/ffbcd271-5f2a-4176-b17f-d795d6011783" />

![Python](https://img.shields.io/badge/python-%233670A0.svg?style=for-the-badge&logo=python&logoColor=ffdd54)
![NumPy](https://img.shields.io/badge/numpy-%23013243.svg?style=for-the-badge&logo=numpy&logoColor=white)
![OpenGL](https://img.shields.io/badge/opengl-%235586A4.svg?style=for-the-badge&logo=opengl&logoColor=white) 
### Minecraft Python Edition is a Minecraft-inspired voxel game written in Python, using Pygame, PyOpenGL, Pyglet, and NumPy. The project focuses on experimenting with voxel rendering, procedural terrain generation, game physics, entities, and Minecraft-style gameplay systems.

## ✨Features
- Dirty chunk loading

- zombie mob

- simple zombie ai

- Better water texture

- Water physics (sort of)

- Fast terrain generation

- Player mining

- Spectator mode(sort of)

- tnt explosion


## 📸In game screenshots
<img width="1274" height="754" alt="屏幕截图 2026-08-26 075310" src="https://github.com/user-attachments/assets/161883b2-27c2-4fb7-a7f4-bc6a62de4260" />
<img width="1271" height="760" alt="屏幕截图 2026-08-26 075317" src="https://github.com/user-attachments/assets/78d54698-4012-43ab-be1e-e27055eb6f0d" />
<img width="1257" height="752" alt="屏幕截图 2026-08-27 062459" src="https://github.com/user-attachments/assets/237020b5-7b7e-4a5f-8157-1ecd7b7d8a91" />
<img width="1257" height="752" alt="屏幕截图 2026-08-27 062442" src="https://github.com/user-attachments/assets/a81cc5ba-d7df-4117-a164-b0f98d9fd8d3" />
(the zombie is shy)
<img width="1276" height="746" alt="image" src="https://github.com/user-attachments/assets/0c12cbcd-270c-4317-b0ed-4a1181dedb06" />


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
- [x] Third-person camera
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


