"""FBX loader using pyassimp (proper structure handling)."""
import os

import numpy as np
import pyassimp
from pyassimp import postprocess


# aiProcess flags - add Debone to avoid bone-related crashes
AI_PROCESS_DEBONE = 0x40000000

def load_fbx(path, flags=postprocess.aiProcess_Triangulate | postprocess.aiProcess_GenSmoothNormals | AI_PROCESS_DEBONE | postprocess.aiProcess_PreTransformVertices):
    """Load FBX model using pyassimp.
    
    Returns list of mesh dicts with vertices, normals, uvs, indices, and material info.
    
    Uses aiProcess_Debone to remove bones (avoids bone pointer issues)
    and aiProcess_PreTransformVertices to bake node transforms.
    """
    abs_path = os.path.abspath(path)
    
    # Import the scene - pyassimp.load returns a context manager
    with pyassimp.load(abs_path, processing=flags) as scene:
        
        if not scene:
            raise RuntimeError(f'pyassimp failed to import {path}')
        
        meshes = []
        
        # Read material names from scene materials
        material_names = []
        for mat in scene.materials:
            try:
                # Try to get name from material properties
                name = "default"
                if hasattr(mat, 'name') and mat.name:
                    name = os.path.basename(str(mat.name))
                elif hasattr(mat, 'properties'):
                    for prop in mat.properties:
                        if hasattr(prop, 'key') and prop.key == '$mat.name':
                            name = os.path.basename(str(prop.data))
                            break
                material_names.append(name)
            except Exception as e:
                material_names.append(f"material_{len(material_names)}")
        
        print(f"[Paimon FBX] Loaded {len(scene.meshes)} meshes, {len(scene.materials)} materials: {material_names}")
        
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
            if mesh.texturecoords is not None:
                for ch, uv_channel in enumerate(mesh.texturecoords):
                    if uv_channel is not None and len(uv_channel) > 0:
                        # Take only x,y components for 2D UVs
                        uv_data = np.array([[uv[0], uv[1]] for uv in uv_channel], dtype=np.float32)
                        all_uvs[ch] = uv_data
            
            primary_uvs = all_uvs.get(0, None)
            
            # Face indices - pyassimp returns numpy arrays for faces
            # Each face is already an array of vertex indices
            indices = []
            for face in mesh.faces:
                # In pyassimp, face is already a numpy array of indices
                for idx in face:
                    indices.append(idx)
            indices = np.array(indices, dtype=np.uint32)
            
            # Material info - use material index to look up name
            mat_idx = mesh.materialindex
            if mat_idx >= len(material_names):
                mat_idx = 0
            mat_name = material_names[mat_idx]
            
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
        
        return meshes
