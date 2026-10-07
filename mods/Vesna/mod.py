"""Vesna companion rendered from an indexed FBX mesh."""
import ctypes
import importlib.util
import json
import math
import os
import random

import numpy as np
from game.entity.PassiveMob import PassiveMob


MOD_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS = os.path.join(MOD_DIR, "assets")
FBX_PATH = os.path.join(ASSETS, "vesna", "NPC_Avatar_Girl_Sword_Vesna.fbx")
TEX_DIR = os.path.join(ASSETS, "vesna", "Textures")
MAT_DIR = os.path.join(ASSETS, "vesna", "Materials")
MOD_JSON = os.path.join(MOD_DIR, "mod.json")


def _read_config():
    try:
        with open(MOD_JSON, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except (OSError, ValueError):
        return {}


CONFIG = _read_config()
UV_CHANNEL = int(CONFIG.get("uv_channel", 0))
UV_FLIP_V = bool(CONFIG.get("uv_flip_v", False))


def _load_fbx_loader():
    path = os.path.join(MOD_DIR, "fbx_loader.py")
    spec = importlib.util.spec_from_file_location("vesna_fbx_loader", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.load_fbx


def _fallback_texture_map():
    mapping = {}
    if not os.path.isdir(MAT_DIR):
        return mapping
    for filename in os.listdir(MAT_DIR):
        if not filename.endswith(".json"):
            continue
        try:
            with open(os.path.join(MAT_DIR, filename), "r",
                      encoding="utf-8") as handle:
                material = json.load(handle)
            texture = material.get("m_SavedProperties", {}).get(
                "m_TexEnvs", {}).get("_MainTex", {}).get("m_Texture", {})
            if texture.get("Name") and not texture.get("IsNull", True):
                mapping[filename[:-5]] = texture["Name"] + ".png"
        except (OSError, ValueError):
            continue
    return mapping


def _texture_filename(mesh, mesh_index):
    mapping = CONFIG.get("texture_map") or _fallback_texture_map()
    material_name = mesh.get("material_name", "")
    short_name = material_name.rsplit("::", 1)[-1]
    keys = (f"mesh:{mesh_index}", material_name, short_name,
            str(mesh.get("material_index", 0)))
    for key in keys:
        if key and key in mapping:
            return mapping[key]
    for key, texture in mapping.items():
        if material_name.endswith(key):
            return texture
    return ""


class Vesna(PassiveMob):
    TEXTURE_PATH = ""
    WANDER_SPEED = 0.4
    MODEL_SCALE = float(CONFIG.get("model_scale", 1.8))
    GROUND_OFFSET = float(CONFIG.get("ground_offset", -1.25))
    MODEL_ROTATION_Y = float(CONFIG.get("model_rotation_y", 180.0))
    MODEL_OFFSET = float(CONFIG.get("model_offset", 0.0))

    def __init__(self, gl):
        self._render_meshes = []
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
            GL_ARRAY_BUFFER, GL_CLAMP_TO_EDGE, GL_COMPILE,
            GL_ELEMENT_ARRAY_BUFFER, GL_LINEAR, GL_STATIC_DRAW,
            GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_TEXTURE_MIN_FILTER,
            GL_TEXTURE_WRAP_S, GL_TEXTURE_WRAP_T, GL_TRIANGLES,
            glBegin, glBindBuffer, glBindTexture, glBufferData, glColor4f,
            glEnd, glEndList, glGenBuffers, glGenLists, glNewList,
            glNormal3f, glTexCoord2f, glTexParameteri, glVertex3f,
        )
        import pyglet

        try:
            meshes = _load_fbx_loader()(FBX_PATH)
        except Exception as error:
            print("Vesna: FBX load failed:", error)
            import traceback
            traceback.print_exc()
            return

        texture_cache = {}
        self._keep_alive = []
        for mesh_index, mesh in enumerate(meshes):
            vertices = np.ascontiguousarray(mesh["vertices"], np.float32)
            normals = mesh["normals"]
            if normals is None:
                normals = np.zeros_like(vertices)
                normals[:, 1] = 1.0
            normals = np.ascontiguousarray(normals, np.float32)
            uvs = mesh.get("all_uvs", {}).get(UV_CHANNEL, mesh["uvs"])
            if uvs is None:
                uvs = np.zeros((len(vertices), 2), np.float32)
            else:
                uvs = np.array(uvs, dtype=np.float32, copy=True)
            if UV_FLIP_V:
                uvs[:, 1] = 1.0 - uvs[:, 1]
            uvs = np.ascontiguousarray(uvs)
            indices = np.ascontiguousarray(mesh["indices"], np.uint32)

            texture_name = _texture_filename(mesh, mesh_index)
            texture_path = os.path.join(TEX_DIR, texture_name)
            texture_id = texture_cache.get(texture_path, 0)
            if not texture_id and os.path.isfile(texture_path):
                image = pyglet.image.load(texture_path)
                texture = image.get_texture()
                texture_id = texture.id
                glBindTexture(GL_TEXTURE_2D, texture_id)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
                glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
                texture_cache[texture_path] = texture_id
                self._keep_alive.append((image, texture))

            material_name = mesh.get("material_name", "")
            mapped_texture = texture_path if texture_name else "<none>"
            if texture_name and not os.path.isfile(texture_path):
                mapped_texture += " (missing)"
            print(
                f"Vesna mesh[{mesh_index}] material[{mesh['material_index']}] "
                f"'{material_name}' -> '{mapped_texture}'")
            print(
                f"  UV{UV_CHANNEL} flip_v={UV_FLIP_V} "
                f"U=[{uvs[:, 0].min():.4f},{uvs[:, 0].max():.4f}] "
                f"V=[{uvs[:, 1].min():.4f},{uvs[:, 1].max():.4f}] "
                f"vertices={len(vertices)} indices={len(indices)}")

            interleaved = np.empty((len(vertices), 8), dtype=np.float32)
            interleaved[:, 0:3] = vertices
            interleaved[:, 3:6] = normals
            interleaved[:, 6:8] = uvs
            interleaved = np.ascontiguousarray(interleaved)

            try:
                vbo = glGenBuffers(1)
                ebo = glGenBuffers(1)
                glBindBuffer(GL_ARRAY_BUFFER, vbo)
                glBufferData(GL_ARRAY_BUFFER, interleaved.nbytes,
                             interleaved, GL_STATIC_DRAW)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, ebo)
                glBufferData(GL_ELEMENT_ARRAY_BUFFER, indices.nbytes,
                             indices, GL_STATIC_DRAW)
                glBindBuffer(GL_ARRAY_BUFFER, 0)
                glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
                self._render_meshes.append({
                    "kind": "vbo", "vbo": vbo, "ebo": ebo,
                    "count": len(indices), "texture": texture_id,
                })
            except Exception as error:
                print(f"  VBO upload failed, using display list: {error}")
                display_list = glGenLists(1)
                glNewList(display_list, GL_COMPILE)
                glBindTexture(GL_TEXTURE_2D, texture_id)
                glColor4f(1, 1, 1, 1)
                glBegin(GL_TRIANGLES)
                for index in indices:
                    vertex_index = int(index)
                    glNormal3f(*map(float, normals[vertex_index]))
                    glTexCoord2f(*map(float, uvs[vertex_index]))
                    glVertex3f(*map(float, vertices[vertex_index]))
                glEnd()
                glEndList()
                self._render_meshes.append({
                    "kind": "list", "id": display_list,
                    "texture": texture_id,
                })

        print(f"Vesna: prepared {len(self._render_meshes)} indexed meshes")

    def update(self, dt):
        self.bob_time += dt * 2.0
        super().update(dt)

    def render(self, a):
        if self.is_dead or not self._render_meshes:
            return

        from OpenGL.GL import (
            GL_ARRAY_BUFFER, GL_ELEMENT_ARRAY_BUFFER, GL_FLOAT,
            GL_NORMAL_ARRAY, GL_TEXTURE0, GL_TEXTURE_2D,
            GL_TEXTURE_COORD_ARRAY, GL_TRIANGLES, GL_TRUE,
            GL_UNSIGNED_INT, GL_VERTEX_ARRAY, glActiveTexture,
            glBindBuffer, glBindTexture, glCallList, glColor4f,
            glDisableClientState, glDrawElements, glEnable,
            glEnableClientState, glNormalPointer, glPopMatrix,
            glPushMatrix, glRotatef, glScalef, glTexCoordPointer,
            glTranslatef, glVertexPointer, glDepthMask,
        )

        glActiveTexture(GL_TEXTURE0)
        glEnable(GL_TEXTURE_2D)
        glColor4f(1, 1, 1, 1)
        glDepthMask(GL_TRUE)
        glPushMatrix()
        glTranslatef(self.position[0],
                     self.position[1] + self.GROUND_OFFSET +
                     self.MODEL_OFFSET + math.sin(self.bob_time) * 0.15,
                     self.position[2])
        glScalef(self.MODEL_SCALE, self.MODEL_SCALE, self.MODEL_SCALE)
        glRotatef(self.rotation[1] + self.MODEL_ROTATION_Y, 0, 1, 0)

        for mesh in self._render_meshes:
            if mesh["kind"] == "list":
                glCallList(mesh["id"])
                continue
            glBindTexture(GL_TEXTURE_2D, mesh["texture"])
            glBindBuffer(GL_ARRAY_BUFFER, mesh["vbo"])
            glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, mesh["ebo"])
            glEnableClientState(GL_VERTEX_ARRAY)
            glEnableClientState(GL_NORMAL_ARRAY)
            glEnableClientState(GL_TEXTURE_COORD_ARRAY)
            glVertexPointer(3, GL_FLOAT, 32, ctypes.c_void_p(0))
            glNormalPointer(GL_FLOAT, 32, ctypes.c_void_p(12))
            glTexCoordPointer(2, GL_FLOAT, 32, ctypes.c_void_p(24))
            glDrawElements(GL_TRIANGLES, mesh["count"],
                           GL_UNSIGNED_INT, ctypes.c_void_p(0))
            glDisableClientState(GL_TEXTURE_COORD_ARRAY)
            glDisableClientState(GL_NORMAL_ARRAY)
            glDisableClientState(GL_VERTEX_ARRAY)

        glBindBuffer(GL_ELEMENT_ARRAY_BUFFER, 0)
        glBindBuffer(GL_ARRAY_BUFFER, 0)
        glPopMatrix()

    def _draw_parts(self):
        pass


def pre_init(api):
    api.register_entity("vesna", Vesna)
    api.register_spawn_egg("vesna", primary=0xC41E3A, secondary=0x1A1A2E)
