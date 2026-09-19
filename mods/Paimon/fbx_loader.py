"""FBX loader using pyassimp (proper structure handling)."""
import os

import numpy as np
import pyassimp
from pyassimp import postprocess


def load_fbx(path, flags=postprocess.aiProcess_Triangulate | postprocess.aiProcess_GenSmoothNormals):
    """Load FBX model using pyassimp.
    
    Returns list of mesh dicts with vertices, normals, uvs, indices, and material info.
    """
    abs_path = os.path.abspath(path)
    
    # Import the scene
    scene = pyassimp.load(abs_path, processing=flags)
    
    if not scene:
        raise RuntimeError(f'pyassimp failed to import {path}')
    
    meshes = []
    
    # Process each mesh in the scene
    for mesh in scene.meshes:
        nv = len(mesh.vertices)
        
        # Vertices (already transformed by PreTransformVertices if used)
        verts = np.array(mesh.vertices, dtype=np.float32)
        
        # Normals
        norms = None
        if mesh.normals is not None and len(mesh.normals) > 0:
            norms = np.array(mesh.normals, dtype=np.float32)
        
        # UV coordinates - get first UV channel
        all_uvs = {}
        if mesh.texturecoords:
            for ch, uv_channel in enumerate(mesh.texturecoords):
                if uv_channel is not None and len(uv_channel) > 0:
                    # Take only x,y components for 2D UVs
                    uv_data = np.array([[uv[0], uv[1]] for uv in uv_channel], dtype=np.float32)
                    all_uvs[ch] = uv_data
        
        primary_uvs = all_uvs.get(0, None)
        
        # Face indices - properly read from aiFace structures
        indices = []
        for face in mesh.faces:
            for idx in face.indices:
                indices.append(idx)
        indices = np.array(indices, dtype=np.uint32)
        
        # Material info
        mat_idx = mesh.materialindex
        mat_name = mesh.material.name if mesh.material else f"material_{mat_idx}"
        
        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': primary_uvs,
            'all_uvs': all_uvs,
            'indices': indices,
            'num_vertices': nv,
            'num_faces': len(mesh.faces),
            'material_index': mat_idx,
            'material_name': mat_name,
        })
    
    # Release the scene
    pyassimp.release(scene)
    
    return meshes
