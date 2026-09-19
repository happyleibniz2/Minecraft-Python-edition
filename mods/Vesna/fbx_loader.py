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


def _read_ai_string(ptr):
    """Read an aiString from memory: uint32 length + char data."""
    length = ctypes.c_uint32.from_address(ptr).value
    if length == 0 or length > 1024:
        return ""
    buf = (ctypes.c_char * length).from_address(ptr + 4)
    return buf.raw.decode('utf-8', errors='replace')


def _read_material_names(dll, scene_ptr):
    """Read material names from the aiScene."""
    scene = scene_ptr.contents
    num_mat = scene.mNumMaterials
    if num_mat == 0:
        return []

    mat_ptr = ctypes.cast(scene.mMaterials, ctypes.POINTER(ctypes.c_void_p))
    names = []
    for i in range(num_mat):
        mat_addr = mat_ptr[i]
        if not mat_addr:
            names.append(f"material_{i}")
            continue
        try:
            mNumProperties = ctypes.c_uint32.from_address(mat_addr + 8).value
            mProperties = ctypes.c_void_p.from_address(mat_addr).value
            if not mProperties or mNumProperties == 0:
                names.append(f"material_{i}")
                continue

            found_name = None
            for pi in range(mNumProperties):
                prop_addr = mProperties + pi * 48
                mKey_ptr = ctypes.c_void_p.from_address(prop_addr).value
                if mKey_ptr:
                    key_str = _read_ai_string(mKey_ptr)
                    if key_str == "?mat.name":
                        mData_ptr = ctypes.c_void_p.from_address(prop_addr + 40).value
                        mDataLength = ctypes.c_uint32.from_address(prop_addr + 36).value
                        if mData_ptr and mDataLength > 0:
                            found_name = ctypes.string_at(mData_ptr, mDataLength - 1).decode('utf-8', errors='replace')
                        break
                # Also check mType/mDataLength to find string properties
                mType = ctypes.c_uint32.from_address(prop_addr + 32).value
                mDataLength = ctypes.c_uint32.from_address(prop_addr + 36).value
                mData_ptr = ctypes.c_void_p.from_address(prop_addr + 40).value
                if mKey_ptr and not found_name:
                    key_str = _read_ai_string(mKey_ptr)
                    if "name" in key_str.lower() and mType == 1 and mDataLength > 0:
                        found_name = ctypes.string_at(mData_ptr, mDataLength - 1).decode('utf-8', errors='replace')

            names.append(found_name or f"material_{i}")
        except Exception as e:
            names.append(f"material_{i}")
    return names


def load_fbx(path, flags=8 | 16):
    dll = _get_dll()

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

    mat_names = _read_material_names(dll, p)
    if mat_names:
        print(f"  FBX materials: {mat_names}")

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

        primary_uvs = all_uvs.get(0, None)

        indices = np.arange(nv, dtype=np.uint32)

        mat_idx = mesh.mMaterialIndex
        mat_label = mat_names[mat_idx] if mat_idx < len(mat_names) else f"material_{mat_idx}"

        meshes.append({
            'vertices': verts,
            'normals': norms,
            'uvs': primary_uvs,
            'all_uvs': all_uvs,
            'indices': indices,
            'num_vertices': nv,
            'num_faces': nf,
            'material_index': mat_idx,
            'material_name': mat_label,
        })

    dll.aiReleaseImport(p)
    return meshes
