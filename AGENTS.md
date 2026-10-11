
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
│   │   ├── Light.py            # 平滑光照主 shader（GLSL 1.20）
│   │   └── SkyShader.py        # 夜空黑洞 shader（引力透镜 + 吸积盘 + 事件视界）
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

**⚠️ ctypes 结构布局（assimp 5.2.5 x64，两次踩坑后验证）**：
- `aiMesh` 在 `mBitangents` 之后有 `mColors[8]`（即使模型无顶点色也占位）——漏掉会把 `mFaces` 从真实偏移 208 错读到 144，表现为 `ValueError: NULL pointer access`
- `aiString.mLength` 是 **4 字节 `ai_uint32`**，不是 `c_size_t`——用 8 字节会把 `mData` 后移 4 字节，每个材质名截掉前 4 个字符（`Avatar_...` 变 `ar_...`），导致材质名匹配全部失败
- 两个 mod 的 `fbx_loader.py` 必须保持一致；材质名靠 `aiGetMaterialString` 读取

**⚠️ 材质→纹理映射**：`mod.json` 的 `texture_map` 以**完整材质名**为 key（Paimon: `NPC_Kanban_Paimon_Mat_Body` 等；Vesna: `Avatar_Girl_Sword_Vesna_Mat_Hair` 等）。Vesna 的 `Avatar_Default_Mat` 在源材质 JSON 中无 `_MainTex`，故意留空不映射

### 5.4 Shader 系统 (`shaders/`)

- BSL 风格延迟渲染管线：`shadow → shadow_composite → prepare → gbuffers → deferred → translucent → composite → final`
- Ping-Pong 缓冲：colortex0-15 交替使用
- 质量预设：Low / Medium / High / Ultra
- 关键文件：`pipeline_config.glsl`（共享 uniforms 和宏）

**修改 shader 时注意**：
- GLSL 版本兼容（项目未显式声明版本，默认兼容模式）
- 不要破坏 Ping-Pong 缓冲的读写顺序

### 5.5 夜空黑洞 shader (`game/Lighting/SkyShader.py`)

- GLSL 1.20 全屏 pass，在 `Scene.draw()` 中 `drawAtmosphereSky()` 和 `drawCelestialSky()` 之后、云渲染之前执行
- **世界锚定**：Python 端每帧传相机基向量（`cameraForward/Right/Up`，来自 `player.rotation`，与 `Clouds` 相同的公式）、`tanHalfFov`、黑洞天球方向 `blackHoleDirection`（反太阳点 `(0, -sin a, cos a)`，午夜在天顶）；fragment 从 NDC 重建真实视线方向——转动视角时黑洞像星空一样在天球上移动，不再粘屏
- **视觉目标是《星际穿越》的卡冈图雅（Gargantua）**：
  - 薄亮吸积盘近乎侧视（`DISK_NORMAL = (0.989, 0.148, 0)`，全世界固定，倾角约 8.5°）；温度配色 `r^-3/4`，亮度 `r^-2`，多普勒近侧增亮偏蓝
  - 近/远侧由 `side = a2·dot(diskNormal, bhDir)` 物理判定：近侧盘亮线穿过事件视界前半部，远侧被吸收
  - 远侧盘面引力包裹成上弧（`LAMBDA_OVER=0.42`，亮）与下弧（`LAMBDA_UNDER=0.26`，暗，仅 HIGH）
  - 光子环 `rho≈1` 高斯细线；捕获区 `smoothstep(0.985,1.0,rho)` 纯黑
  - 星场用切平面的精确点质量（Einstein）透镜 `beta = theta·(1 - thetaE²/|theta|²)`，`rho=1` 处放大率发散成爱因斯坦环；星源按**方向**经八面体映射采样（`skyUv`），星 glued 到天球
- 坐标约定：`rho = |ray 在天空平面的分量| / shadowSin`（`shadowSin = sin(14°)` 阴影角半径），`rho=1` 即捕获边界
- **质量分级 `settings.BLACKHOLE_QUALITY`**（`OFF`/`LOW`/`HIGH`，shader 设置菜单循环切换，`gui/options.json` 持久化）：OFF 跳过整个 pass（回落原版星点）；LOW 无星场透镜 + 仅上弧；HIGH 全部
- 只在 `star_brightness > 0.01` 时激活，白天保留固定管线太阳/月亮纹理
- 初始化时机：`Scene.resetScene()` 只做构造；编译在 GL context 就绪后 `self.light.initialize()` 旁，随后 `set_quality(game_settings.BLACKHOLE_QUALITY)`
- 资源释放：`resetScene()` 会 `close()` 上一个实例的 GL 程序
- 无 GL context 时优雅降级（`tests/test_sky_shader.py` 覆盖 11 个无 GL 路径）

### 5.6 体积云 (`game/world/Clouds.py`)

- GLSL 1.20 全屏 raymarch pass（`Scene.draw()` 中天空之后）；`volume_shader` 编译失败或 shader 关闭时回落经典 billboard 云团
- **密度场**：FBM 基形 + Worley 细胞结构混合；`uDetail≥1` 用高频 Worley 沿边缘侵蚀（`1-density` 加权 → 厚核不散、边缘成絮）
- **光照（UE 风格近似）**：向阳光的 Beer-Lambert 二次行进自遮蔽（`uSunSamples` 次采样，光深>2 早停）；双瓣 Henyey-Greenstein 相位（前向强散射 + 向后弱瓣，`hgPhase` 分母有 epsilon 保护）；Powder 项防"棉花球"扁平化；`skyColor` 环境项近似一拍多重散射
- **采样纪律**：IGN（interleaved-gradient-noise）抖动把条带变成高频噪声；自适应步进（空旷处步长 ×3）；透射率 <0.02 早停
- **质量分级 `settings.CLOUD_QUALITY`**（POTATO/LOW/MEDIUM/HIGH/GPU，`Clouds.QUALITY_PARAMS` 表驱动）：**五档全部 raymarch**（POTATO=4步/1阳光采样最便宜，GPU=32步+8采样+全部特性）；billboard 云团仅作 volume shader 不可用时的回落（实测 billboard 路径 ~6.3ms/帧 CPU——瓶颈是 ~782 个即时模式 quad 的 PyOpenGL 提交（90%），列表构建 0.57ms、排序仅 0.09ms，勿盲删排序）。菜单中 GPU 显示为红色 `I PAID FOR THE WHOLE GPU!`
- quality 通过 uniform 驱动（`uSteps/uSunSamples/uDetail/uPowder/uAdaptive/uDualLobe`），**无需重编译**；`Scene.resetScene()` 重建后 `set_quality(game_settings.CLOUD_QUALITY)` 应用
- **半分辨率渲染（UE 标准优化）**：LOW/MEDIUM/HIGH 在 `(W/2, H/2)` FBO 中 raymarch，LINEAR 上采样合成到天空（`resolution_scale=0.5`）；GPU 档全分辨率。FBO 按需重建（窗口 resize 检测尺寸变化），`close()` 释放；FBO 不完整时自动回落直渲
- 暂未实现的时间重投影：需要运动向量 + 历史缓冲基建，当前由"半分辨率 × 采样分级"承担性能伸缩
- **实测数据（GL 4.6 compat + GL_TIME_ELAPSED timer query，-60° 云最重视角，854×480 窗口，AMD Radeon 集显）**：GPU 时间 POTATO 0.68ms / LOW 1.30ms / MEDIUM 5.96ms / HIGH 12.15ms / GPU 21.07ms；地平线视角更低（MEDIUM ≈3.4ms CPU 全链路）。IGN 抖动为**静态逐像素**（移除了每帧时变项，消除噪点爬行）

### 5.7 性能管线（>120 FPS 目标）

- **`settings.VSYNC`**（默认 **OFF**）：`create_opengl_display` 按 `vsync=1 if VSYNC else 0` 建窗——vsync 会把帧率硬锁在显示器刷新率，高帧率目标必须关。菜单切换标记 (restart)，SDL 仅在建窗时应用
- **MSAA 按设置创建**：`ANTI_ALIASING=False` 时 context 请求 0 samples（原来恒 4x，白白吃填充率）
- **窗口标题 4 Hz 节流**：`set_caption` + f-string 原来每帧执行
- **天空/星点颜色上传缓存**：`Scene.drawAtmosphereSky`（~2400 floats）、`_star/galaxy_vertex_list.colors`（~720/1680 floats）原来每帧重建 tuple；现按量化键（颜色 3 位小数）缓存，只在昼夜颜色变化时重建
- **阴影 pass 正交视锥裁剪**：`CubeHandler.shadow_frustum`（独立 `Frustum` 实例，不污染主视锥）在 `render_shadow` 内对 chunk AABB 精确裁剪——太阳正交盒只覆盖玩家周围 ~48 格，原来按 96 半径距离画全部 chunk
- 帧预算参考：120 FPS = 8.3 ms/帧；云 pass（半分辨率 MEDIUM 16 步）+ 世界批渲染 + 2 Hz 阴影 + Python 主循环为三大头

---

## 6. 当前开发焦点（Genshin 分支）

### 已完成
- [x] Vesna 和 Paimon 的 FBX 几何体加载
- [x] 材质索引和材质名读取
- [x] 面索引修复 — 从 `mFaces` 读取真实索引（`mFaces@208`），不再用 `np.arange(nv)`
- [x] 统一两个 mod 的纹理映射 — `mod.json` 的 `texture_map` / `uv_channel` / `uv_flip_v` 配置驱动
- [x] 材质名匹配修复 — `aiString.mLength` 用 4 字节 `ai_uint32`；`texture_map` 以完整材质名为 key（Paimon 5 项 / Vesna 12 项），`tests/test_mod_models.py` 验证每个 mesh 都解析到真实存在的纹理
- [x] Vesna 合并冲突解决 — `fbx_loader.py` / `mod.py` 保留 ctypes + VBO 渲染版本
- [x] 世界生成批量提交 — `CubeHandler.add_generated_batch()` + `genChunk()` 批量出队，减少脏 section 重标记
- [x] 夜空黑洞 GLSL shader — `game/Lighting/SkyShader.py`，集成进 `Scene.draw()`（待 runtime 视觉验证）
- [x] 聊天框 — `game/GUI/Chat.py`，T 键打开（"/" 键预填斜杠），Enter 发送、Esc 取消；打字时屏蔽移动/鼠标输入
- [x] 命令系统 — `/help`、`/gamemode <creative|survival|spectator>`（creative 免伤）、`/day set <day|night|midnight|0-24000>`、`/clear`、`/exit`
- [x] 黑洞世界锚定 — 相机基向量 + 反太阳点天球方向，转动视角时黑洞随天球移动；星场经八面体映射 glued 到天上
- [x] `settings.BLACKHOLE_QUALITY`（OFF/LOW/HIGH）+ `settings.CLOUD_QUALITY`（POTATO/LOW/MEDIUM/HIGH/GPU），shader 设置菜单循环切换、红色 GPU 档标签
- [x] 体积云重写 — UE 风格：Powder、HG 双瓣、阳光二次行进自遮蔽、边缘侵蚀、IGN 抖动、自适应步进（`game/world/Clouds.py`）
- [x] Pig/Chicken/Creeper 被动生物 + 官方蛋色生成蛋 + 注册进 `Scene.entity_types()`
- [x] `PlayerAvatar`（`game/entity/PlayerAvatar.py`，wide steve 64×64 皮肤）支持的第三人称视图；`Player.updateView` 实现了真正的相机后拉/镜像前视
- [x] F3 切换第三人称（此前是调试面板），`Ctrl+F3` 继承原调试信息切换
- [x] **键位回归香草**：F3 = 调试覆盖层（F3+B 保留 hitboxes），F5 = 相机循环 1/2/3
- [x] 第三人称相机修复 — 拉回平移必须在**最外层**（`glTranslatef(0,0,-back)` 先于 `glRotatef` 调用）；此前相机在玩家前方、玩家落在视锥背后（"玩家全黑"根因），矩阵数值验证 4 用例
- [x] 黑洞吸积盘水平化 — disk 帧由 `cameraUp` 投影构建（视觉水平带 + 上/下包裹弧，Interstellar 构图），倾角固定 0.14；`diskNormal` uniform 移除
- [x] 异步视线可见性 — `game/entity/VisibilityWorker.py` 后台线程做 LOS"路径追踪"，两拍滞回防闪烁；渲染线程零阻塞（结果相机 2 格内有效，超界回落原同步探测）
- [x] 手执动态光源 — `Player.update_hand_light()`：手持火把随身照明，切换物品/死亡/关设置即时熄灭；`settings.DYNAMIC_LIGHTING` 菜单实时门控（shader uniform 已有）
- [x] 创意库存 — `game/entity/CreativeInventory.py`：`tab_items.png` 195×136 region ×2，9×5 调色板（左键整组/右键单个）+ 底部热栏（复用生存槽机制），滚轮翻页，E 键按 `is_creative` 分叉
- [x] gamemode/战斗一致性审计修复（`tests/test_gamemode_combat.py` 锁定）：
  - **幽灵窗口锁死** — 开着任何模态窗口时死亡（创造模式虚空伤害绕过免伤 / 生存开背包被僵尸打死），死亡屏期间 `updateScene` 停跑、窗口 ESC 永远收不到 → 重生后窗口重新锁死 `allowEvents`（无法移动/攻击/破坏）。`death_screen()` 现在强制销毁两个窗口
  - **P 键混合态** — 遗留 P 键只翻 `is_spectator` 不清 `is_creative`，产生 `creative+spectator` 混合（spectator 挡 `attackEntity` → "创造模式打不了怪"）。P 进入旁观时现在会清 `is_creative`
  - **确认无 bug**：`attackEntity` 无 creative 门控（香草创造可攻击），creative→survival 切换本身不影响造成伤害（用户报的症状来自上述两个锁死，非切换逻辑）
- [x] 创意库存滚轮翻页修复 — 翻页原来写在 `keyboardAndMouse` 门控**内**，而模态窗口可见时恰好把该门控设 False（死代码）；现移到事件循环外层优先处理
- [x] 创意库存热栏行修复 — `HOTBAR_Y` 236→224（香草图集热栏行 top-down y=112，像素探测槽位边界 18/36/54/72/90 网格 + 112 热栏）
- [x] 实体距离分层 — `Scene.update_entities()`：水平 64 格内完整模拟；64..128 冻结（渲染保留、AI/物理停跑）；128+ despawn（`die()` 移除）。远处生物群不再拖累帧率（`tests/test_entity_distance.py` 锁定边界与水平距离语义）
- [x] 位置音效距离衰减修复 — **pygame 2.6.1（SDL3）回归**：双参 `set_volume(left, right)` 会把主音量重置为 1.0，导致 `SoundPhysics` 的 32 格衰减完全失效——所有实体脚步声不管多远都满音量（"不管在什么区块都能听到脚步声"）。改用单参 `set_volume(gain)`（含超出距离的早退分支），立体声 pan 暂时降级（代码注释保留待 pygame 修复）。`tests/test_sound_physics.py` 用静音 buffer 在真 mixer 上锁衰减曲线
- [x] 图标纹理上传越界修复 — `functions.realize_icon()`：先上传真实尺寸再改绘制宽高；9 处突变点全部换用（修复库存首次 blit 的 access violation）

### 进行中 / 待办
- [ ] **模型渲染 runtime 视觉验证** — 几何/索引/材质名/纹理映射已由测试覆盖，需 `python start.py` 实际确认贴图正确
- [ ] **VBO / glDrawElements 迁移** — 牛/羊等内置实体仍用 display list，性能差
- [ ] **坐标 / 缩放 / 朝向统一** — 两个 mod 的 `MODEL_SCALE` 和 `GROUND_OFFSET` 不一致（Paimon 2.0 / Vesna 1.8）

### 已知问题
- Paimon 的 UV 是量化的（5 个调色板索引），需要专用 shader——裸 GL 渲染下呈马赛克色块，这是模型源数据特性，不是 bug
- 按 P 键切换旁观模式（`is_spectator`）保留为旧快捷键；`/gamemode spectator` 与之等价

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
9. **不要直接改未上传纹理的 `width/height`** — pyglet 惰性 `get_texture()` 会按突变后的尺寸上传像素 buffer，`glTexSubImage2D` 越界读（偶尔 access violation）。放大图标必须用 `functions.realize_icon(image, w, h)`（先按真实尺寸上传，再改 Texture 的绘制宽高）；texture 化之后再改宽高是安全的（只影响绘制 quad）
10. **GL 平移在外层 = 视图空间平移** — `glTranslatef` 先于 `glRotatef` 调用时平移在视图空间生效（第三人称相机拉回的正确做法）；放在旋转之后会把相机移到世界固定方向上（玩家身后→玩家前方的经典 bug）

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

*最后更新：2026-10-02*
*分支：Genshin*
```

---

