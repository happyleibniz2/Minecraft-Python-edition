import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Materials whose Unity material has no _MainTex; they stay untextured on
# purpose and must resolve to an empty mapping.
VESNA_UNTEXTURED = {"Avatar_Default_Mat"}


def _load_mod(name):
    path = os.path.join(ROOT, "mods", name, "mod.py")
    spec = importlib.util.spec_from_file_location(f"test_mod_{name}", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class ModModelTests(unittest.TestCase):
    def test_paimon_model_loads_and_textures_resolve(self):
        mod = _load_mod("Paimon")
        meshes = mod._load_fbx_loader()(mod.FBX_PATH)

        self.assertEqual(len(meshes), 5)
        for mesh_index, mesh in enumerate(meshes):
            self.assertGreater(mesh["num_faces"], 0)
            self.assertEqual(len(mesh["indices"]), mesh["num_faces"] * 3)
            self.assertLess(int(mesh["indices"].max()), mesh["num_vertices"])
            self.assertIsNotNone(mesh["material_name"])

            texture = mod._texture_filename(mesh, mesh_index)
            self.assertTrue(
                texture,
                f"Paimon mesh {mesh_index} ({mesh['material_name']}) "
                f"has no texture mapping")
            path = os.path.join(mod.TEX_DIR, texture)
            self.assertTrue(
                os.path.isfile(path),
                f"Paimon mesh {mesh_index} texture missing: {path}")

    def test_vesna_model_loads_and_textures_resolve(self):
        mod = _load_mod("Vesna")
        meshes = mod._load_fbx_loader()(mod.FBX_PATH)

        self.assertEqual(len(meshes), 13)
        for mesh_index, mesh in enumerate(meshes):
            self.assertGreater(mesh["num_faces"], 0)
            self.assertEqual(len(mesh["indices"]), mesh["num_faces"] * 3)
            self.assertLess(int(mesh["indices"].max()), mesh["num_vertices"])
            self.assertIsNotNone(mesh["material_name"])

            texture = mod._texture_filename(mesh, mesh_index)
            if mesh["material_name"] in VESNA_UNTEXTURED:
                self.assertFalse(
                    texture,
                    f"Vesna mesh {mesh_index} should stay untextured, "
                    f"got {texture!r}")
                continue
            self.assertTrue(
                texture,
                f"Vesna mesh {mesh_index} ({mesh['material_name']}) "
                f"has no texture mapping")
            path = os.path.join(mod.TEX_DIR, texture)
            self.assertTrue(
                os.path.isfile(path),
                f"Vesna mesh {mesh_index} texture missing: {path}")


if __name__ == "__main__":
    unittest.main()
