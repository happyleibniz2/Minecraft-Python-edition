"""FBX loader using assimp DLL via ctypes.

Correct struct layout for assimp 5.2.5 on Windows x64 (has mNumFaces,
no mColors array in aiMesh).
"""
import ctypes
import os

import numpy as np

_DLL = None
DLL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'assimp-vc143-mt.dll')


class Vec3(ctypes.Structure):
    _fields_ = [('x', ctypes.c_float), ('y', ctypes.c_float), ('z', ctypes.c_float)]

Vec3P = ctypes.POINTER(Vec3)


def _get_dll():
    global _DLL
    if _DLL is None:
        _DLL = ctypes.CDLL(DLL_PATH)
    return _DLL


def load_fbx(path, flags=8 | 16):
    dll = _get_dll()

    # aiMesh layout (assimp 5.2.5 x64):
    #   0: mPrimitiveTypes   (uint32)
    #   4: mNumVertices      (uint32)
    #   8: mNumFaces         (uint32) + pad(4) for pointer alignment
    #  16: mVertices         (ptr)
    #  24: mNormals          (ptr)
    #  32: mTangents         (ptr)
    #  40: mBitangents       (ptr)
    #  48: mTextureCoords[8] (8 x ptr = 64 bytes)
    # 112: mNumUVComponents[8] (8 x uint32 = 32 bytes)
    # 144: mFaces            (ptr)
    # 152: mNumBones         (uint32) + pad(4)
    # 160: mBones            (ptr)
    # 168: mMaterialIndex    (uint32)

    class Mesh(ctypes.Structure):
        pass
    Mesh._fields_ = [
        ('mPrimitiveTypes', ctypes.c_uint),
        ('mNumVertices', ctypes.c_uint),
        ('mNumFaces', ctypes.c_uint),
        ('_pad0', ctypes.c_uint),
        ('mVertices', Vec3P),
        ('mNormals', Vec3P),
        ('mTangents', Vec3P),
        ('mBitangents', Vec3P),
        ('mTextureCoords', Vec3P * 8),
        ('mNumUVComponents', ctypes.c_uint * 8),
        ('mFaces', ctypes.c_void_p),
        ('mNumBones', ctypes.c_uint),
        ('_pad1', ctypes.c_uint),
        ('mBones', ctypes.c_void_p),
        ('mMaterialIndex', ctypes.c_uint),
    ]

    class Scene(ctypes.Structure):
        _fields_ = [
            ('mFlags', ctypes.c_uint), ('_p0', ctypes.c_uint),
            ('mRootNode', ctypes.c_void_p),
            ('mNumMeshes', ctypes.c_uint), ('_p1', ctypes.c_uint),
            ('mMeshes', ctypes.POINTER(ctypes.POINTER(Mesh))),
            ('mNumMaterials', ctypes.c_uint), ('_p2', ctypes.c_uint),
            ('mMaterials', ctypes.c_void_p),
        ]

    dll.aiImportFile.restype = ctypes.POINTER(Scene)
    dll.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    dll.aiReleaseImport.restype = None
    dll.aiReleaseImport.argtypes = [ctypes.POINTER(Scene)]

    p = dll.aiImportFile(os.path.abspath(path).encode(), flags)
    if not p:
        raise RuntimeError('assimp aiImportFile failed')
    scene = p.contents

    meshes = []
    for i in range(scene.mNumMeshes):
        mesh = scene.mMeshes[i].contents
        nv = mesh.mNumVertices
        nf = mesh.mNumFaces

        verts_arr = np.ctypeslib.as_array(mesh.mVertices, (nv,))
        verts = np.column_stack([verts_arr['x'], verts_arr['y'], verts_arr['z']])

        norms = None
        if mesh.mNormals:
            n_arr = np.ctypeslib.as_array(mesh.mNormals, (nv,))
            norms = np.column_stack([n_arr['x'], n_arr['y'], n_arr['z']])

        all_uvs = {}
        for ch in range(8):
            if mesh.mTextureCoords[ch]:
                u_arr = np.ctypeslib.as_array(mesh.mTextureCoords[ch], (nv,))
                uv_data = np.column_stack([u_arr['x'], u_arr['y']])
                all_uvs[ch] = uv_data
                u_range = (uv_data[:, 0].min(), uv_data[:, 0].max())
                v_range = (uv_data[:, 1].min(), uv_data[:, 1].max())
                unique_u = len(np.unique(np.round(uv_data[:, 0], 4)))
                unique_v = len(np.unique(np.round(uv_data[:, 1], 4)))
                print(f"  UV channel {ch}: {unique_u}x{unique_v} unique, "
                      f"U=[{u_range[0]:.4f},{u_range[1]:.4f}], "
                      f"V=[{v_range[0]:.4f},{v_range[1]:.4f}]")

        primary_uvs = all_uvs.get(0, None)

        indices = np.arange(nv, dtype=np.uint32)

        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': primary_uvs,
            'all_uvs': all_uvs,
            'indices': indices,
            'num_vertices': nv,
            'num_faces': nf,
            'material_index': mesh.mMaterialIndex,
        })

    dll.aiReleaseImport(p)
    return meshes
