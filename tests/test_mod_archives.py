import json
import logging
import os
import stat
import struct
import sys
import tempfile
import unittest
import warnings
import zipfile
from types import SimpleNamespace
from unittest import mock

from game.Mod.forge.mod_loader import ModLoader


class ModArchiveTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.previous_logging_threshold = logging.root.manager.disable
        logging.disable(logging.CRITICAL)

    @classmethod
    def tearDownClass(cls):
        logging.disable(cls.previous_logging_threshold)

    def test_loads_manifest_entry_relative_import_and_asset(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "example.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "archive_example",
                    "version": "1.2.3",
                    "dependencies": [],
                    "entry": "mod.py",
                }))
                package.writestr("helper.py", "VALUE = 'relative import works'\n")
                package.writestr(
                    "mod.py",
                    "from .helper import VALUE\n"
                    "def pre_init(api):\n"
                    "    path = api.get_asset_path('assets/message.txt')\n"
                    "    with open(path, encoding='utf-8') as asset:\n"
                    "        api.scene.trace.append((VALUE, asset.read()))\n",
                )
                package.writestr("assets/message.txt", "bundled asset works")

            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loaded = loader.load_all()

            self.assertEqual(set(loaded), {"archive_example"})
            self.assertEqual(
                scene.trace,
                [("relative import works", "bundled asset works")],
            )
            self.assertEqual(loaded["archive_example"].MOD_INFO["version"], "1.2.3")
            loader.close()

    def test_unload_removes_registrations_modules_and_extracted_files(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "unloadable.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "unloadable",
                    "version": "1.0",
                    "dependencies": [],
                    "entry": "mod.py",
                }))
                package.writestr(
                    "mod.py",
                    "def pre_init(api):\n"
                    "    api.register_entity('archive_entity', lambda scene: object())\n"
                    "    api.subscribe('probe', lambda scene: scene.trace.append('listener'))\n",
                )

            scene = SimpleNamespace(
                trace=[], mod_entity_types={},
                entity_types=lambda: {},
            )
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loaded = loader.load_all()
            module = loaded["unloadable"]
            extracted_root = module.__mynnkraft_root__
            module_name = module.__mynnkraft_module_name__

            self.assertIn("archive_entity", scene.mod_entity_types)
            self.assertTrue(os.path.isdir(extracted_root))
            self.assertIn(module_name, sys.modules)
            self.assertTrue(loader.unload_mod("unloadable"))
            self.assertNotIn("archive_entity", scene.mod_entity_types)
            self.assertNotIn(module_name, sys.modules)
            self.assertFalse(os.path.exists(extracted_root))
            loader.post("probe", scene=scene)
            self.assertEqual(scene.trace, [])

    def test_manifest_without_entry_falls_back_to_init(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "init_entry.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "init_entry",
                    "version": "1.0",
                    "dependencies": [],
                }))
                package.writestr(
                    "__init__.py",
                    "def pre_init(api): api.scene.trace.append('init loaded')\n",
                )

            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loaded = loader.load_all()

            self.assertEqual(set(loaded), {"init_entry"})
            self.assertEqual(scene.trace, ["init loaded"])
            loader.close()

    def test_archive_dependencies_share_lifecycle_with_legacy_mods(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "base.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'base', 'version': '1.0'}\n"
                    "def pre_init(api): api.scene.trace.append('base:pre')\n"
                    "def init(api): api.scene.trace.append('base:init')\n"
                )
            archive = os.path.join(mods_path, "dependent.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "dependent",
                    "version": "2.0",
                    "dependencies": ["base"],
                }))
                package.writestr(
                    "mod.py",
                    "MOD_INFO = {'id': 'ignored_code_id'}\n"
                    "def pre_init(api): api.scene.trace.append('dependent:pre')\n"
                    "def init(api): api.scene.trace.append('dependent:init')\n",
                )

            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loaded = loader.load_all()

            self.assertEqual(set(loaded), {"base", "dependent"})
            self.assertEqual(scene.trace, [
                "base:pre", "dependent:pre", "base:init", "dependent:init",
            ])
            self.assertNotIn("ignored_code_id", loaded)
            loader.close()

    def test_rejects_archive_path_traversal_before_writing(self):
        with tempfile.TemporaryDirectory() as root:
            mods_path = os.path.join(root, "mods")
            extraction_parent = os.path.join(root, "extracted")
            os.makedirs(mods_path)
            os.makedirs(extraction_parent)
            archive = os.path.join(mods_path, "unsafe.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "unsafe", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
                package.writestr("../escaped.txt", "must not be written")

            old_tempdir = tempfile.tempdir
            tempfile.tempdir = extraction_parent
            try:
                loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                                   mods_path=mods_path)
                loaded = loader.load_all()
                loader.close()
            finally:
                tempfile.tempdir = old_tempdir

            self.assertEqual(loaded, {})
            self.assertIn(archive, loader.failed_mods)
            self.assertFalse(os.path.exists(os.path.join(extraction_parent, "escaped.txt")))

    def test_asset_paths_cannot_escape_extracted_root(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "asset_escape.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "asset_escape", "version": "1.0", "dependencies": [],
                }))
                package.writestr(
                    "mod.py",
                    "def pre_init(api): api.get_asset_path('../outside.txt')\n",
                )

            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            loaded = loader.load_all()

            self.assertEqual(loaded, {})
            self.assertIsInstance(loader.failed_mods["asset_escape"], ValueError)
            self.assertIsNone(loader.failed_mods["asset_escape"].__traceback__)
            loader.close()

    def test_failed_relative_import_cannot_poison_reloaded_archive(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "reload.mcpymod")

            def write_archive(value, fail):
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr("mod.json", json.dumps({
                        "id": "reload", "version": "1.0", "dependencies": [],
                    }))
                    package.writestr("helper.py", f"VALUE = {value!r}\n")
                    package.writestr(
                        "mod.py",
                        "from .helper import VALUE\n"
                        + ("raise RuntimeError('first import fails')\n" if fail else
                           "def pre_init(api): api.scene.trace.append(VALUE)\n"),
                    )

            write_archive("stale", True)
            first = ModLoader(gl=SimpleNamespace(trace=[], mod_entity_types={}),
                              mods_path=mods_path)
            self.assertEqual(first.load_all(), {})
            first.close()

            write_archive("fresh", False)
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            second = ModLoader(gl=scene, mods_path=mods_path)
            self.assertEqual(set(second.load_all()), {"reload"})
            self.assertEqual(scene.trace, ["fresh"])
            second.close()

    @unittest.skipUnless(os.name == "nt", "Windows device-name behavior")
    def test_rejects_windows_device_names(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "device.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "device", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
                package.writestr("assets/COM¹.txt", "not a normal file")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            self.assertEqual(loader.load_all(), {})
            self.assertIn(archive, loader.failed_mods)
            self.assertTrue(ModLoader._is_windows_reserved("NUL .txt"))
            loader.close()

    def test_unload_cleanup_is_independent_of_current_working_directory(self):
        original_cwd = os.getcwd()
        with tempfile.TemporaryDirectory() as root:
            mods_path = os.path.join(root, "mods")
            elsewhere = os.path.join(root, "elsewhere")
            os.makedirs(mods_path)
            os.makedirs(elsewhere)
            archive = os.path.join(mods_path, "cwd.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "cwd", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
            try:
                os.chdir(root)
                loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                                   mods_path="mods")
                module = loader.load_all()["cwd"]
                extracted_root = module.__mynnkraft_root__
                os.chdir(elsewhere)
                self.assertTrue(loader.unload_mod("cwd"))
                self.assertFalse(os.path.exists(extracted_root))
            finally:
                os.chdir(original_cwd)

    def test_manifest_rejects_non_string_scalar_fields(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "invalid_manifest.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": None, "version": False, "dependencies": [123],
                }))
                package.writestr("mod.py", "pass\n")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            self.assertEqual(loader.load_all(), {})
            self.assertIn(archive, loader.failed_mods)
            loader.close()

    def test_close_is_terminal(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "legacy.py"), "w", encoding="utf-8") as file:
                file.write("MOD_INFO = {'id': 'legacy', 'version': '1.0'}\n")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            loader.close()
            with self.assertRaises(RuntimeError):
                loader.load_all()

    def test_loose_python_mod_keeps_non_package_import_semantics(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "legacy.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'legacy', 'version': '1.0'}\n"
                    "def pre_init(api): api.scene.trace.append(__package__)\n"
                )
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loader.load_all()
            self.assertEqual(scene.trace, [""])
            loader.close()

    def test_rejects_unsupported_or_ambiguous_archive_members(self):
        cases = ("symlink", "bzip2", "case_duplicate", "file_limit")
        for case in cases:
            with self.subTest(case=case), tempfile.TemporaryDirectory() as mods_path:
                archive = os.path.join(mods_path, f"{case}.mcpymod")
                with zipfile.ZipFile(archive, "w") as package:
                    package.writestr("mod.json", json.dumps({
                        "id": case, "version": "1.0", "dependencies": [],
                    }))
                    package.writestr("mod.py", "pass\n")
                    if case == "symlink":
                        link = zipfile.ZipInfo("assets/link")
                        link.create_system = 3
                        link.external_attr = (stat.S_IFLNK | 0o777) << 16
                        package.writestr(link, "target")
                    elif case == "bzip2":
                        package.writestr("assets/data.bin", b"data",
                                         compress_type=zipfile.ZIP_BZIP2)
                    elif case == "case_duplicate":
                        package.writestr("assets/Name.txt", "first")
                        package.writestr("assets/name.txt", "second")
                    else:
                        package.writestr("third.txt", "over configured limit")

                loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                                   mods_path=mods_path)
                if case == "file_limit":
                    loader.MAX_ARCHIVE_FILES = 2
                self.assertEqual(loader.load_all(), {})
                self.assertIn(archive, loader.failed_mods)
                loader.close()

    def test_legacy_directory_mod_remains_supported(self):
        with tempfile.TemporaryDirectory() as mods_path:
            directory = os.path.join(mods_path, "directory_mod")
            os.makedirs(directory)
            with open(os.path.join(directory, "mod.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'directory_mod', 'version': '1.0'}\n"
                    "def pre_init(api): api.scene.trace.append('directory loaded')\n"
                )
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            self.assertEqual(set(loader.load_all()), {"directory_mod"})
            self.assertEqual(scene.trace, ["directory loaded"])
            loader.close()

    def test_event_unload_is_deferred_and_skips_queued_callbacks(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "a.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'a', 'version': '1.0'}\n"
                    "def pre_init(api):\n"
                    "    api.subscribe('probe', lambda scene: "
                    "(scene.trace.append('a'), api.loader.unload_mod('a')))\n"
                )
            with open(os.path.join(mods_path, "b.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'b', 'version': '1.0', 'dependencies': ['a']}\n"
                    "def pre_init(api):\n"
                    "    api.subscribe('probe', lambda scene: scene.trace.append('b'))\n"
                )
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loader.load_all()
            loader.post("probe", scene=scene)
            self.assertEqual(scene.trace, ["a"])
            self.assertNotIn("a", loader.loaded_mods)
            self.assertNotIn("b", loader.loaded_mods)
            loader.close()

    def test_lifecycle_unload_skips_later_mod_hook(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "a.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'a', 'version': '1.0'}\n"
                    "def init(api):\n"
                    "    api.scene.trace.append('a:init')\n"
                    "    api.loader.unload_mod('b')\n"
                )
            with open(os.path.join(mods_path, "b.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'b', 'version': '1.0'}\n"
                    "def init(api): api.scene.trace.append('b:init')\n"
                )
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            loaded = loader.load_all()
            self.assertEqual(scene.trace, ["a:init"])
            self.assertEqual(set(loaded), {"a"})
            loader.close()

    def test_failed_dependency_isolated_before_dependent_hook(self):
        with tempfile.TemporaryDirectory() as mods_path:
            with open(os.path.join(mods_path, "base.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'base', 'version': '1.0'}\n"
                    "def pre_init(api): raise RuntimeError('base failed')\n"
                )
            with open(os.path.join(mods_path, "dependent.py"), "w", encoding="utf-8") as file:
                file.write(
                    "MOD_INFO = {'id': 'dependent', 'version': '1.0', "
                    "'dependencies': ['base']}\n"
                    "def pre_init(api): api.scene.trace.append('must not run')\n"
                )
            scene = SimpleNamespace(trace=[], mod_entity_types={})
            loader = ModLoader(gl=scene, mods_path=mods_path)
            self.assertEqual(loader.load_all(), {})
            self.assertEqual(scene.trace, [])
            self.assertIn("base", loader.failed_mods)
            self.assertIn("dependent", loader.failed_mods)
            loader.close()

    def test_rejects_zip64_locator_even_without_classic_sentinels(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "zip64_locator.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "zip64_locator", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
            with open(archive, "rb") as file:
                data = file.read()
            eocd = data.rfind(b"PK\x05\x06")
            locator = struct.pack("<4sLQL", b"PK\x06\x07", 0, 0, 1)
            with open(archive, "wb") as file:
                file.write(data[:eocd] + locator + data[eocd:])

            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            self.assertEqual(loader.load_all(), {})
            self.assertIn("ZIP64", str(loader.failed_mods[archive]))
            loader.close()

    def test_manifest_size_is_bounded_before_json_parsing(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "large_manifest.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "large_manifest", "version": "x" * 100,
                    "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            loader.MAX_MANIFEST_SIZE = 32
            self.assertEqual(loader.load_all(), {})
            self.assertIn("too large", str(loader.failed_mods[archive]))
            loader.close()

    def test_rejects_zip64_local_member_without_locator(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "zip64_member.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "zip64_member", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
                with package.open("assets/data.bin", "w", force_zip64=True) as output:
                    output.write(b"data")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            self.assertEqual(loader.load_all(), {})
            self.assertIn("ZIP64", str(loader.failed_mods[archive]))
            loader.close()

    def test_failed_unload_cleanup_can_be_retried_by_mod_id(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "retry_cleanup.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "retry_cleanup", "version": "1.0", "dependencies": [],
                }))
                package.writestr("mod.py", "pass\n")
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            module = loader.load_all()["retry_cleanup"]
            extracted_root = module.__mynnkraft_root__
            with mock.patch("game.Mod.forge.mod_loader.shutil.rmtree",
                            side_effect=PermissionError("locked")):
                self.assertFalse(loader.unload_mod("retry_cleanup"))
            self.assertTrue(os.path.isdir(extracted_root))
            self.assertTrue(loader.unload_mod("retry_cleanup"))
            self.assertFalse(os.path.exists(extracted_root))
            loader.close()

    def test_failed_hook_releases_chained_tracebacks_and_extracted_files(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "failed_hook.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "failed_hook", "version": "1.0", "dependencies": [],
                }))
                package.writestr("assets/data.txt", "held open during failure")
                package.writestr(
                    "mod.py",
                    "HANDLE = None\n"
                    "def pre_init(api):\n"
                    "    global HANDLE\n"
                    "    HANDLE = open(api.get_asset_path('assets/data.txt'), 'rb')\n"
                    "    try:\n"
                    "        raise ValueError('cause')\n"
                    "    except ValueError as cause:\n"
                    "        raise RuntimeError('hook failed') from cause\n",
                )
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                self.assertEqual(loader.load_all(), {})
            failure = loader.failed_mods["failed_hook"]
            self.assertIsNone(failure.__traceback__)
            self.assertIsNotNone(failure.__cause__)
            self.assertIsNone(failure.__cause__.__traceback__)
            self.assertEqual(loader._archive_temp_dirs, {})
            self.assertEqual(loader._pending_mod_cleanup, {})
            loader.close()

    @unittest.skipUnless(os.name == "nt", "Windows open-file cleanup behavior")
    def test_module_owned_open_file_cleanup_retries_by_mod_id(self):
        with tempfile.TemporaryDirectory() as mods_path:
            archive = os.path.join(mods_path, "open_file.mcpymod")
            with zipfile.ZipFile(archive, "w") as package:
                package.writestr("mod.json", json.dumps({
                    "id": "open_file", "version": "1.0", "dependencies": [],
                }))
                package.writestr("assets/data.txt", "open")
                package.writestr(
                    "mod.py",
                    "HANDLE = None\n"
                    "def pre_init(api):\n"
                    "    global HANDLE\n"
                    "    HANDLE = open(api.get_asset_path('assets/data.txt'), 'rb')\n",
                )
            loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}),
                               mods_path=mods_path)
            module = loader.load_all()["open_file"]
            extracted_root = module.__mynnkraft_root__
            self.assertFalse(loader.unload_mod("open_file"))
            del module
            with warnings.catch_warnings():
                warnings.simplefilter("ignore", ResourceWarning)
                self.assertTrue(loader.unload_mod("open_file"))
            self.assertFalse(os.path.exists(extracted_root))
            loader.close()

    def test_exception_group_children_are_detached(self):
        loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}), mods_path="missing")
        try:
            raise ValueError("child")
        except ValueError as child:
            group = ExceptionGroup("group", [child])
        detached = loader._detach_exception(group)
        self.assertIsNone(detached.__traceback__)
        self.assertIsNone(detached.exceptions[0].__traceback__)
        loader.close()

    def test_stored_failure_does_not_retain_exception_argument_objects(self):
        loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}), mods_path="missing")
        with tempfile.TemporaryFile() as handle:
            detached = loader._detach_exception(RuntimeError(handle))
            self.assertIsInstance(detached, RuntimeError)
            self.assertEqual(len(detached.args), 1)
            self.assertIsInstance(detached.args[0], str)
        loader.close()

    def test_mod_defined_exception_constructor_is_not_reused(self):
        class ModError(Exception):
            retained = None

            def __init__(self, message):
                super().__init__(message)
                self.handle = self.retained

        loader = ModLoader(gl=SimpleNamespace(mod_entity_types={}), mods_path="missing")
        with tempfile.TemporaryFile() as handle:
            ModError.retained = handle
            detached = loader._detach_exception(ModError("custom"))
            self.assertIs(type(detached), RuntimeError)
            self.assertFalse(hasattr(detached, "handle"))
            self.assertEqual(detached.args, ("custom",))
            ModError.retained = None
        loader.close()

    def test_zip64_central_extra_is_detected(self):
        extra = struct.pack("<HHQQ", 0x0001, 16, 4, 4)
        self.assertTrue(ModLoader._has_zip64_extra(extra))


if __name__ == "__main__":
    unittest.main()
