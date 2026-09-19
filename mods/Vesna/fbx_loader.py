"""FBX loader using ctypes with CORRECT assimp aiMesh struct layout."""
import ctypes
import os

import numpy as np

_DLL = None
def _get_dll():
    global _DLL
    if _DLL is None:
        try:
            _DLL = ctypes.CDLL("libassimp.so.5")
        except:
            _DLL = ctypes.CDLL("libassimp.so.4")
    return _DLL


class Vec3(ctypes.Structure):
    _fields_ = [('x', ctypes.c_float), ('y', ctypes.c_float), ('z', ctypes.c_float)]

Vec3P = ctypes.POINTER(Vec3)


class Face(ctypes.Structure):
    _fields_ = [
        ('mNumIndices', ctypes.c_uint),
        ('mIndices', ctypes.POINTER(ctypes.c_uint)),
    ]

FaceP = ctypes.POINTER(Face)


# Correct aiMesh layout matching assimp 5.x header
# Offsets calculated from: uint(4) * 3 + ptr(8)*4 + ptr(8)*8 + ptr(8)*8 + uint(4)*8 + padding + FaceP
# = 12 + 32 + 64 + 64 + 32 + 4(padding) = 208, then mFaces @ 208
class Mesh(ctypes.Structure):
    _fields_ = [
        ('mPrimitiveTypes', ctypes.c_uint),      # offset 0
        ('mNumVertices', ctypes.c_uint),         # offset 4
        ('mNumFaces', ctypes.c_uint),            # offset 8
        ('_pad0', ctypes.c_uint),                # offset 12 (alignment)
        ('mVertices', Vec3P),                    # offset 16
        ('mNormals', Vec3P),                     # offset 24
        ('mTangents', Vec3P),                    # offset 32
        ('mBitangents', Vec3P),                  # offset 40
        ('mColors', ctypes.c_void_p * 8),        # offset 48-112 (aiColor4D*[8])
        ('mTextureCoords', Vec3P * 8),           # offset 112-176 (aiVector3D*[8])
        ('mNumUVComponents', ctypes.c_uint * 8), # offset 176-208
        ('_pad1', ctypes.c_uint),                # offset 208 (alignment padding)
        ('mFaces', FaceP),                       # offset 212 - CRITICAL: proper Face pointer
        ('mNumBones', ctypes.c_uint),            # offset 220
        ('_pad2', ctypes.c_uint),                # offset 224
        ('mBones', ctypes.c_void_p),             # offset 228
        ('mMaterialIndex', ctypes.c_uint),       # offset 236
        ('_pad3', ctypes.c_uint),                # offset 240
        ('mName', ctypes.c_char * 64),           # offset 244 - simplified aiString
    ]


class Scene(ctypes.Structure):
    _fields_ = [
        ('mFlags', ctypes.c_uint),
        ('_pad0', ctypes.c_uint),
        ('mRootNode', ctypes.c_void_p),
        ('mNumMeshes', ctypes.c_uint),
        ('_pad1', ctypes.c_uint),
        ('mMeshes', ctypes.POINTER(ctypes.c_void_p)),  # aiMesh**
        ('mNumMaterials', ctypes.c_uint),
        ('_pad2', ctypes.c_uint),
        ('mMaterials', ctypes.POINTER(ctypes.c_void_p)),
    ]


def load_fbx(path, flags=0x8 | 0x40):  # aiProcess_Triangulate | aiProcess_GenSmoothNormals
    """Load FBX model with correct struct layouts and proper face index reading."""
    dll = _get_dll()
    
    dll.aiImportFile.restype = ctypes.POINTER(Scene)
    dll.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    dll.aiReleaseImport.restype = None
    dll.aiReleaseImport.argtypes = [ctypes.POINTER(Scene)]
    
    abs_path = os.path.abspath(path).encode()
    p = dll.aiImportFile(abs_path, flags)
    if not p:
        raise RuntimeError(f'aiImportFile failed for {path}')
    
    scene = p.contents
    meshes = []
    
    # Get mesh pointer array
    MeshPtrArray = ctypes.POINTER(ctypes.c_void_p * scene.mNumMeshes)
    mesh_ptrs = ctypes.cast(scene.mMeshes, MeshPtrArray).contents
    
    for i in range(scene.mNumMeshes):
        mp = mesh_ptrs[i]
        mesh = ctypes.cast(mp, ctypes.POINTER(Mesh)).contents
        
        nv = mesh.mNumVertices
        nf = mesh.mNumFaces
        
        # Vertices
        verts_arr = np.ctypeslib.as_array(mesh.mVertices, (nv,))
        verts = np.column_stack([verts_arr['x'], verts_arr['y'], verts_arr['z']]).astype(np.float32)
        
        # Normals
        norms = None
        if mesh.mNormals:
            n_arr = np.ctypeslib.as_array(mesh.mNormals, (nv,))
            norms = np.column_stack([n_arr['x'], n_arr['y'], n_arr['z']]).astype(np.float32)
        
        # UV coordinates
        all_uvs = {}
        for ch in range(8):
            if mesh.mTextureCoords[ch]:
                u_arr = np.ctypeslib.as_array(mesh.mTextureCoords[ch], (nv,))
                uv_data = np.column_stack([u_arr['x'], u_arr['y']]).astype(np.float32)
                all_uvs[ch] = uv_data
        
        primary_uvs = all_uvs.get(0, None)
        
        # CRITICAL FIX: Read face indices properly from aiFace structures
        indices = []
        for j in range(nf):
            face = mesh.mFaces[j]
            for k in range(face.mNumIndices):
                indices.append(face.mIndices[k])
        indices = np.array(indices, dtype=np.uint32)
        
        mat_idx = mesh.mMaterialIndex
        
        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': primary_uvs,
            'all_uvs': all_uvs,
            'indices': indices,
            'num_vertices': nv,
            'num_faces': nf,
            'material_index': mat_idx,
            'material_name': f"material_{mat_idx}",
        })
    
    dll.aiReleaseImport(p)
    return meshes
