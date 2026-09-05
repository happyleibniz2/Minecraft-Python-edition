"""Forge-inspired Python mod loader.

Mods live in ``mods/`` as either ``name.py`` or ``name/mod.py`` and expose
optional ``pre_init(api)``, ``init(api)`` and ``post_init(api)`` hooks.
``MOD_INFO`` may define ``id``, ``version`` and ``dependencies``.
"""

import importlib.util
import logging
import os
import sys
import traceback
from collections import defaultdict

import pyglet
from OpenGL.GL import *


class EventBus:
    def __init__(self, loader=None):
        self.listeners = defaultdict(list)
        self.listener_owners = defaultdict(dict)
        self.loader = loader

    def subscribe(self, event, callback):
        if callback not in self.listeners[event]:
            self.listeners[event].append(callback)
            owner = self.loader.current_mod if self.loader is not None else None
            self.listener_owners[event][callback] = owner
        return callback

    def remove_owner(self, owner):
        for event, callbacks in list(self.listeners.items()):
            callbacks[:] = [
                callback for callback in callbacks
                if self.listener_owners[event].get(callback) != owner
            ]
            self.listener_owners[event] = {
                callback: callback_owner
                for callback, callback_owner in self.listener_owners[event].items()
                if callback_owner != owner
            }

    def post(self, event, **payload):
        results = []
        for callback in self.listeners.get(event, ())[:]:
            previous_owner = self.loader.current_mod if self.loader is not None else None
            if self.loader is not None:
                self.loader.current_mod = self.listener_owners[event].get(callback)
            try:
                results.append(callback(**payload))
            except Exception:
                logging.exception("Mod event '%s' failed in %r", event, callback)
            finally:
                if self.loader is not None:
                    self.loader.current_mod = previous_owner
        return results


class ForgeAPI:
    def __init__(self, loader):
        self.loader = loader
        self.scene = loader.gl
        self.events = loader.events

    def subscribe(self, event, callback):
        return self.events.subscribe(event, callback)

    def register_entity(self, entity_id, factory):
        entity_id = self._valid_id(entity_id)
        if entity_id in {"cow", "sheep", "zombie"}:
            raise ValueError(f"Registry id already exists: {entity_id}")
        self.loader._record_mapping_change(self.scene.mod_entity_types, entity_id)
        self.scene.mod_entity_types[entity_id] = factory
        self.events.post("entity_registered", entity_id=entity_id, factory=factory)

    def register_item(self, name, texture_path, stack_size=64):
        from game import Items

        name = self._valid_id(name)
        self.loader._record_mapping_change(self.scene.texture, name)
        self.loader._record_mapping_change(self.scene.inventory_textures, name)

        image = pyglet.image.load(texture_path)
        texture = image.get_texture()
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        self.scene.texture[name] = pyglet.graphics.TextureGroup(texture)

        icon = pyglet.image.load(texture_path)
        icon.width = 22
        icon.height = 22
        self.scene.inventory_textures[name] = icon

        previous_stack = Items.CUSTOM_STACK_SIZES.get(name)
        was_non_block = name in Items.NON_BLOCK_ITEMS
        self.loader._record_undo(
            lambda: self._restore_item(name, previous_stack, was_non_block)
        )
        Items.register_item(name, stack_size)
        self.events.post("item_registered", name=name)

    def register_block(self, name, texture_paths, block_type="solid"):
        name = self._valid_id(name)
        if isinstance(texture_paths, str):
            texture_paths = [texture_paths] * 6
        if len(texture_paths) != 6:
            raise ValueError("register_block requires one texture or six face textures")

        self.loader._record_mapping_change(self.scene.block, name)
        self.loader._record_mapping_change(self.scene.texture, name)
        self.loader._record_mapping_change(self.scene.inventory_textures, name)
        groups = []
        for path in texture_paths:
            image = pyglet.image.load(path)
            texture = image.get_texture()
            glBindTexture(texture.target, texture.id)
            glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
            glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
            groups.append(pyglet.graphics.TextureGroup(texture))
        self.scene.block[name] = tuple(groups)
        self.scene.texture[name] = groups[0]

        icon = pyglet.image.load(texture_paths[3])
        icon.width = 22
        icon.height = 22
        self.scene.inventory_textures[name] = icon
        if block_type == "alpha":
            already_alpha = name in self.scene.mod_alpha_textures
            self.loader._record_undo(lambda: self._restore_alpha(name, already_alpha))
            self.scene.mod_alpha_textures.add(name)
            if name not in self.scene.cubes.alpha_textures:
                self.scene.cubes.alpha_textures = tuple(self.scene.cubes.alpha_textures) + (name,)
        self.events.post("block_registered", name=name, block_type=block_type)

    def _restore_alpha(self, name, already_alpha):
        if already_alpha:
            return
        self.scene.mod_alpha_textures.discard(name)
        self.scene.cubes.alpha_textures = tuple(
            item for item in self.scene.cubes.alpha_textures if item != name
        )

    @staticmethod
    def _restore_item(name, previous_stack, was_non_block):
        from game import Items

        if previous_stack is None:
            Items.CUSTOM_STACK_SIZES.pop(name, None)
        else:
            Items.CUSTOM_STACK_SIZES[name] = previous_stack
        if not was_non_block:
            Items.NON_BLOCK_ITEMS.discard(name)

    @staticmethod
    def _valid_id(value):
        value = str(value).strip().lower()
        if not value or not all(character.isalnum() or character in "_-" for character in value):
            raise ValueError(f"Invalid registry id: {value!r}")
        return value


class ModLoader:
    def __init__(self, gl=None, sound=None, settings=None, player=None, gui=None,
                 gc=None, mods_path="mods"):
        self.gl = gl
        self.sound = sound
        self.settings = settings
        self.player = player
        self.gui = gui
        self.garbage_collector = gc
        self.mods_path = mods_path
        self.current_mod = None
        self.events = EventBus(self)
        self.api = ForgeAPI(self)
        self.loaded_mods = {}
        self.failed_mods = {}
        self._ordered = []
        self._dependencies = {}
        self._undo_actions = defaultdict(list)
        self._completed_phases = set()
        self._prepared = False

    def discover(self):
        if not os.path.isdir(self.mods_path):
            return []
        candidates = []
        for entry in sorted(os.listdir(self.mods_path)):
            if entry.startswith("_"):
                continue
            path = os.path.join(self.mods_path, entry)
            if os.path.isfile(path) and entry.endswith(".py"):
                candidates.append(path)
            elif os.path.isdir(path):
                module = os.path.join(path, "mod.py")
                if os.path.isfile(module):
                    candidates.append(module)
        return candidates

    def load_all(self):
        self.load_pre_init()
        return self.load_remaining()

    def load_pre_init(self):
        self._prepare()
        self._run_phase("pre_init")
        self._refresh_loaded_mods()
        return self.loaded_mods

    def load_remaining(self):
        self.load_pre_init()
        self._run_phase("init")
        self._run_phase("post_init")
        self._refresh_loaded_mods()
        logging.info("Loaded %d mods: %s", len(self.loaded_mods),
                     ", ".join(self.loaded_mods) or "none")
        return self.loaded_mods

    def try_better(self):
        """Legacy entry point that executes the complete lifecycle."""
        return self.load_all()

    def post(self, event, **payload):
        return self.events.post(event, **payload)

    def _import_mod(self, path):
        provisional = os.path.splitext(os.path.basename(path))[0]
        module_name = f"mynnkraft_mod_{provisional}_{abs(hash(os.path.abspath(path)))}"
        spec = importlib.util.spec_from_file_location(module_name, path)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            sys.modules.pop(module_name, None)
            raise
        module.__mynnkraft_source__ = path
        module.__mynnkraft_fallback_id__ = self._fallback_id(path)
        return module

    def _prepare(self):
        if self._prepared:
            return
        modules = []
        for path in self.discover():
            try:
                modules.append(self._import_mod(path))
            except Exception as error:
                self.failed_mods[path] = error
                logging.error("Failed loading mod %s\n%s", path, traceback.format_exc())
        self._ordered, self._dependencies = self._dependency_order(modules)
        self._prepared = True

    def _run_phase(self, phase):
        if phase in self._completed_phases:
            return
        for mod_id, module in self._ordered:
            if mod_id in self.failed_mods:
                continue
            failed_dependency = next(
                (dependency for dependency in self._dependencies[mod_id]
                 if dependency in self.failed_mods), None
            )
            if failed_dependency is not None:
                self._mark_failed(
                    mod_id, RuntimeError(f"Dependency {failed_dependency} failed")
                )
                continue
            hook = getattr(module, phase, None)
            if hook is None:
                continue
            self.current_mod = mod_id
            try:
                hook(self.api)
                self.events.post(f"mod_{phase}", mod_id=mod_id, module=module)
            except Exception as error:
                self._mark_failed(mod_id, error)
                logging.error("Mod %s failed during %s\n%s",
                              mod_id, phase, traceback.format_exc())
            finally:
                self.current_mod = None
        self._completed_phases.add(phase)

    def _mark_failed(self, mod_id, error):
        if mod_id in self.failed_mods:
            return
        self.failed_mods[mod_id] = error
        self.events.remove_owner(mod_id)
        for undo in reversed(self._undo_actions.pop(mod_id, ())):
            try:
                undo()
            except Exception:
                logging.exception("Failed rolling back mod %s", mod_id)
        for dependent, dependencies in self._dependencies.items():
            if mod_id in dependencies:
                self._mark_failed(
                    dependent, RuntimeError(f"Dependency {mod_id} failed")
                )

    def _record_undo(self, callback):
        if self.current_mod is not None:
            self._undo_actions[self.current_mod].append(callback)

    def _record_mapping_change(self, mapping, key):
        if self.current_mod is None:
            return
        if key in mapping:
            raise ValueError(f"Registry id already exists: {key}")

        def undo():
            mapping.pop(key, None)

        self._record_undo(undo)

    def _refresh_loaded_mods(self):
        self.loaded_mods = {
            mod_id: module for mod_id, module in self._ordered
            if mod_id not in self.failed_mods
        }

    @staticmethod
    def _fallback_id(path):
        filename = os.path.basename(path)
        raw = (os.path.basename(os.path.dirname(path))
               if filename == "mod.py" else os.path.splitext(filename)[0])
        normalized = "".join(
            character if character.isalnum() or character in "_-" else "_"
            for character in raw.lower()
        ).strip("_-")
        return normalized or "unnamed_mod"

    def _dependency_order(self, modules):
        grouped = defaultdict(list)
        dependencies = {}
        for module in modules:
            source = module.__mynnkraft_source__
            try:
                info = getattr(module, "MOD_INFO", {})
                if not isinstance(info, dict):
                    raise TypeError("MOD_INFO must be a dictionary")
                mod_id = ForgeAPI._valid_id(
                    info.get("id", module.__mynnkraft_fallback_id__)
                )
                raw_dependencies = info.get("dependencies", ())
                if isinstance(raw_dependencies, str):
                    raw_dependencies = (raw_dependencies,)
                dependencies[mod_id] = tuple(
                    ForgeAPI._valid_id(dependency) for dependency in raw_dependencies
                )
                grouped[mod_id].append(module)
            except Exception as error:
                self.failed_mods[source] = error

        by_id = {}
        for mod_id, candidates in grouped.items():
            if len(candidates) > 1:
                error = ValueError(f"Duplicate mod id: {mod_id}")
                self.failed_mods[mod_id] = error
                for module in candidates:
                    self.failed_mods[module.__mynnkraft_source__] = error
            else:
                by_id[mod_id] = candidates[0]

        ordered = []
        state = {}
        stack = []

        def visit(mod_id):
            if mod_id in self.failed_mods:
                return False
            if state.get(mod_id) == 2:
                return True
            if state.get(mod_id) == 1:
                cycle = stack[stack.index(mod_id):]
                for member in cycle:
                    self.failed_mods[member] = ValueError(
                        f"Circular mod dependency involving {', '.join(cycle)}"
                    )
                return False

            state[mod_id] = 1
            stack.append(mod_id)
            valid = True
            for dependency in dependencies.get(mod_id, ()):
                if dependency not in by_id:
                    self.failed_mods[mod_id] = ValueError(
                        f"Mod {mod_id} requires missing mod {dependency}"
                    )
                    valid = False
                    break
                if not visit(dependency):
                    self.failed_mods.setdefault(
                        mod_id, RuntimeError(f"Dependency {dependency} failed")
                    )
                    valid = False
                    break
            stack.pop()
            state[mod_id] = 2
            if valid and mod_id not in self.failed_mods:
                ordered.append((mod_id, by_id[mod_id]))
                return True
            return False

        for mod_id in sorted(by_id):
            visit(mod_id)
        valid_dependencies = {
            mod_id: dependencies.get(mod_id, ()) for mod_id, _ in ordered
        }
        return ordered, valid_dependencies
