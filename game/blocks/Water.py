import json
import math
import os
import time
from dataclasses import dataclass

import pyglet
from OpenGL.GL import *


@dataclass(frozen=True)
class FluidState:
    level: int = 0
    source: bool = False
    falling: bool = False


class AnimatedTextureGroup(pyglet.graphics.TextureGroup):
    def __init__(self, frames, frame_times):
        super().__init__(frames[0])
        self.frames = tuple(frames)
        self.frame_times = tuple(frame_times)
        self.total_time = sum(frame_times)
        self.started_at = time.perf_counter()

    def set_state(self):
        elapsed = (time.perf_counter() - self.started_at) % self.total_time
        frame = self.frames[-1]
        for texture, duration in zip(self.frames, self.frame_times):
            if elapsed < duration:
                frame = texture
                break
            elapsed -= duration
        glEnable(frame.target)
        glBindTexture(frame.target, frame.id)


def load_animated_texture(path):
    image = pyglet.image.load(path)
    frame_size = image.width
    if image.height % frame_size:
        raise ValueError(f"Animated texture is not a vertical frame strip: {path}")

    frame_count = image.height // frame_size
    textures = []
    for index in range(frame_count):
        y = image.height - (index + 1) * frame_size
        texture = image.get_region(0, y, frame_size, frame_size).get_texture()
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_NEAREST)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_NEAREST)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_S, GL_REPEAT)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_T, GL_REPEAT)
        textures.append(texture)

    animation = _load_animation_metadata(path)
    default_ticks = max(1, int(animation.get("frametime", 1)))
    configured_frames = animation.get("frames")
    if configured_frames:
        sequence = []
        durations = []
        for entry in configured_frames:
            if isinstance(entry, dict):
                index = int(entry["index"])
                ticks = max(1, int(entry.get("time", default_ticks)))
            else:
                index = int(entry)
                ticks = default_ticks
            if 0 <= index < frame_count:
                sequence.append(textures[index])
                durations.append(ticks / 20)
    else:
        sequence = textures
        durations = [default_ticks / 20] * frame_count

    if not sequence:
        sequence = textures
        durations = [default_ticks / 20] * frame_count

    return AnimatedTextureGroup(sequence, durations)


def configure_water_textures(scene):
    still = load_animated_texture(os.path.join("textures", "water_still.png"))
    flow = load_animated_texture(os.path.join("textures", "water_flow.png"))
    scene.texture["water_still"] = still
    scene.texture["water_flow"] = flow
    scene.block["water"] = (flow, flow, still, still, flow, flow)
    scene.water_overlay = scene.texture.get("water_overlay")


def water_face_vertices(pos, face_index, height, lower_height=0, gameTime=0.0):
    """Generate water face vertices with wave displacement for realistic fluid motion."""
    x, y, z = pos
    x0, x1 = x - 0.5, x + 0.5
    z0, z1 = z - 0.5, z + 0.5
    
    # CRITICAL FIX: Add vertex displacement for wave animation
    # Three combined sine waves with different frequencies and speeds
    def waveHeight(vx, vz, t):
        w1 = math.sin(vx * 0.8 + t * 1.5) * 0.06
        w2 = math.sin(vz * 0.6 + t * 1.1) * 0.04
        w3 = math.sin((vx + vz) * 1.2 + t * 2.0) * 0.02
        return w1 + w2 + w3
    
    # Apply wave displacement to water surface vertices
    if face_index == 3:  # Top surface
        h00 = waveHeight(x0, z0, gameTime)
        h01 = waveHeight(x0, z1, gameTime)
        h11 = waveHeight(x1, z1, gameTime)
        h10 = waveHeight(x1, z0, gameTime)
        top_base = y - 0.5 + height
        faces = (
            (x0, y - 0.5 + lower_height, z0, x0, y - 0.5 + lower_height, z1, x0, top_base, z1, x0, top_base, z0),
            (x1, y - 0.5 + lower_height, z1, x1, y - 0.5 + lower_height, z0, x1, top_base, z0, x1, top_base, z1),
            (x0, y - 0.5 + lower_height, z0, x1, y - 0.5 + lower_height, z0, x1, y - 0.5 + lower_height, z1, x0, y - 0.5 + lower_height, z1),
            # Top face with displaced vertices for wave effect
            (x0, top_base + h00, z0, x1, top_base + h10, z0, x1, top_base + h11, z1, x0, top_base + h01, z1),
            (x1, y - 0.5 + lower_height, z0, x0, y - 0.5 + lower_height, z0, x0, top_base + h00, z0, x1, top_base + h10, z0),
            (x0, y - 0.5 + lower_height, z1, x1, y - 0.5 + lower_height, z1, x1, top_base + h11, z1, x0, top_base + h01, z1),
        )
    else:
        # Side faces - use simpler displacement
        bottom = y - 0.5 + lower_height
        top = y - 0.5 + height
        # Add slight wave to top edge of side faces
        wave_top = 0.0
        if face_index in (0, 1, 4, 5):  # Side faces
            mid_x = (x0 + x1) * 0.5 if face_index in (0, 1) else x0
            mid_z = (z0 + z1) * 0.5 if face_index in (4, 5) else z0
            wave_top = waveHeight(mid_x, mid_z, gameTime) * 0.5
        
        faces = (
            (x0, bottom, z0, x0, bottom, z1, x0, top + wave_top, z1, x0, top + wave_top, z0),
            (x1, bottom, z1, x1, bottom, z0, x1, top + wave_top, z0, x1, top + wave_top, z1),
            (x0, bottom, z0, x1, bottom, z0, x1, bottom, z1, x0, bottom, z1),
            (x0, top, z1, x1, top, z1, x1, top, z0, x0, top, z0),
            (x1, bottom, z0, x0, bottom, z0, x0, top, z0, x1, top, z0),
            (x0, bottom, z1, x1, bottom, z1, x1, top, z1, x0, top, z1),
        )
    
    return faces[face_index]


def _load_animation_metadata(path):
    for metadata_path in (path + ".mcmeta", path + ".mmcmeta"):
        if os.path.isfile(metadata_path):
            with open(metadata_path, "r", encoding="utf-8") as metadata_file:
                return json.load(metadata_file).get("animation", {})
    return {}
