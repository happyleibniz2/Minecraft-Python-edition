"""Build-time converter: FBX -> binary mesh data using assimp DLL.

Reads the FBX file via the assimp DLL with raw struct offsets and writes a
simple binary blob that the Paimon mod can load at runtime without assimp.
"""
import ctypes
import os
import struct
import sys
import numpy as np

DLL_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                        '..', '..', 'assimp-vc143-mt.dll')

OUTPUT = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                      'paimon_mesh.bin')

FBX_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                         'assets', 'Paimon', 'Default', 'NPC_Kanban_Paimon.fbx')

# Mesh struct offsets (empirically verified against assimp 5.2.5 x64):
#   0: mPrimitiveTypes (uint32)
#   4: mNumVertices   (uint32)
#   8: mVertices      (ptr)
#  16: mNormals       (ptr)
#  24: mTangents      (ptr)
#  32: mBitangents    (ptr)
#  40: mColors[8]     (8 x ptr)
# 104: mTextureCoords[8] (8 x ptr)
# 168: mNumUVComponents[8] (8 x uint32)
# 200: mFaces         (ptr)
# 208: mNumBones      (uint32)
# 212: _pad           (4)
# 216: mBones         (ptr)
# 224: mMaterialIndex (uint32)

MESH_NV_OFF = 4
MESH_VERTS_OFF = 8
MESH_NORMS_OFF = 16
MESH_UV0_OFF = 104
MESH_FACES_OFF = 200
MESH_MAT_OFF = 224

# aiFace struct:
#   0: mNumIndices (uint32)
#   4: _pad        (uint32)
#   8: mIndices    (ptr)
FACE_NIDX_OFF = 0
FACE_INDICES_OFF = 8
FACE_SIZE = 16


def _r32(base, off):
    return struct.unpack_from('I', bytes((ctypes.c_byte * 4).from_address(base + off)))[0]


def _r64(base, off):
    return struct.unpack_from('Q', bytes((ctypes.c_byte * 8).from_address(base + off)))[0]


def _rvec3s(ptr, count):
    if not ptr:
        return None
    data = bytes((ctypes.c_byte * (12 * count)).from_address(ptr))
    return np.frombuffer(data, dtype=np.float32).reshape(count, 3).copy()


def _rface_indices(face_ptr, idx_count):
    """Read indices from a single aiFace."""
    indices = []
    for j in range(idx_count):
        idx = struct.unpack_from('I', bytes((ctypes.c_byte * 4).from_address(face_ptr + j * 4)))[0]
        indices.append(idx)
    return indices


def main():
    dll = ctypes.CDLL(DLL_PATH)
    dll.aiImportFile.restype = ctypes.c_void_p
    dll.aiImportFile.argtypes = [ctypes.c_char_p, ctypes.c_uint]
    dll.aiReleaseImport.restype = None
    dll.aiReleaseImport.argtypes = [ctypes.c_void_p]

    # aiProcess_Triangulate | aiProcess_GenSmoothNormals
    p = dll.aiImportFile(FBX_PATH.encode(), 8 | 16)
    if not p:
        print('FAILED to import', FBX_PATH)
        sys.exit(1)

    scene_addr = p
    # Scene layout verified: mFlags(4)+pad(4)+rootNode(8)+mNumMeshes(4)+pad(4)+mMeshes(8)
    num_meshes = _r32(scene_addr, 16)
    meshes_ptr = _r64(scene_addr, 24)

    print('Scene: %d meshes' % num_meshes)

    with open(OUTPUT, 'wb') as f:
        f.write(struct.pack('I', num_meshes))

        for i in range(num_meshes):
            mesh_addr = _r64(meshes_ptr, i * 8)
            nv = _r32(mesh_addr, MESH_NV_OFF)
            verts_ptr = _r64(mesh_addr, MESH_VERTS_OFF)
            norms_ptr = _r64(mesh_addr, MESH_NORMS_OFF)
            uv0_ptr = _r64(mesh_addr, MESH_UV0_OFF)
            faces_ptr = _r64(mesh_addr, MESH_FACES_OFF)
            mat_idx = _r32(mesh_addr, MESH_MAT_OFF)

            verts = _rvec3s(verts_ptr, nv)
            norms = _rvec3s(norms_ptr, nv)
            uvs = _rvec3s(uv0_ptr, nv)
            if uvs is not None:
                uvs = uvs[:, :2].copy()

            # Read faces to get index count
            # Each aiFace is 16 bytes (mNumIndices=4 + pad=4 + mIndices=8)
            # We need to know total face count. Since assimp triangulated,
            # num_indices = nv (typically)
            # But we need to read from faces to get the actual count.
            # First face's mNumIndices tells us indices per face (should be 3 for triangulated).
            total_indices = 0
            all_indices = []
            if faces_ptr and nv > 0:
                # Read first face to get face size
                first_nidx = _r32(faces_ptr, FACE_NIDX_OFF)
                # For a triangulated mesh, total_indices ~ nv
                # Read all faces until we have enough indices
                max_faces = nv  # safety limit
                for fi in range(max_faces):
                    face_addr = faces_ptr + fi * FACE_SIZE
                    nidx = _r32(face_addr, FACE_NIDX_OFF)
                    if nidx == 0:
                        break
                    indices = _rface_indices(face_addr + FACE_INDICES_OFF, nidx)
                    all_indices.extend(indices)
                    total_indices += nidx
                    if total_indices >= nv and nidx == first_nidx:
                        # Check if next face exists
                        next_face = face_addr + FACE_SIZE
                        try:
                            next_nidx = _r32(next_face, FACE_NIDX_OFF)
                            if next_nidx == 0:
                                break
                        except:
                            break

            num_indices = len(all_indices)
            print('  mesh[%d]: %d verts, %d indices, mat=%d, has_norms=%s, has_uvs=%s' % (
                i, nv, num_indices, mat_idx,
                norms is not None, uvs is not None))

            # Write mesh header
            f.write(struct.pack('III', nv, num_indices, mat_idx))

            # Write vertices (3 floats each)
            for v in verts:
                f.write(struct.pack('fff', v[0], v[1], v[2]))

            # Write normals
            if norms is not None:
                f.write(b'\x01')  # has_normals flag
                for n in norms:
                    f.write(struct.pack('fff', n[0], n[1], n[2]))
            else:
                f.write(b'\x00')

            # Write UVs
            if uvs is not None:
                f.write(b'\x01')  # has_uvs flag
                for u in uvs:
                    f.write(struct.pack('ff', u[0], u[1]))
            else:
                f.write(b'\x00')

            # Write indices
            for idx in all_indices:
                f.write(struct.pack('I', idx))

    dll.aiReleaseImport(p)
    print('Wrote', OUTPUT, '(%d bytes)' % os.path.getsize(OUTPUT))


if __name__ == '__main__':
    main()
