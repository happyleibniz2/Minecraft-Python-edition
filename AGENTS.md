
---

```markdown
# AGENTS.md — Minecraft Python Edition (Genshin Branch)

> OpenCode 项目规则文件。每次会话启动时自动加载。
> 目的：让 Agent 快速理解项目结构、约定、关键路径，避免盲目探索。

---

## 1. 项目概述

**Minecraft Python Edition** — 用 Python 写的 Minecraft 风格体素游戏。

- **引擎**：Pygame + PyOpenGL + Pyglet + NumPy
- **渲染**：OpenGL 3D，块状体素，第一/第三人称摄像机
- **世界**：程序化地形，区块加载，多生物群系
- **Mod 系统**：Forge 风格的 `mods/` 目录，自动加载
- **当前分支**：`Genshin` — 加入原神角色 Vesna 和 Paimon 作为可生成实体

**Python 版本**：3.8–3.12（开发环境为 3.12）
**平台**：Windows 10+ 优先，Linux 兼容

---

## 2. 快速命令

| 操作 | 命令 |
|------|------|
| 安装依赖 | `pip install -r requirements.txt` |
| 启动游戏 | `python3.12 start.py` |
| 运行测试 | `python3.12 -m pytest tests/ -v` |
| 检查语法 | `python3.12 -m py_compile <file>.py` |

**注意**：Windows 上不要用 `run.bat`，直接用 `python start.py`。

---

## 3. 项目结构

```
Minecraft-Python-edition/
├── start.py                    # 入口点，环境检查 + 启动主程序
├── minecraft_main_program.py   # 主游戏循环，场景初始化，事件处理
├── settings.py                 # 全局设置，选项加载/保存（gui/options.json）
├── functions.py                # 工具函数，纹理加载
├── requirements.txt
├── assimp-vc143-mt.dll         # assimp 运行时 DLL（根目录）
│
├── game/                       # 核心游戏引擎
│   ├── Scene.py                # 场景类，渲染循环
│   ├── entity/                 # 实体系统
│   │   ├── Entity.py           # 实体基类
│   │   ├── PassiveMob.py       # 被动生物基类（Vesna/Paimon 继承此）
│   │   ├── Player.py           # 玩家
│   │   ├── Zombie.py           # 僵尸
│   │   ├── Cow.py              # 牛
│   │   ├── Sheep.py            # 羊
│   │   ├── SpawnEggs.py        # 生成蛋
│   │   └── Inventory.py
│   ├── blocks/                 # 方块系统
│   │   ├── Cube.py             # 方块数据
│   │   ├── CubeHandler.py      # 方块管理
│   │   ├── RenderChunk.py      # 区块渲染
│   │   ├── Water.py            # 水物理
│   │   ├── CraftingTable.py
│   │   └── droppedBlock.py
│   ├── world/                  # 世界生成
│   │   ├── worldGenerator.py   # 地形生成
│   │   ├── Biomes.py           # 生物群系
│   │   ├── Clouds.py           # 体积云
│   │   ├── DayNightCycle.py    # 昼夜循环
│   │   ├── Explosion.py        # TNT 爆炸
│   │   └── PerlinNoise.py
│   ├── GUI/                    # 用户界面
│   │   ├── GUI.py              # GUI 管理器
│   │   ├── Button.py, Sliderbox.py, Editarea.py, ModalWindow.py
│   ├── Lighting/               # 光照系统
│   │   └── Light.py
│   ├── sound/                  # 声音系统
│   │   ├── Sound.py, BlockSound.py, SoundPhysics.py
│   └── Mod/forge/              # Mod 加载器
│       └── mod_loader.py       # 核心：EventBus, ForgeAPI, 安全 .mcpymod 解压
│
├── mods/                       # Mod 目录（自动加载）
│   ├── Vesna/                  # Vesna 实体 mod
│   │   ├── mod.json            # mod 元数据
│   │   ├── mod.py              # 实体类，材质映射，渲染逻辑
│   │   ├── fbx_loader.py       # FBX 加载器（ctypes + assimp DLL）
│   │   └── assets/vesna/       # 模型 + 纹理 + 材质 JSON
│   └── Paimon/                 # Paimon 实体 mod
│       ├── mod.json
│       ├── mod.py
│       ├── fbx_loader.py
│       └── assets/Paimon/      # 模型 + 纹理
│
├── shaders/                    # BSL 风格延迟渲染管线
│   ├── pipeline_config.glsl    # 共享 uniforms，常量，宏
│   ├── shadow/                 # 阴影贴图生成
│   ├── gbuffers/               # G-buffer 几何传递
│   ├── deferred/               # 光照计算
│   ├── composite/              # 后处理 + 色调映射
│   └── final/                  # 最终输出
│
├── textures/                   # 方块和物品纹理
├── sounds/                     # 音效文件
├── gui/                        # GUI 资源 + options.json + lang.mclanguage
├── assets/Minecraft/           # 语言文件，背景纹理
├── saves/Current_world/        # 世界存档
└── tests/                      # 测试
```

---

## 4. 代码风格与约定

### 导入顺序
1. 标准库（`os`, `sys`, `json`, `math`, `random`）
2. 第三方（`numpy`, `pygame`, `pyglet`, `OpenGL`）
3. 项目内部（`from settings import *`, `from game.xxx import yyy`）

### 命名
- 类名：`PascalCase`（`PassiveMob`, `CubeHandler`）
- 函数/变量：`snake_case` 或 `camelCase`（项目混用，跟现有文件保持一致）
- 常量：`UPPER_SNAKE`（`MESH_TEXTURE_MAP`, `GROUND_OFFSET`）
- 私有方法：`_leading_underscore`

### 日志
- 使用 `logging` 模块，`log_deb()` 用于调试输出
- 日志文件自动写入 `logs/YYYY-MM-DD_HH-MM-SS.log`
- **不要用 `print()` 做调试**，除非是临时排查

### 异常处理
- FBX 加载失败时打印完整 traceback（`traceback.print_exc()`）
- Mod 事件回调失败会被 EventBus 记录，3 次后自动退订
- 不要吞掉异常，至少记录日志

---

## 5. 关键模块详解

### 5.1 Mod 系统 (`game/Mod/forge/mod_loader.py`)

- **加载路径**：`mods/name.mcpymod`（zip 归档）、`mods/name.py`、`mods/name/mod.py`
- **生命周期钩子**：`pre_init(api)` → `init(api)` → `post_init(api)`
- **元数据**：归档用 `mod.json`，散装 mod 用 `MOD_INFO` 字典
- **事件总线**：`api.events.subscribe(event, callback)` 注册回调
- **安全解压**：自动防御 zip-slip 路径穿越
- **注册 API**：`api.register_entity(id, factory)` 注册自定义实体

**⚠️ 修改 mod_loader.py 时务必运行 `python -m pytest tests/test_mod_archives.py`**

### 5.2 实体系统 (`game/entity/`)

- `Entity.py` — 基类，有 `gl` 引用，位置，碰撞
- `PassiveMob.py` — 被动生物基类，有 `WANDER_SPEED`，随机游走 AI
- Vesna 和 Paimon 继承 `PassiveMob`

**自定义实体 mod 的最小结构**：
```python
class MyEntity(PassiveMob):
    TEXTURE_PATH = ""
    WANDER_SPEED = 0.4
    GROUND_OFFSET = -1.25
    MODEL_SCALE = 1.8
    MODEL_OFFSET = 0.0

    def __init__(self, gl):
        super().__init__(gl)
        # 自定义初始化

    def _load_textures(self):
        # 加载纹理，构建 display list
        ...
```

### 5.3 FBX 加载器 (`mods/*/fbx_loader.py`)

- 使用 `ctypes` 调用 `assimp-vc143-mt.dll`（根目录）
- Windows：`ctypes.CDLL("assimp-vc143-mt.dll")`
- 返回 `list[dict]`，每个 mesh 包含：
  - `vertices` (N,3), `normals` (N,3), `uvs` (N,2), `indices` (M,)
  - `num_vertices`, `num_faces`, `material_index`, `material_name`

**⚠️ assimp DLL 必须在根目录，且 Windows 需先 `os.add_dll_directory()`**

### 5.4 Shader 系统 (`shaders/`)

- BSL 风格延迟渲染管线：`shadow → shadow_composite → prepare → gbuffers → deferred → translucent → composite → final`
- Ping-Pong 缓冲：colortex0-15 交替使用
- 质量预设：Low / Medium / High / Ultra
- 关键文件：`pipeline_config.glsl`（共享 uniforms 和宏）

**修改 shader 时注意**：
- GLSL 版本兼容（项目未显式声明版本，默认兼容模式）
- 不要破坏 Ping-Pong 缓冲的读写顺序

---

## 6. 当前开发焦点（Genshin 分支）

### 已完成
- [x] Vesna 和 Paimon 的 FBX 几何体加载
- [x] 材质索引和材质名读取
- [x] 纹理绑定（有轻微错位，待修复）
- [x] 实体生成和位置放置

### 进行中 / 待办
- [ ] **纹理错位修复** — 可能是 UV 翻转 / UV 通道 / 材质映射问题
- [ ] **统一两个 mod 的纹理映射** — Vesna 用 `Materials/*.json`，Paimon 用硬编码
- [ ] **面索引修复** — 当前 `indices = np.arange(nv)`，未读 `mFaces`
- [ ] **VBO / glDrawElements 迁移** — 当前用 display list，性能差
- [ ] **坐标 / 缩放 / 朝向统一** — 两个 mod 的 `MODEL_SCALE` 和 `GROUND_OFFSET` 不一致

### 已知问题
- `fbx_loader.py` 中 `indices = np.arange(nv)` — 对某些模型可能 UV 错位
- Vesna 和 Paimon 的材质映射逻辑不统一
- Paimon 的 UV 是量化的（5 个调色板索引），需要专用 shader

---

## 7. 常见陷阱

1. **不要在 Windows 上使用 `run.bat`** — 直接用 `python start.py`
2. **assimp DLL 必须在根目录** — `fbx_loader.py` 从根目录加载
3. **`gui/lang.mclanguage` 决定语言** — `settings.py` 启动时读取
4. **`gui/options.json` 持久化设置** — 修改 `settings.py` 的 `save_options()` 时同步更新
5. **不要手动修改 `saves/` 目录** — 游戏自动管理
6. **`__pycache__` 已提交** — 不要删除或 gitignore
7. **shader 文件没有显式 `#version`** — 保持兼容模式
8. **Mod 事件回调抛异常会被自动退订** — 3 次失败即移除

---

## 8. 给 OpenCode 的特别说明

### 上下文管理
- **不要默认扫描整个仓库**。先读本文件，再按任务需要读取相关文件。
- 修改代码前，先读目标文件和它的直接依赖。
- 如果任务涉及 `mods/Vesna` 或 `mods/Paimon`，**两个目录一起读**，因为它们结构对称但实现不一致。

### 输出偏好
- 输出完整文件，不要片段（除非明确要求）
- 修改代码时保留现有注释和风格
- 不要引入新依赖，除非必要
- 不要自动格式化整个文件

### 任务拆分
- 大任务拆成小步骤，每步输出后等待验证
- 不要一次性重构多个模块
- 修改后提供测试命令

### 禁止事项
- ❌ 不要修改 `start.py` 的 pip 安装逻辑
- ❌ 不要改动 `settings.py` 的全局变量名
- ❌ 不要删除 `logs/` 目录
- ❌ 不要碰 `assimp-vc143-mt.dll`

---

## 9. 参考链接

- [仓库](https://github.com/happyleibniz2/Minecraft-Python-edition/tree/Genshin)
- [README](https://github.com/happyleibniz2/Minecraft-Python-edition/blob/Genshin/README.md)
- [Shader 文档](https://github.com/happyleibniz2/Minecraft-Python-edition/tree/Genshin/shaders)

---

*最后更新：2026-09-19*
*分支：Genshin*
```

---

