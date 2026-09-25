<<<<<<< HEAD
"""FBX loader for the project's Assimp 5.2.5 Windows DLL."""
import ctypes
import os

import numpy as np


DLL_PATH = os.path.abspath(os.path.join(
    os.path.dirname(__file__), "..", "..", "assimp-vc143-mt.dll"))
AI_PROCESS_TRIANGULATE = 0x8
AI_PROCESS_GEN_SMOOTH_NORMALS = 0x40
AI_PROCESS_PRE_TRANSFORM_VERTICES = 0x100
_DLL = None


class Vec3(ctypes.Structure):
    _fields_ = [("x", ctypes.c_float),
                ("y", ctypes.c_float),
                ("z", ctypes.c_float)]


class Face(ctypes.Structure):
    _fields_ = [("mNumIndices", ctypes.c_uint),
                ("mIndices", ctypes.POINTER(ctypes.c_uint))]


class AiString(ctypes.Structure):
    _fields_ = [("length", ctypes.c_size_t),
                ("data", ctypes.c_char * 1024)]


Vec3P = ctypes.POINTER(Vec3)
FaceP = ctypes.POINTER(Face)


def _get_dll():
    global _DLL
    if _DLL is None:
        _DLL = ctypes.CDLL(DLL_PATH)
    return _DLL


def _material_names(dll, scene):
    if not scene.mMaterials or scene.mNumMaterials == 0:
        return []

    dll.aiGetMaterialString.argtypes = [
        ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint, ctypes.c_uint,
        ctypes.POINTER(AiString),
    ]
    dll.aiGetMaterialString.restype = ctypes.c_int
    materials = ctypes.cast(
        scene.mMaterials, ctypes.POINTER(ctypes.c_void_p))
    names = []
    for index in range(scene.mNumMaterials):
        value = AiString()
        result = dll.aiGetMaterialString(
            materials[index], b"?mat.name", 0, 0, ctypes.byref(value))
        if result == 0 and value.length:
            names.append(value.data[:value.length].decode(
                "utf-8", errors="replace"))
        else:
            names.append(f"material_{index}")
    return names


def load_fbx(path, flags=(AI_PROCESS_TRIANGULATE |
                          AI_PROCESS_GEN_SMOOTH_NORMALS |
                          AI_PROCESS_PRE_TRANSFORM_VERTICES)):
    """Return mesh arrays copied out of Assimp-owned memory.

    ``uvs`` is always UV channel zero. ``all_uvs`` preserves every channel.
    """
    dll = _get_dll()

    # Empirically verified for assimp-vc143-mt.dll on Windows x64.
    class Mesh(ctypes.Structure):
        _fields_ = [
            ("mPrimitiveTypes", ctypes.c_uint),
            ("mNumVertices", ctypes.c_uint),
            ("mNumFaces", ctypes.c_uint),
            ("_pad0", ctypes.c_uint),
            ("mVertices", Vec3P),
            ("mNormals", Vec3P),
            ("mTangents", Vec3P),
            ("mBitangents", Vec3P),
            ("mTextureCoords", Vec3P * 8),
            ("mNumUVComponents", ctypes.c_uint * 8),
            ("mFaces", FaceP),
            ("mNumBones", ctypes.c_uint),
            ("_pad1", ctypes.c_uint),
            ("mBones", ctypes.c_void_p),
            ("mMaterialIndex", ctypes.c_uint),
        ]

    class Scene(ctypes.Structure):
        _fields_ = [
            ("mFlags", ctypes.c_uint), ("_pad0", ctypes.c_uint),
            ("mRootNode", ctypes.c_void_p),
            ("mNumMeshes", ctypes.c_uint), ("_pad1", ctypes.c_uint),
            ("mMeshes", ctypes.POINTER(ctypes.POINTER(Mesh))),
            ("mNumMaterials", ctypes.c_uint), ("_pad2", ctypes.c_uint),
            ("mMaterials", ctypes.c_void_p),
        ]

    dll.aiImportFile.restype = ctypes.POINTER(Scene)
    dll.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    dll.aiReleaseImport.restype = None
    dll.aiReleaseImport.argtypes = [ctypes.POINTER(Scene)]

    scene_pointer = dll.aiImportFile(os.path.abspath(path).encode(), flags)
    if not scene_pointer:
        raise RuntimeError(f"Assimp failed to import {path}")

    try:
        scene = scene_pointer.contents
        material_names = _material_names(dll, scene)
        meshes = []
        for mesh_index in range(scene.mNumMeshes):
            mesh = scene.mMeshes[mesh_index].contents
            vertex_count = mesh.mNumVertices

            source = np.ctypeslib.as_array(mesh.mVertices, (vertex_count,))
            vertices = np.column_stack(
                [source["x"], source["y"], source["z"]]).astype(
                    np.float32, copy=True)

            normals = None
            if mesh.mNormals:
                source = np.ctypeslib.as_array(mesh.mNormals, (vertex_count,))
                normals = np.column_stack(
                    [source["x"], source["y"], source["z"]]).astype(
                        np.float32, copy=True)

            all_uvs = {}
            for channel in range(8):
                if mesh.mTextureCoords[channel]:
                    source = np.ctypeslib.as_array(
                        mesh.mTextureCoords[channel], (vertex_count,))
                    all_uvs[channel] = np.column_stack(
                        [source["x"], source["y"]]).astype(
                            np.float32, copy=True)

            face_indices = []
            for face_index in range(mesh.mNumFaces):
                face = mesh.mFaces[face_index]
                if face.mNumIndices != 3:
                    raise RuntimeError(
                        f"Mesh {mesh_index} face {face_index} was not triangulated")
                face_indices.extend(face.mIndices[i] for i in range(3))
            indices = np.asarray(face_indices, dtype=np.uint32)
            if len(indices) and int(indices.max()) >= vertex_count:
                raise RuntimeError(
                    f"Mesh {mesh_index} has an out-of-range face index")

            material_index = mesh.mMaterialIndex
            material_name = (material_names[material_index]
                             if material_index < len(material_names)
                             else f"material_{material_index}")
            meshes.append({
                "vertices": vertices,
                "normals": normals,
                "uvs": all_uvs.get(0),
                "all_uvs": all_uvs,
                "indices": indices,
                "num_vertices": vertex_count,
                "num_faces": mesh.mNumFaces,
                "material_index": material_index,
                "material_name": material_name,
            })
        return meshes
    finally:
        dll.aiReleaseImport(scene_pointer)
=======
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
        
        # Material names will be resolved from JSON files in mod.py
        # Here we just use material_0, material_1, etc. as placeholders
        # The actual texture mapping happens in mod.py using material_index
        material_names = [f"material_{i}" for i in range(len(scene.materials))]
        
        print(f"[Vesna FBX] Loaded {len(scene.meshes)} meshes, {len(scene.materials)} materials")
        
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
            # Each face is already a numpy array of indices
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
>>>>>>> 21f9a7d42d7e7076c2c7499aaa45451262efb8a5
