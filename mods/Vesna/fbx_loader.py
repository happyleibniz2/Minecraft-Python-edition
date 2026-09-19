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


class AiString(ctypes.Structure):
    _fields_ = [('length', ctypes.c_uint), ('data', ctypes.c_char * 1024)]


class Face(ctypes.Structure):
    _fields_ = [
        ('mNumIndices', ctypes.c_uint),
        ('mIndices', ctypes.POINTER(ctypes.c_uint)),
    ]

FaceP = ctypes.POINTER(Face)


# Correct aiMesh layout matching assimp 5.x header (64-bit Linux)
# Verified offsets: mFaces @ 208, mNumBones @ 216, mBones @ 224, mMaterialIndex @ 232
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
        # NO _pad1 here! mFaces will naturally align to offset 208
        ('mFaces', FaceP),                       # offset 208 - CRITICAL: proper Face pointer
        ('mNumBones', ctypes.c_uint),            # offset 216
        ('_pad2', ctypes.c_uint),                # offset 220 (alignment for mBones pointer)
        ('mBones', ctypes.c_void_p),             # offset 224
        ('mMaterialIndex', ctypes.c_uint),       # offset 232
        ('_pad3', ctypes.c_uint),                # offset 236 (alignment for mName)
        ('mName', ctypes.c_char * 1024),         # offset 240 - simplified aiString {uint len; char[1024];}
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


# aiProcess flags
AI_PROCESS_TRIANGULATE = 0x8
AI_PROCESS_GEN_SMOOTH_NORMALS = 0x40
AI_PROCESS_DEBONE = 0x40000000  # Remove bones to avoid bone-related crashes
AI_PROCESS_PRE_TRANSFORM_VERTICES = 0x100  # Bake node transforms into vertices

def _read_material_names(dll, scene_ptr, num_mats):
    """Reads real material names from aiMaterial structures using aiGetMaterialString."""
    names = []
    if num_mats == 0 or not scene_ptr.contents.mMaterials:
        return ["default"]
    
    # Setup function prototype for aiGetMaterialString
    # aiReturn aiGetMaterialString(const aiMaterial* pMat, const char* pKey, unsigned int type, unsigned int index, aiString* pOut);
    dll.aiGetMaterialString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint, ctypes.POINTER(AiString)]
    dll.aiGetMaterialString.restype = ctypes.c_int
    
    AI_MATKEY_NAME = b"$mat.name"
    AI_TEXTURE_TYPE_NONE = 0
    
    for i in range(num_mats):
        mat_ptr = scene_ptr.contents.mMaterials[i]
        out_str = AiString()
        ret = dll.aiGetMaterialString(mat_ptr, AI_MATKEY_NAME, AI_TEXTURE_TYPE_NONE, 0, ctypes.byref(out_str))
        if ret == 0 and out_str.length > 0:
            name = out_str.data[:out_str.length].decode('utf-8', errors='ignore')
            # Clean up name (remove paths if any)
            name = os.path.basename(name)
            names.append(name)
        else:
            names.append(f"material_{i}")
            
    return names


def load_fbx(path, flags=AI_PROCESS_TRIANGULATE | AI_PROCESS_GEN_SMOOTH_NORMALS | AI_PROCESS_DEBONE | AI_PROCESS_PRE_TRANSFORM_VERTICES):
    """Load FBX model with correct struct layouts and proper face index reading.
    
    Uses aiProcess_Debone to remove bones (avoids bone pointer issues)
    and aiProcess_PreTransformVertices to bake node transforms.
    """
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
    
    # Read real material names first
    material_names = _read_material_names(dll, p, scene.mNumMaterials)
    print(f"[Vesna FBX] Loaded {scene.mNumMeshes} meshes, {scene.mNumMaterials} materials: {material_names}")
    
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
        if mat_idx >= len(material_names):
            mat_idx = 0
        
        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': primary_uvs,
            'all_uvs': all_uvs,
            'indices': indices,
            'num_vertices': nv,
            'num_faces': nf,
            'material_index': mat_idx,
            'material_name': material_names[mat_idx],
        })
    
    dll.aiReleaseImport(p)
    return meshes
