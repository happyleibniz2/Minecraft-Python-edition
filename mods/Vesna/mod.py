"""Vesna entity mod — auto-discovers mesh-to-texture mapping from FBX material names."""
import importlib.util
import json
import math
import os
import random

import numpy as np
from game.entity.PassiveMob import PassiveMob

ASSETS = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets"))
MOD_DIR = os.path.dirname(os.path.abspath(__file__))
FBX_PATH = os.path.join(ASSETS, "vesna", "NPC_Avatar_Girl_Sword_Vesna.fbx")
TEX_DIR = os.path.join(ASSETS, "vesna", "Textures")
MAT_DIR = os.path.join(ASSETS, "vesna", "Materials")


def _load_fbx_loader():
    fbx_path = os.path.join(MOD_DIR, "fbx_loader.py")
    spec = importlib.util.spec_from_file_location("vesna_fbx_loader", fbx_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_fbx


def _build_material_texture_map():
    """Read material JSONs and extract _MainTex name for each material."""
    mat_map = {}
    if not os.path.isdir(MAT_DIR):
        return mat_map
    for fname in os.listdir(MAT_DIR):
        if not fname.endswith('.json'):
            continue
        mat_name = fname.replace('.json', '')
        try:
            with open(os.path.join(MAT_DIR, fname), 'r') as f:
                data = json.load(f)
            maintex = data.get('m_SavedProperties', {}).get('m_TexEnvs', {}).get('_MainTex', {})
            tex_info = maintex.get('m_Texture', {})
            tex_name = tex_info.get('Name', '')
            is_null = tex_info.get('IsNull', True)
            if tex_name and not is_null:
                tex_path = os.path.join(TEX_DIR, tex_name + '.png')
                if os.path.isfile(tex_path):
                    mat_map[mat_name] = tex_path
                else:
                    mat_map[mat_name] = tex_path
        except Exception:
            pass
    return mat_map


class Vesna(PassiveMob):
    TEXTURE_PATH = ""
    WANDER_SPEED = 0.4
    GROUND_OFFSET = -1.25
    MODEL_SCALE = 1.8
    MODEL_OFFSET = 0.0

    def __init__(self, gl):
        self._mesh_data = None
        self._display_lists = []
        self._loaded = False
        super().__init__(gl)
        self.hp = 20
        self.width = 0.6
        self.height = 1.6
        self.bob_time = random.uniform(0, math.tau)

    def _load_textures(self):
        if self._loaded:
            return
        self._loaded = True

        from OpenGL.GL import (
            glEnable, glDisable, GL_TEXTURE_2D, GL_TEXTURE0, glActiveTexture,
            glBindTexture, glTexParameteri, glColor4f,
            GL_TEXTURE_MIN_FILTER, GL_TEXTURE_MAG_FILTER,
            GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T,
            GL_LINEAR, GL_CLAMP_TO_EDGE,
            glGenLists, glNewList, glEndList, GL_COMPILE,
            GL_TRIANGLES, glBegin, glEnd,
            glVertex3f, glTexCoord2f, glNormal3f,
        )
        import pyglet

        mat_tex_map = _build_material_texture_map()
        print(f"Vesna: material texture map: { {k: os.path.basename(v) for k, v in mat_tex_map.items()} }")

        try:
            load_fbx = _load_fbx_loader()
            self._mesh_data = load_fbx(FBX_PATH)
            print(f"Vesna: loaded {len(self._mesh_data)} meshes")
        except Exception as e:
            print("Vesna: FBX load failed:", e)
            import traceback
            traceback.print_exc()
            return

        self._keep_alive = getattr(self, '_keep_alive', [])

        for i, mesh in enumerate(self._mesh_data):
            verts = np.ascontiguousarray(mesh['vertices'], dtype=np.float32)
            norms = np.ascontiguousarray(mesh['normals'], dtype=np.float32) if mesh['normals'] is not None else None
            uvs = np.ascontiguousarray(mesh['uvs'], dtype=np.float32) if mesh['uvs'] is not None else None
            mat_name = mesh.get('material_name', '')
            mat_idx = mesh['material_index']

            tex_file = mat_tex_map.get(mat_name, '')
            tex_id = 0

            if tex_file and os.path.isfile(tex_file):
                try:
                    image = pyglet.image.load(tex_file)
                    tex = image.get_texture()
                    glBindTexture(GL_TEXTURE_2D, tex.id)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    tex_id = tex.id
                    self._keep_alive.append((image, tex))
                    print(f"  mesh[{i}] mat[{mat_idx}] '{mat_name}' -> {os.path.basename(tex_file)} (GL {tex_id})")
                except Exception as e:
                    print(f"  mesh[{i}] mat[{mat_idx}] '{mat_name}' texture FAILED: {e}")
            else:
                print(f"  mesh[{i}] mat[{mat_idx}] '{mat_name}' -> no diffuse texture")

            if uvs is not None:
                unique_vals = len(np.unique(np.round(uvs, 4)))
                print(f"    UVs: {unique_vals} unique, "
                      f"U=[{uvs[:, 0].min():.4f},{uvs[:, 0].max():.4f}] "
                      f"V=[{uvs[:, 1].min():.4f},{uvs[:, 1].max():.4f}]")

            dl = glGenLists(1)
            glNewList(dl, GL_COMPILE)
            glActiveTexture(GL_TEXTURE0)
            glEnable(GL_TEXTURE_2D)
            if tex_id:
                glBindTexture(GL_TEXTURE_2D, tex_id)
            glBegin(GL_TRIANGLES)
            nv = len(verts)
            for vi in range(nv):
                if norms is not None:
                    glNormal3f(float(norms[vi, 0]), float(norms[vi, 1]), float(norms[vi, 2]))
                if uvs is not None:
                    glTexCoord2f(float(uvs[vi, 0]), float(uvs[vi, 1]))
                glVertex3f(float(verts[vi, 0]), float(verts[vi, 1]), float(verts[vi, 2]))
            glEnd()
            glEndList()
            self._display_lists.append(dl)
            print(f"    {nv} verts -> display list {dl}")

    def update(self, dt):
        self.bob_time += dt * 2.0
        super().update(dt)

    def render(self, a):
        if self.is_dead or not self._display_lists:
            return

        from OpenGL.GL import (
            glPushMatrix, glPopMatrix, glTranslatef, glScalef, glRotatef,
            glColor4f, glCallList, GL_TEXTURE0, glActiveTexture,
            glDepthMask, GL_TRUE,
        )

        bob = math.sin(self.bob_time) * 0.15

        glActiveTexture(GL_TEXTURE0)
        glColor4f(1, 1, 1, 1)
        glDepthMask(GL_TRUE)
        glPushMatrix()
        glTranslatef(self.position[0],
                     self.position[1] + self.GROUND_OFFSET + self.MODEL_OFFSET + bob,
                     self.position[2])
        glScalef(self.MODEL_SCALE, self.MODEL_SCALE, self.MODEL_SCALE)
        glRotatef(self.rotation[1] + 180, 0, 1, 0)

        for dl in self._display_lists:
            glCallList(dl)

        glPopMatrix()

    def _draw_parts(self):
        pass


def pre_init(api):
    api.register_entity("vesna", Vesna)
    api.register_spawn_egg("vesna", primary=0xC41E3A, secondary=0x1A1A2E)
