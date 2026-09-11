# Python Forge-style Mods

The recommended distribution format is a ZIP archive named `*.mcpymod`.
Loose `mods/name.py` and `mods/name/mod.py` mods remain supported.

## Archive Layout

The manifest and entry module must be at the archive root, not inside an extra
parent directory.

```text
example.mcpymod
|-- mod.json
|-- mod.py
|-- helper.py
`-- assets/
    |-- models/example.obj
    |-- sounds/example.ogg
    `-- textures/example.png
```

`mod.json` is required:

```json
{
  "id": "example",
  "version": "1.0.0",
  "dependencies": [],
  "entry": "mod.py"
}
```

`id`, `version`, and the `dependencies` list are required. `entry` is optional:
the loader uses `mod.py`, or root `__init__.py` when no `mod.py` exists. Entry
files must remain at the archive root. The manifest is authoritative if the
entry module also defines `MOD_INFO`.

Entry modules are imported as packages, so relative imports work:

```python
from .helper import ExampleEntity

def pre_init(api):
    texture = api.get_asset_path("assets/textures/example.png")
    api.register_item("example_item", texture, stack_size=16)
    api.register_entity("example_entity", ExampleEntity)

def init(api):
    api.subscribe("client_tick", lambda scene, dt: None)

def post_init(api):
    print("Example mod loaded")
```

Available lifecycle hooks are `pre_init`, `init`, and `post_init`.
`pre_init` runs after world registries exist, while `init` and `post_init` run
after built-in sounds and GUI assets are ready. Registry IDs must be unique;
a failed mod and its dependents are isolated without stopping unrelated mods.

The event bus supports `client_tick`, `render_world`, `block_added`,
`block_removed`, `entity_spawned`, plus registration/lifecycle events.

## Assets And Cleanup

Archives are safely extracted into an operating-system temporary directory.
`api.get_asset_path(relative_path)` returns an absolute path inside that
directory. Absolute paths and paths escaping the mod root are rejected.

`loader.unload_mod("example")` unloads dependents first, rolls back registry
and event-bus changes, removes imported package modules, and deletes extracted
files. `loader.close()` unloads every mod and also runs automatically at normal
process exit.

Archive extraction rejects path traversal, symbolic links, encrypted entries,
Windows device names, case-insensitive duplicate paths, unsupported compression,
ZIP64 metadata, more than 2,048 files, oversized metadata, and more than 128 MiB
of archive or extracted content. Standard stored and deflated ZIP entries are
supported.

## Security

`.mcpymod` changes packaging only. A mod is ordinary Python code with the same
access to files, processes, the network, and the operating system as the game.
Install and run only trusted mods.
