"""FBX loader using pyassimp."""
import os

import numpy as np

try:
    import pyassimp as assimp
    import pyassimp.types as types
    HAS_ASSIMP = True
except ImportError:
    try:
        import assimp
        import assimp.types
        HAS_ASSIMP = True
    except ImportError:
        HAS_ASSIMP = False


def _read_material_names(scene):
    """Read material names from the aiScene."""
    if not scene or not scene.materials:
        return []
    
    names = []
    for mat in scene.materials:
        if mat and mat.name:
            names.append(mat.name)
        else:
            names.append("material_{}".format(len(names)))
    return names


def load_fbx(path, flags=None):
    if not HAS_ASSIMP:
        raise RuntimeError("pyassimp not available. Install with: pip install pyassimp")
    
    scene = assimp.load(path)
    if not scene:
        raise RuntimeError('assimp failed to load file')
    
    mat_names = _read_material_names(scene)
    if mat_names:
        print(f"  FBX materials: {mat_names}")
    
    meshes = []
    for mesh in scene.meshes:
        nv = len(mesh.vertices) // 3
        
        verts = np.array(mesh.vertices, dtype=np.float32).reshape(-1, 3)
        
        norms = None
        if mesh.normals and len(mesh.normals) > 0:
            norms = np.array(mesh.normals, dtype=np.float32).reshape(-1, 3)
        
        uvs = None
        if mesh.texturecoords and len(mesh.texturecoords) > 0:
            uv_data = np.array(mesh.texturecoords[0], dtype=np.float32)
            if len(uv_data) >= 2:
                uvs = uv_data.reshape(-1, 2)[:, :2]
                unique_u = len(np.unique(np.round(uvs[:, 0], 4)))
                unique_v = len(np.unique(np.round(uvs[:, 1], 4)))
                print(f"  UV channel 0: {unique_u}x{unique_v} unique, "
                      f"U=[{uvs[:, 0].min():.4f},{uvs[:, 0].max():.4f}], "
                      f"V=[{uvs[:, 1].min():.4f},{uvs[:, 1].max():.4f}]")
        
        mat_idx = mesh.materialindex
        mat_label = mat_names[mat_idx] if mat_idx < len(mat_names) else "material_{}".format(mat_idx)
        
        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': uvs,
            'all_uvs': {0: uvs} if uvs is not None else {},
            'num_vertices': nv,
            'num_faces': len(mesh.faces) if hasattr(mesh, 'faces') else nv // 3,
            'material_index': mat_idx,
            'material_name': mat_label,
        })
    
    assimp.release()
    return meshes
