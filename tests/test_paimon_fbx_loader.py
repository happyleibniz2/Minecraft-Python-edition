import importlib.util
import os
import unittest


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOADER_PATH = os.path.join(ROOT, "mods", "Paimon", "fbx_loader.py")
FBX_PATH = os.path.join(
    ROOT, "mods", "Paimon", "assets", "Paimon", "Default",
    "NPC_Kanban_Paimon.fbx",
)


class PaimonFbxLoaderTests(unittest.TestCase):
    def test_reads_indexed_faces_from_the_assimp_mesh_layout(self):
        spec = importlib.util.spec_from_file_location("test_paimon_fbx_loader", LOADER_PATH)
        loader = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loader)

        meshes = loader.load_fbx(FBX_PATH)

        self.assertEqual(len(meshes), 5)
        for mesh in meshes:
            self.assertGreater(mesh["num_faces"], 0)
            self.assertEqual(len(mesh["indices"]), mesh["num_faces"] * 3)
            self.assertLess(int(mesh["indices"].max()), mesh["num_vertices"])


if __name__ == "__main__":
    unittest.main()
