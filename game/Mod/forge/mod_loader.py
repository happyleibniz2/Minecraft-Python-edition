"""Forge-inspired Python mod loader with safe ``.mcpymod`` extraction.

Mods live in ``mods/`` as ``name.mcpymod``, ``name.py`` or ``name/mod.py`` and
expose optional ``pre_init(api)``, ``init(api)`` and ``post_init(api)`` hooks.
Archives use root ``mod.json`` metadata; loose mods use optional ``MOD_INFO``.
"""

import atexit
import gc as python_gc
import importlib.util
import json
import logging
import os
import shutil
import stat
import struct
import sys
import tempfile
import traceback
import uuid
import zipfile
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
        if self.loader is not None:
            self.loader._begin_dispatch()
        try:
            for callback in self.listeners.get(event, ())[:]:
                if callback not in self.listeners.get(event, ()):
                    continue
                previous_owner = self.loader.current_mod if self.loader is not None else None
                if self.loader is not None:
                    owner = self.listener_owners[event].get(callback)
                    if owner in self.loader._pending_unloads:
                        continue
                    self.loader.current_mod = owner
                try:
                    results.append(callback(**payload))
                except Exception:
                    logging.exception("Mod event '%s' failed in %r", event, callback)
                finally:
                    if self.loader is not None:
                        self.loader.current_mod = previous_owner
        finally:
            if self.loader is not None:
                self.loader._end_dispatch()
        return results


class ForgeAPI:
    def __init__(self, loader):
        self.loader = loader
        self.scene = loader.gl
        self.events = loader.events

    def subscribe(self, event, callback):
        return self.events.subscribe(event, callback)

    def get_asset_path(self, relative_path):
        if self.loader.current_mod is None:
            raise RuntimeError("get_asset_path must be called from a mod hook or event")
        return self.loader.get_asset_path(self.loader.current_mod, relative_path)

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
    MAX_ARCHIVE_BYTES = 128 * 1024 * 1024
    MAX_CENTRAL_DIRECTORY_SIZE = 4 * 1024 * 1024
    MAX_ARCHIVE_FILES = 2048
    MAX_MANIFEST_SIZE = 64 * 1024
    MAX_MEMBER_NAME = 512
    MAX_ARCHIVE_SIZE = 128 * 1024 * 1024
    MAX_DEPENDENCIES = 128
    MAX_ID_LENGTH = 64
    MAX_VERSION_LENGTH = 64

    def __init__(self, gl=None, sound=None, settings=None, player=None, gui=None,
                 gc=None, mods_path="mods"):
        self.gl = gl
        self.sound = sound
        self.settings = settings
        self.player = player
        self.gui = gui
        self.garbage_collector = gc
        self.mods_path = os.path.abspath(os.fspath(mods_path))
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
        self._mod_roots = {}
        self._archive_temp_dirs = {}
        self._pending_mod_cleanup = {}
        self._pending_archive_cleanup = set()
        self._closed = False
        self._dispatch_depth = 0
        self._pending_unloads = set()
        self._closing_requested = False
        self._atexit_callback = self.close
        atexit.register(self._atexit_callback)

    def discover(self):
        if not os.path.isdir(self.mods_path):
            return []
        candidates = []
        for entry in sorted(os.listdir(self.mods_path)):
            if entry.startswith("_"):
                continue
            path = os.path.join(self.mods_path, entry)
            if os.path.isfile(path) and entry.endswith((".py", ".mcpymod")):
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
        if self._closed:
            raise RuntimeError("ModLoader is closed")
        self._prepare()
        self._run_phase("pre_init")
        self._retry_pending_cleanups()
        self._refresh_loaded_mods()
        return self.loaded_mods

    def load_remaining(self):
        self.load_pre_init()
        self._run_phase("init")
        self._retry_pending_cleanups()
        self._run_phase("post_init")
        self._retry_pending_cleanups()
        self._refresh_loaded_mods()
        logging.info("Loaded %d mods: %s", len(self.loaded_mods),
                     ", ".join(self.loaded_mods) or "none")
        return self.loaded_mods

    def try_better(self):
        """Legacy entry point that executes the complete lifecycle."""
        return self.load_all()

    def post(self, event, **payload):
        return self.events.post(event, **payload)

    def _begin_dispatch(self):
        self._dispatch_depth += 1

    def _end_dispatch(self):
        self._dispatch_depth -= 1
        if self._dispatch_depth:
            return
        if self._closing_requested:
            self._closing_requested = False
            self._pending_unloads.clear()
            self.close()
            return
        pending = self._pending_unloads
        self._pending_unloads = set()
        for mod_id, _ in reversed(self._ordered[:]):
            if mod_id in pending:
                self.unload_mod(mod_id)

    def _retry_pending_cleanups(self):
        if self._pending_mod_cleanup or self._pending_archive_cleanup:
            python_gc.collect()
        mod_sources = set(self._pending_mod_cleanup.values())
        for mod_id, source in list(self._pending_mod_cleanup.items()):
            if self._cleanup_archive(source):
                self._pending_mod_cleanup.pop(mod_id, None)
        for source in list(self._pending_archive_cleanup - mod_sources):
            self._cleanup_archive(source)

    def _module_for_id(self, mod_id):
        module = self.loaded_mods.get(mod_id)
        if module is not None:
            return module
        return next((module for current_id, module in self._ordered
                     if current_id == mod_id and current_id not in self.failed_mods), None)

    def unload_mod(self, mod_id):
        mod_id = ForgeAPI._valid_id(mod_id)
        module = self._module_for_id(mod_id)
        if module is None and mod_id in self._pending_mod_cleanup:
            source = self._pending_mod_cleanup[mod_id]
            python_gc.collect()
            cleaned = self._cleanup_archive(source)
            if cleaned:
                self._pending_mod_cleanup.pop(mod_id, None)
            return cleaned
        if self._dispatch_depth:
            if module is not None:
                self._pending_unloads.update(self._dependent_closure(mod_id))
                return True
            return False
        if module is None:
            return False
        dependents = [
            dependent for dependent, dependencies in self._dependencies.items()
            if mod_id in dependencies and self._module_for_id(dependent) is not None
        ]
        dependents_cleaned = True
        for dependent in dependents:
            dependents_cleaned = self.unload_mod(dependent) and dependents_cleaned

        self._rollback_mod(mod_id)
        self.loaded_mods.pop(mod_id, None)
        self._mod_roots.pop(mod_id, None)
        self._dependencies.pop(mod_id, None)
        self._ordered = [item for item in self._ordered if item[0] != mod_id]
        cleaned = self._cleanup_module(module)
        if not cleaned:
            self._pending_mod_cleanup[mod_id] = module.__mynnkraft_source__
        else:
            self._pending_mod_cleanup.pop(mod_id, None)
        return cleaned and dependents_cleaned

    def _dependent_closure(self, mod_id):
        result = {mod_id}
        changed = True
        while changed:
            changed = False
            for dependent, dependencies in self._dependencies.items():
                if dependent not in result and any(item in result for item in dependencies):
                    result.add(dependent)
                    changed = True
        return result

    def close(self):
        if self._closed:
            return
        if self._dispatch_depth:
            self._closing_requested = True
            self._pending_unloads.update(
                mod_id for mod_id, _ in self._ordered
                if mod_id not in self.failed_mods
            )
            return
        cleanup_failed = False
        for mod_id in reversed([current_id for current_id, _ in self._ordered]):
            if self._module_for_id(mod_id) is not None:
                try:
                    self.unload_mod(mod_id)
                except Exception:
                    cleanup_failed = True
                    logging.exception("Failed unloading mod %s during shutdown", mod_id)
        python_gc.collect()
        self._retry_pending_cleanups()
        for source in list(self._archive_temp_dirs):
            cleanup_failed = not self._cleanup_archive(source) or cleanup_failed
        self._pending_mod_cleanup = {
            mod_id: source for mod_id, source in self._pending_mod_cleanup.items()
            if source in self._archive_temp_dirs
        }
        if not cleanup_failed and not self._archive_temp_dirs:
            self._closed = True
            atexit.unregister(self._atexit_callback)

    def get_asset_path(self, mod_id, relative_path):
        mod_id = ForgeAPI._valid_id(mod_id)
        root = self._mod_roots.get(mod_id)
        if root is None:
            raise KeyError(f"Unknown mod id: {mod_id}")
        relative_path = os.fspath(relative_path)
        if os.path.isabs(relative_path):
            raise ValueError("Mod asset path must be relative")
        root = os.path.realpath(root)
        target = os.path.realpath(os.path.join(root, relative_path))
        if os.path.commonpath((root, target)) != root:
            raise ValueError("Mod asset path escapes the mod root")
        if not os.path.exists(target):
            raise FileNotFoundError(target)
        return target

    def _import_mod(self, path):
        if path.lower().endswith(".mcpymod"):
            return self._import_archive(path)
        return self._import_python(path, path, os.path.dirname(path), package=False)

    def _import_python(self, entry_path, source_path, root_path, manifest=None,
                       package=False):
        entry_path = os.path.realpath(entry_path)
        source_path = os.path.abspath(source_path)
        root_path = os.path.realpath(root_path)
        provisional = os.path.splitext(os.path.basename(source_path))[0]
        module_name = f"mynnkraft_mod_{provisional}_{uuid.uuid4().hex}"
        spec_options = ({"submodule_search_locations": [os.path.dirname(entry_path)]}
                        if package else {})
        spec = importlib.util.spec_from_file_location(module_name, entry_path,
                                                      **spec_options)
        if spec is None or spec.loader is None:
            raise ImportError(f"Cannot create module spec for {source_path}")
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        try:
            spec.loader.exec_module(module)
        except Exception:
            self._remove_module_namespace(module_name)
            raise
        if manifest is not None:
            module.MOD_INFO = {
                "id": manifest["id"],
                "version": manifest["version"],
                "dependencies": manifest["dependencies"],
            }
        module.__mynnkraft_source__ = source_path
        module.__mynnkraft_fallback_id__ = self._fallback_id(source_path)
        module.__mynnkraft_root__ = root_path
        module.__mynnkraft_module_name__ = module_name
        return module

    def _import_archive(self, archive_path):
        archive_path = os.path.abspath(archive_path)
        self._validate_archive_container(archive_path)
        temporary = tempfile.mkdtemp(prefix="mcpymod_")
        self._archive_temp_dirs[archive_path] = temporary
        try:
            with zipfile.ZipFile(archive_path) as archive:
                self._safe_extract(archive, temporary)
            manifest_path = os.path.join(temporary, "mod.json")
            if not os.path.isfile(manifest_path):
                raise ValueError("Archive must contain mod.json at its root")
            if os.path.getsize(manifest_path) > self.MAX_MANIFEST_SIZE:
                raise ValueError("mod.json is too large")
            with open(manifest_path, "r", encoding="utf-8") as manifest_file:
                raw_manifest = json.load(manifest_file)
            if isinstance(raw_manifest, dict) and "entry" not in raw_manifest:
                raw_manifest = dict(raw_manifest)
                raw_manifest["entry"] = ("mod.py" if os.path.isfile(
                    os.path.join(temporary, "mod.py")) else "__init__.py")
            manifest = self._validate_manifest(raw_manifest)
            entry_path = os.path.realpath(os.path.join(temporary, manifest["entry"]))
            root = os.path.realpath(temporary)
            if os.path.commonpath((root, entry_path)) != root:
                raise ValueError("Manifest entry escapes the archive root")
            if not os.path.isfile(entry_path):
                raise FileNotFoundError(f"Mod entry not found: {manifest['entry']}")
            module = self._import_python(entry_path, archive_path, root, manifest,
                                         package=True)
        except Exception as error:
            self._detach_exception(error)
            if not self._cleanup_archive(archive_path):
                self._pending_archive_cleanup.add(archive_path)
            raise
        return module

    def _validate_manifest(self, manifest):
        if not isinstance(manifest, dict):
            raise TypeError("mod.json must contain a JSON object")
        if not isinstance(manifest.get("id"), str):
            raise TypeError("mod.json id must be a string")
        if not isinstance(manifest.get("version"), str):
            raise TypeError("mod.json version must be a string")
        if "dependencies" not in manifest:
            raise ValueError("mod.json requires dependencies")
        if len(manifest["id"]) > self.MAX_ID_LENGTH:
            raise ValueError("mod.json id is too long")
        mod_id = ForgeAPI._valid_id(manifest["id"])
        version = manifest["version"].strip()
        if not version:
            raise ValueError("mod.json requires a non-empty version")
        if len(version) > self.MAX_VERSION_LENGTH:
            raise ValueError("mod.json version is too long")
        dependencies = manifest["dependencies"]
        if not isinstance(dependencies, list):
            raise TypeError("mod.json dependencies must be a list")
        if len(dependencies) > self.MAX_DEPENDENCIES:
            raise ValueError("mod.json has too many dependencies")
        if not all(isinstance(value, str) for value in dependencies):
            raise TypeError("mod.json dependency ids must be strings")
        if any(len(value) > self.MAX_ID_LENGTH for value in dependencies):
            raise ValueError("mod.json dependency id is too long")
        dependencies = [ForgeAPI._valid_id(value) for value in dependencies]
        entry = manifest.get("entry", "mod.py")
        if not isinstance(entry, str) or not entry.endswith(".py"):
            raise ValueError("mod.json entry must name a Python file")
        normalized = os.path.normpath(entry.replace("/", os.sep).replace("\\", os.sep))
        if os.path.isabs(normalized) or normalized == ".." or normalized.startswith(".." + os.sep):
            raise ValueError("mod.json entry must stay inside the archive")
        if os.path.dirname(normalized):
            raise ValueError("mod.json entry must be at the archive root")
        return {"id": mod_id, "version": version,
                "dependencies": dependencies, "entry": normalized}

    def _validate_archive_container(self, archive_path):
        archive_size = os.path.getsize(archive_path)
        if archive_size > self.MAX_ARCHIVE_BYTES:
            raise ValueError("Mod archive file is too large")
        tail_size = min(archive_size, 65557)
        with open(archive_path, "rb") as archive_file:
            archive_file.seek(archive_size - tail_size)
            tail = archive_file.read(tail_size)

        signature = b"PK\x05\x06"
        offset = tail.rfind(signature)
        record = None
        while offset >= 0:
            if offset + 22 <= len(tail):
                values = struct.unpack_from("<4s4H2LH", tail, offset)
                comment_length = values[-1]
                if archive_size - tail_size + offset + 22 + comment_length == archive_size:
                    record = values
                    break
            offset = tail.rfind(signature, 0, offset)
        if record is None:
            raise zipfile.BadZipFile("Missing ZIP end-of-central-directory record")

        _, disk, central_disk, disk_entries, total_entries, central_size, central_offset, _ = record
        if disk or central_disk or disk_entries != total_entries:
            raise ValueError("Multi-disk mod archives are not supported")
        if total_entries == 0xFFFF or central_size == 0xFFFFFFFF or central_offset == 0xFFFFFFFF:
            raise ValueError("ZIP64 mod archives are not supported")
        if total_entries > self.MAX_ARCHIVE_FILES:
            raise ValueError("Mod archive contains too many files")
        if central_size > self.MAX_CENTRAL_DIRECTORY_SIZE:
            raise ValueError("Mod archive central directory is too large")
        eocd_offset = archive_size - tail_size + offset
        if eocd_offset >= 20:
            with open(archive_path, "rb") as archive_file:
                archive_file.seek(eocd_offset - 20)
                if archive_file.read(4) == b"PK\x06\x07":
                    raise ValueError("ZIP64 mod archives are not supported")
        if central_offset + central_size > eocd_offset:
            raise zipfile.BadZipFile("Invalid ZIP central directory")

    def _safe_extract(self, archive, destination):
        infos = archive.infolist()
        if len(infos) > self.MAX_ARCHIVE_FILES:
            raise ValueError("Mod archive contains too many files")
        if sum(info.file_size for info in infos) > self.MAX_ARCHIVE_SIZE:
            raise ValueError("Mod archive is too large when extracted")

        destination = os.path.realpath(destination)
        seen = set()
        extracted_size = 0
        for info in infos:
            if self._has_zip64_extra(info.extra):
                raise ValueError("ZIP64 mod archives are not supported")
            if info.compress_type not in (zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED):
                raise ValueError(f"Unsupported ZIP compression: {info.compress_type}")
            if len(info.filename) > self.MAX_MEMBER_NAME:
                raise ValueError("Mod archive member name is too long")
            name = info.filename.replace("\\", "/")
            parts = [part for part in name.split("/") if part not in ("", ".")]
            if (not parts or name.startswith("/") or any(part == ".." for part in parts)
                    or any(":" in part or part.rstrip(" .") != part
                           or self._is_windows_reserved(part) for part in parts)):
                raise ValueError(f"Unsafe archive path: {info.filename}")
            key = "/".join(parts).lower()
            if key in seen:
                raise ValueError(f"Duplicate archive path: {info.filename}")
            seen.add(key)
            mode = info.external_attr >> 16
            if stat.S_ISLNK(mode):
                raise ValueError(f"Archive links are not allowed: {info.filename}")
            if info.flag_bits & 0x1:
                raise ValueError("Encrypted mod archives are not supported")
            if self._zip64_local_member(archive, info):
                raise ValueError("ZIP64 mod archives are not supported")

            target = os.path.realpath(os.path.join(destination, *parts))
            if os.path.commonpath((destination, target)) != destination:
                raise ValueError(f"Unsafe archive path: {info.filename}")
            if info.is_dir():
                os.makedirs(target, exist_ok=True)
                continue
            os.makedirs(os.path.dirname(target), exist_ok=True)
            with archive.open(info) as source, open(target, "wb") as output:
                while True:
                    chunk = source.read(1024 * 1024)
                    if not chunk:
                        break
                    extracted_size += len(chunk)
                    if extracted_size > self.MAX_ARCHIVE_SIZE:
                        raise ValueError("Mod archive exceeded its extraction limit")
                    output.write(chunk)

    @staticmethod
    def _is_windows_reserved(component):
        is_reserved = getattr(os.path, "isreserved", None)
        if is_reserved is not None and is_reserved(component):
            return True
        if any(ord(character) < 32 or character in '<>"|?*' for character in component):
            return True
        stem = component.split(".", 1)[0].rstrip(" ").upper()
        return (stem in {"CON", "PRN", "AUX", "NUL", "CONIN$", "CONOUT$"}
                or stem in {f"COM{index}" for index in range(1, 10)}
                or stem in {f"LPT{index}" for index in range(1, 10)}
                or stem in {f"COM{index}" for index in "¹²³"}
                or stem in {f"LPT{index}" for index in "¹²³"})

    @staticmethod
    def _zip64_local_member(archive, info):
        current = archive.fp.tell()
        try:
            archive.fp.seek(info.header_offset)
            header = archive.fp.read(30)
            if len(header) != 30 or header[:4] != b"PK\x03\x04":
                raise zipfile.BadZipFile(f"Invalid local header: {info.filename}")
            values = struct.unpack("<4s5H3L2H", header)
            compressed_size, file_size = values[7], values[8]
            name_length, extra_length = values[9], values[10]
            archive.fp.seek(name_length, os.SEEK_CUR)
            extra = archive.fp.read(extra_length)
            return (ModLoader._has_zip64_extra(extra)
                    or compressed_size == 0xFFFFFFFF or file_size == 0xFFFFFFFF)
        finally:
            archive.fp.seek(current)

    @staticmethod
    def _has_zip64_extra(extra):
        offset = 0
        while offset + 4 <= len(extra):
            field_id, field_size = struct.unpack_from("<HH", extra, offset)
            if field_id == 0x0001:
                return True
            offset += 4 + field_size
        return False

    def _prepare(self):
        if self._prepared:
            return
        modules = []
        for path in self.discover():
            try:
                modules.append(self._import_mod(path))
            except Exception as error:
                diagnostic = traceback.format_exc()
                self.failed_mods[path] = self._detach_exception(error)
                logging.error("Failed loading mod %s\n%s", path, diagnostic)
        self._ordered, self._dependencies = self._dependency_order(modules)
        valid_modules = {module for _, module in self._ordered}
        for module in modules:
            if module not in valid_modules:
                self._cleanup_module(module)
        self._mod_roots = {
            mod_id: module.__mynnkraft_root__ for mod_id, module in self._ordered
        }
        self._prepared = True

    def _run_phase(self, phase):
        if phase in self._completed_phases:
            return
        self._begin_dispatch()
        try:
            for mod_id, module in self._ordered:
                if mod_id in self.failed_mods or mod_id in self._pending_unloads:
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
                    diagnostic = traceback.format_exc()
                    self._mark_failed(mod_id, error)
                    logging.error("Mod %s failed during %s\n%s",
                                  mod_id, phase, diagnostic)
                finally:
                    self.current_mod = None
        finally:
            module = None
            hook = None
            self._completed_phases.add(phase)
            self._end_dispatch()

    def _mark_failed(self, mod_id, error):
        if mod_id in self.failed_mods:
            return
        self.failed_mods[mod_id] = self._detach_exception(error)
        for dependent, dependencies in list(self._dependencies.items()):
            if mod_id in dependencies:
                self._mark_failed(
                    dependent, RuntimeError(f"Dependency {mod_id} failed")
                )
        module = next((module for current_id, module in self._ordered
                       if current_id == mod_id), None)
        self._rollback_mod(mod_id)
        self._mod_roots.pop(mod_id, None)
        if module is not None:
            cleaned = self._cleanup_module(module)
            if not cleaned:
                self._pending_mod_cleanup[mod_id] = module.__mynnkraft_source__
        self.loaded_mods.pop(mod_id, None)
        self._dependencies.pop(mod_id, None)
        self._ordered = [item for item in self._ordered if item[0] != mod_id]

    def _rollback_mod(self, mod_id):
        self.events.remove_owner(mod_id)
        for undo in reversed(self._undo_actions.pop(mod_id, ())):
            try:
                undo()
            except Exception:
                logging.exception("Failed rolling back mod %s", mod_id)

    def _cleanup_module(self, module):
        module_name = getattr(module, "__mynnkraft_module_name__", module.__name__)
        self._remove_module_namespace(module_name)
        source = getattr(module, "__mynnkraft_source__", "")
        cleaned = self._cleanup_archive(source)
        if not cleaned:
            self._pending_archive_cleanup.add(source)
        return cleaned

    def _cleanup_archive(self, source):
        path = self._archive_temp_dirs.get(source)
        if path is None:
            self._pending_archive_cleanup.discard(source)
            return True
        try:
            shutil.rmtree(path)
        except FileNotFoundError:
            pass
        except Exception:
            logging.exception("Failed deleting extracted mod %s", source)
            return False
        self._archive_temp_dirs.pop(source, None)
        self._pending_archive_cleanup.discard(source)
        return True

    @staticmethod
    def _detach_exception(error):
        pending = [error]
        seen = set()
        while pending:
            current = pending.pop()
            if id(current) in seen:
                continue
            seen.add(id(current))
            error_traceback = current.__traceback__
            if error_traceback is not None:
                traceback.clear_frames(error_traceback)
                current.__traceback__ = None
            if current.__cause__ is not None:
                pending.append(current.__cause__)
            if current.__context__ is not None:
                pending.append(current.__context__)
            pending.extend(getattr(current, "exceptions", ()))
        return ModLoader._copy_exception(error)

    @staticmethod
    def _copy_exception(error, seen=None):
        if seen is None:
            seen = {}
        if id(error) in seen:
            return seen[id(error)] or RuntimeError("cyclic exception reference")
        seen[id(error)] = None
        try:
            message = str(error)
        except Exception:
            message = type(error).__name__
        children = getattr(error, "exceptions", None)
        try:
            if children is not None:
                copied = BaseExceptionGroup(message, [
                    ModLoader._copy_exception(child, seen) for child in children
                ])
            else:
                exception_type = type(error) if type(error).__module__ == "builtins" else RuntimeError
                copied = exception_type(message)
        except Exception:
            copied = RuntimeError(f"{type(error).__name__}: {message}")
        seen[id(error)] = copied
        if error.__cause__ is not None:
            copied.__cause__ = ModLoader._copy_exception(error.__cause__, seen)
        if error.__context__ is not None:
            copied.__context__ = ModLoader._copy_exception(error.__context__, seen)
        copied.__suppress_context__ = error.__suppress_context__
        return copied

    @staticmethod
    def _remove_module_namespace(module_name):
        for imported_name in list(sys.modules):
            if imported_name == module_name or imported_name.startswith(module_name + "."):
                sys.modules.pop(imported_name, None)

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
                self.failed_mods[source] = self._detach_exception(error)

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
