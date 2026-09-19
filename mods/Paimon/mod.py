"""Paimon entity mod — loads FBX via assimp DLL, renders with original textures.

Genshin Impact models use quantized UVs (5 palette indices) designed for a
custom toon shader. In standard OpenGL, each triangle picks one texel from
the diffuse texture, producing a flat-colour mosaic that is the correct
appearance for this model without the proprietary shader.
"""
import importlib.util
import math
import os
import random

import numpy as np
from game.entity.PassiveMob import PassiveMob

ASSETS = os.path.abspath(os.path.join(os.path.dirname(__file__), "assets"))
MOD_DIR = os.path.dirname(os.path.abspath(__file__))
FBX_PATH = os.path.join(ASSETS, "Paimon", "Default", "NPC_Kanban_Paimon.fbx")
TEX_DIR = os.path.join(ASSETS, "Paimon", "Default", "Textures")

MESH_TEXTURE_MAP = {
    0: "NPC_Kanban_Paimon_Tex_Body_Diffuse.png",
    1: "NPC_Kanban_Paimon_Tex_Face_Diffuse.png",
    2: "NPC_Kanban_Paimon_Tex_Cloak_Diffuse.png",
    3: "NPC_Kanban_Paimon_Tex_Face_Diffuse.png",
    4: "NPC_Kanban_Paimon_Tex_Hair_Diffuse.png",
}


def _load_fbx_loader():
    fbx_path = os.path.join(MOD_DIR, "fbx_loader.py")
    spec = importlib.util.spec_from_file_location("paimon_fbx_loader", fbx_path)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod.load_fbx


class Paimon(PassiveMob):
    TEXTURE_PATH = ""
    WANDER_SPEED = 0.4
    GROUND_OFFSET = -1.25
    MODEL_SCALE = 2.0
    MODEL_OFFSET = 0.0

    def __init__(self, gl):
        self._mesh_data = None
        self._display_lists = []
        self._loaded = False
        super().__init__(gl)
        self.hp = 20
        self.width = 0.6
        self.height = 1.8
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
            GL_NEAREST, GL_CLAMP_TO_EDGE,
            glGenLists, glNewList, glEndList, GL_COMPILE,
            GL_TRIANGLES, glBegin, glEnd,
            glVertex3f, glTexCoord2f, glNormal3f,
        )
        import pyglet

        self._mesh_tex_ids = []
        for idx in sorted(MESH_TEXTURE_MAP.keys()):
            tex_name = MESH_TEXTURE_MAP[idx]
            tex_file = os.path.join(TEX_DIR, tex_name)
            tex_id = 0
            if os.path.isfile(tex_file):
                try:
                    image = pyglet.image.load(tex_file)
                    tex = image.get_texture()
                    glBindTexture(GL_TEXTURE_2D, tex.id)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                    glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                    tex_id = tex.id
                    self._keep_alive = getattr(self, '_keep_alive', [])
                    self._keep_alive.append((image, tex))
                    print(f"Paimon: mesh[{idx}] texture {tex_name} -> GL {tex_id} ({image.width}x{image.height})")
                except Exception as e:
                    print(f"Paimon: mesh[{idx}] texture {tex_name} FAILED: {e}")
                    import traceback
                    traceback.print_exc()
            else:
                print(f"Paimon: mesh[{idx}] texture not found: {tex_file}")
            self._mesh_tex_ids.append(tex_id)

        try:
            load_fbx = _load_fbx_loader()
            self._mesh_data = load_fbx(FBX_PATH)
            print(f"Paimon: loaded {len(self._mesh_data)} meshes")
        except Exception as e:
            print("Paimon: FBX load failed:", e)
            import traceback
            traceback.print_exc()
            return

        for i, mesh in enumerate(self._mesh_data):
            verts = np.ascontiguousarray(mesh['vertices'], dtype=np.float32)
            norms = np.ascontiguousarray(mesh['normals'], dtype=np.float32) if mesh['normals'] is not None else None
            uvs = np.ascontiguousarray(mesh['uvs'], dtype=np.float32) if mesh['uvs'] is not None else None
            tex_id = self._mesh_tex_ids[i] if i < len(self._mesh_tex_ids) else 0

            if uvs is not None:
                u_min, u_max = uvs[:, 0].min(), uvs[:, 0].max()
                v_min, v_max = uvs[:, 1].min(), uvs[:, 1].max()
                unique_u = len(np.unique(np.round(uvs[:, 0], 4)))
                unique_v = len(np.unique(np.round(uvs[:, 1], 4)))
                print(f"Paimon: mesh[{i}] UVs: {unique_u}x{unique_v} unique, "
                      f"U=[{u_min:.4f},{u_max:.4f}] V=[{v_min:.4f},{v_max:.4f}]")
                if v_max <= 0.0 or v_min >= 1.0:
                    print(f"  WARNING: V range looks wrong, may need V-flip!")
                if u_max > 1.01 or u_min < -0.01 or v_max > 1.01 or v_min < -0.01:
                    print(f"  WARNING: UVs outside [0,1] range!")
            else:
                print(f"Paimon: mesh[{i}] NO UVs")

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
            print(f"Paimon: mesh[{i}] {nv} verts -> display list {dl}")

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
    api.register_entity("paimon", Paimon)
    api.register_spawn_egg("paimon", primary=0xFFFFFF, secondary=0x3D5A80)
