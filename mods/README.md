# Python Forge-style Mods

Place mods in `mods/name.py` or `mods/name/mod.py`.

```python
MOD_INFO = {
    "id": "example",
    "version": "1.0.0",
    "dependencies": [],
}

def pre_init(api):
    api.register_item("example_item", "mods/example/item.png", stack_size=16)

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
