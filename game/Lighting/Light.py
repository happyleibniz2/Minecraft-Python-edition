"""Smooth skylight and torch lighting for the compatibility renderer."""

import math

import numpy as np
from OpenGL.GL import *
from OpenGL.GLU import gluLookAt
from OpenGL.GL.shaders import compileProgram, compileShader
import settings


VERTEX_SHADER = """
#version 120
varying vec4 vertexColor;
varying float torchLight;
varying float fogDistance;
varying vec3 worldPosition;
varying vec4 shadowCoord;
attribute float swayWeight;
uniform mat4 inverseViewMatrix;
uniform mat4 shadowMatrix;
uniform float leavesSway;
uniform float gameTime;
uniform vec2 cloudOffset;

void main() {
    vec4 animatedPosition = gl_Vertex;
    if (leavesSway > 0.5 && swayWeight > 0.0) {
        float primary = sin(gameTime * 1.65
            + gl_Vertex.x * 0.73 + gl_Vertex.z * 0.51 + cloudOffset.x * 0.035);
        float detail = sin(gameTime * 2.47
            + gl_Vertex.x * 1.31 - gl_Vertex.z * 0.87 + cloudOffset.y * 0.05);
        float motion = (primary * 0.72 + detail * 0.28) * swayWeight;
        animatedPosition.x += motion * 0.075;
        animatedPosition.z += motion * 0.032;
    }

    gl_Position = gl_ModelViewProjectionMatrix * animatedPosition;
    gl_TexCoord[0] = gl_MultiTexCoord0;
    vertexColor = gl_Color;
    torchLight = gl_MultiTexCoord0.z;
    vec4 viewPosition = gl_ModelViewMatrix * animatedPosition;
    vec4 world = inverseViewMatrix * viewPosition;
    fogDistance = length(viewPosition.xyz);
    worldPosition = world.xyz;
    shadowCoord = shadowMatrix * world;
}
"""


FRAGMENT_SHADER = """
#version 120
uniform sampler2D texture0;
uniform float skyLight;
uniform vec3 fogColor;
uniform float fogStart;
uniform float fogEnd;
uniform float gameTime;
uniform sampler2D shadowMap;
uniform int shadowsEnabled;
uniform vec2 shadowTexel;
uniform int shadowQuality;
uniform vec2 cloudOffset;
uniform float cloudCoverage;
uniform float weatherStrength;
uniform float dynamicLighting;
varying vec4 vertexColor;
varying float torchLight;
varying float fogDistance;
varying vec3 worldPosition;
varying vec4 shadowCoord;

float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float noise21(vec2 p) {
    vec2 i = floor(p);
    vec2 f = fract(p);
    f = f * f * (3.0 - 2.0 * f);
    return mix(mix(hash21(i), hash21(i + vec2(1.0, 0.0)), f.x),
               mix(hash21(i + vec2(0.0, 1.0)), hash21(i + vec2(1.0)), f.x), f.y);
}

float cloudNoise(vec2 p) {
    return noise21(p);
}

float realtimeShadow() {
    if (shadowsEnabled == 0 || shadowCoord.w <= 0.0) {
        return 1.0;
    }
    vec3 projected = shadowCoord.xyz / shadowCoord.w;
    if (projected.x <= 0.0 || projected.x >= 1.0 ||
        projected.y <= 0.0 || projected.y >= 1.0 ||
        projected.z <= 0.0 || projected.z >= 1.0) {
        return 1.0;
    }

    float bias = 0.0018;
    float centerDepth = texture2D(shadowMap, projected.xy).r;
    float lit = projected.z - bias <= centerDepth ? 1.0 : 0.0;
    if (shadowQuality > 0) {
        float spread = shadowQuality == 1 ? 0.85 : 1.45;
        vec2 offset = shadowTexel * spread;
        float d0 = texture2D(shadowMap, projected.xy + vec2(-offset.x, -offset.y)).r;
        float d1 = texture2D(shadowMap, projected.xy + vec2( offset.x, -offset.y)).r;
        float d2 = texture2D(shadowMap, projected.xy + vec2(-offset.x,  offset.y)).r;
        float d3 = texture2D(shadowMap, projected.xy + vec2( offset.x,  offset.y)).r;
        lit += projected.z - bias <= d0 ? 1.0 : 0.0;
        lit += projected.z - bias <= d1 ? 1.0 : 0.0;
        lit += projected.z - bias <= d2 ? 1.0 : 0.0;
        lit += projected.z - bias <= d3 ? 1.0 : 0.0;
        lit /= 5.0;
    }
    return mix(0.38, 1.0, lit);
}

void main() {
    vec4 texel = texture2D(texture0, gl_TexCoord[0].xy);
    float dayAmount = smoothstep(0.12, 0.85, skyLight);

    vec3 nightSky = vec3(0.34, 0.42, 0.72) * skyLight;
    vec3 daySky = vec3(1.04, 1.00, 0.91) * skyLight;
    vec3 skylight = mix(nightSky, daySky, dayAmount);

    float flicker = 0.975 + 0.025 * sin(gameTime * 8.0
                     + worldPosition.x * 1.7 + worldPosition.z * 2.3);
    float activeTorchLight = torchLight * dynamicLighting;
    vec3 torchColor = vec3(1.18, 0.73, 0.38) * activeTorchLight * flicker;
    vec3 illumination = max(skylight, torchColor);

    float sunShadowStrength = dayAmount * 0.82 * (1.0 - weatherStrength * 0.72);
    float sunShadow = mix(1.0, realtimeShadow(), sunShadowStrength);
    float cloudField = cloudNoise((worldPosition.xz + cloudOffset) * 0.018);
    float cloudThreshold = 0.82 - cloudCoverage * 0.45;
    float cloudDensity = smoothstep(cloudThreshold, cloudThreshold + 0.16, cloudField);
    float cloudShadow = 1.0 - cloudDensity * 0.24 * dayAmount;
    illumination *= min(sunShadow, cloudShadow);

    vec3 color = texel.rgb * vertexColor.rgb * illumination;

    float luminance = dot(color, vec3(0.2126, 0.7152, 0.0722));
    color = mix(vec3(luminance), color, 1.10);
    color = max(vec3(0.0), (color - 0.025) * 1.035 + 0.025);
    color = pow(color, vec3(0.96));

    float fogRange = max(0.001, fogEnd - fogStart);
    float fogAmount = smoothstep(0.0, 1.0,
                          clamp((fogDistance - fogStart) / fogRange, 0.0, 1.0));
    color = mix(color, fogColor, fogAmount);

    gl_FragColor = vec4(color, texel.a * vertexColor.a);
}
"""


class Light:
    TORCH_RADIUS = 15.0
    LIGHT_CELL_SIZE = 16
    SHADOW_QUALITY_SIZES = {"LOW": 512, "MEDIUM": 1024, "HIGH": 2048}
    SHADOW_SIZE = 1024
    SHADOW_RADIUS = 48.0

    def __init__(self, gl):
        self.gl = gl
        self.enabled = settings.SHADERS
        self.SHADOW_SIZE = self.SHADOW_QUALITY_SIZES[settings.SHADOW_QUALITY]
        self.lightSources = set()
        self._light_columns = {}
        self._vertex_light_cache = {}
        self.sky_brightness = 1.0
        self.shader = None
        self.sky_uniform = None
        self.texture_uniform = None
        self.fog_color_uniform = None
        self.fog_start_uniform = None
        self.fog_end_uniform = None
        self.time_uniform = None
        self.inverse_view_uniform = None
        self.shadow_matrix_uniform = None
        self.shadow_sampler_uniform = None
        self.shadows_enabled_uniform = None
        self.shadow_texel_uniform = None
        self.shadow_quality_uniform = None
        self.cloud_offset_uniform = None
        self.cloud_coverage_uniform = None
        self.weather_uniform = None
        self.dynamic_lighting_uniform = None
        self.leaves_sway_uniform = None
        self.sway_attribute_location = -1
        self.fog_color = (0.5, 0.7, 1.0)
        self.fog_start = 10.0
        self.fog_end = 80.0
        self.elapsed = 0.0
        self.cloud_offset = (0.0, 0.0)
        self.cloud_coverage = 0.56
        self.weather_strength = 0.0
        self.shadow_fbo = 0
        self.shadow_texture = 0
        self.shadow_matrix = np.identity(4, dtype=np.float32)
        self.shadow_ready = False
        self._saved_viewport = None
        self.last_shadow_time = -999.0
        self.last_shadow_center = None
        self.last_shadow_direction = None

    def initialize(self):
        """Compile the GLSL 1.20 compatibility shader, with safe fallback."""
        if self.shader is not None:
            return self.shader != 0
        try:
            self.shader = compileProgram(
                compileShader(VERTEX_SHADER, GL_VERTEX_SHADER),
                compileShader(FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
            )
            self.sky_uniform = glGetUniformLocation(self.shader, "skyLight")
            self.texture_uniform = glGetUniformLocation(self.shader, "texture0")
            self.fog_color_uniform = glGetUniformLocation(self.shader, "fogColor")
            self.fog_start_uniform = glGetUniformLocation(self.shader, "fogStart")
            self.fog_end_uniform = glGetUniformLocation(self.shader, "fogEnd")
            self.time_uniform = glGetUniformLocation(self.shader, "gameTime")
            self.inverse_view_uniform = glGetUniformLocation(self.shader, "inverseViewMatrix")
            self.shadow_matrix_uniform = glGetUniformLocation(self.shader, "shadowMatrix")
            self.shadow_sampler_uniform = glGetUniformLocation(self.shader, "shadowMap")
            self.shadows_enabled_uniform = glGetUniformLocation(self.shader, "shadowsEnabled")
            self.shadow_texel_uniform = glGetUniformLocation(self.shader, "shadowTexel")
            self.shadow_quality_uniform = glGetUniformLocation(self.shader, "shadowQuality")
            self.cloud_offset_uniform = glGetUniformLocation(self.shader, "cloudOffset")
            self.cloud_coverage_uniform = glGetUniformLocation(self.shader, "cloudCoverage")
            self.weather_uniform = glGetUniformLocation(self.shader, "weatherStrength")
            self.dynamic_lighting_uniform = glGetUniformLocation(self.shader, "dynamicLighting")
            self.leaves_sway_uniform = glGetUniformLocation(self.shader, "leavesSway")
            self.sway_attribute_location = glGetAttribLocation(self.shader, "swayWeight")
            self._initialize_shadow_map()
            return True
        except Exception as error:
            print(f"Warning: smooth lighting shader unavailable ({error})")
            self.shader = 0
            return False

    def addLightSource(self, x, y, z):
        source = (round(x), round(y), round(z))
        if source in self.lightSources:
            return
        self.lightSources.add(source)
        cell = (source[0] // self.LIGHT_CELL_SIZE, source[2] // self.LIGHT_CELL_SIZE)
        self._light_columns.setdefault(cell, set()).add(source)
        self._vertex_light_cache.clear()
        self._dirty_light_region(source)

    def removeLightSource(self, x, y, z):
        source = (round(x), round(y), round(z))
        if source not in self.lightSources:
            return
        self.lightSources.remove(source)
        cell = (source[0] // self.LIGHT_CELL_SIZE, source[2] // self.LIGHT_CELL_SIZE)
        column = self._light_columns.get(cell)
        if column is not None:
            column.discard(source)
            if not column:
                del self._light_columns[cell]
        self._vertex_light_cache.clear()
        self._dirty_light_region(source)

    def set_sky_brightness(self, brightness):
        self.sky_brightness = max(0.06, min(1.0, float(brightness)))

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            glUseProgram(0)
        elif self.shader is None:
            self.initialize()

    def set_shadow_quality(self, quality):
        quality = str(quality).upper()
        size = self.SHADOW_QUALITY_SIZES.get(quality, 1024)
        if size == self.SHADOW_SIZE and self.shadow_texture:
            return
        self.SHADOW_SIZE = size
        self.shadow_ready = False
        self.last_shadow_time = -999.0
        self._delete_shadow_map()
        if self.shader:
            self._initialize_shadow_map()

    def set_environment(self, fog_color, fog_start, fog_end):
        self.fog_color = tuple(float(component) for component in fog_color[:3])
        self.fog_start = float(fog_start)
        self.fog_end = float(fog_end)

    def set_clouds(self, offset, coverage):
        self.cloud_offset = tuple(float(value) for value in offset[:2])
        self.cloud_coverage = float(coverage)

    def set_weather(self, strength):
        self.weather_strength = max(0.0, min(1.0, float(strength)))

    def get_vertex_light(self, vertex):
        """Smooth torch light at a vertex, 15 down to 0 over 15 blocks."""
        if not self.lightSources:
            return 0.0
        key = tuple(vertex)
        cached = self._vertex_light_cache.get(key)
        if cached is not None:
            return cached
        light = self._calculate_vertex_light(*key)
        if len(self._vertex_light_cache) >= 65536:
            self._vertex_light_cache.clear()
        self._vertex_light_cache[key] = light
        return light

    def _calculate_vertex_light(self, x, y, z):
        brightest = 0.0
        cell_x = math.floor(x / self.LIGHT_CELL_SIZE)
        cell_z = math.floor(z / self.LIGHT_CELL_SIZE)
        for offset_x in (-1, 0, 1):
            for offset_z in (-1, 0, 1):
                for lx, ly, lz in self._light_columns.get((cell_x + offset_x, cell_z + offset_z), ()):
                    dx = x - lx
                    dy = y - (ly + 0.35)
                    dz = z - lz
                    distance_squared = dx * dx + dy * dy + dz * dz
                    if distance_squared >= self.TORCH_RADIUS * self.TORCH_RADIUS:
                        continue
                    light = 1.0 - math.sqrt(distance_squared) / self.TORCH_RADIUS
                    if light > brightest:
                        brightest = light
        return max(0.0, min(1.0, brightest))

    def close(self):
        """Release caches and shadow-map resources before a world reset."""
        self._vertex_light_cache.clear()
        resources = (
            (self.shadow_fbo, lambda value: glDeleteFramebuffers(1, [value])),
            (self.shadow_texture, lambda value: glDeleteTextures([value])),
            (self.shader, glDeleteProgram),
        )
        for resource, delete in resources:
            if not resource:
                continue
            try:
                delete(resource)
            except Exception as error:
                print(f"Warning: could not release lighting resource ({error})")
        self.shadow_fbo = 0
        self.shadow_texture = 0
        self.shadow_ready = False
        self.shader = 0

    def _delete_shadow_map(self):
        if self.shadow_fbo:
            try:
                glDeleteFramebuffers(1, [self.shadow_fbo])
            except Exception:
                pass
        if self.shadow_texture:
            try:
                glDeleteTextures([self.shadow_texture])
            except Exception:
                pass
        self.shadow_fbo = 0
        self.shadow_texture = 0
        self.shadow_ready = False

    def texture_coordinates(self, face_vertices, cube=None):
        """UV plus per-vertex torch light encoded in texture-coordinate Z."""
        uv = ((0, 0), (1, 0), (1, 1), (0, 1))
        coords = []
        for index, (u, v) in enumerate(uv):
            vertex = face_vertices[index * 3:index * 3 + 3]
            coords.extend((u, v, self.get_vertex_light(vertex)))
        return 't3f', tuple(coords)

    def sway_attribute(self, face_vertices, cube):
        """Per-vertex wind weight for leaves/grass, using a generic attribute."""
        if self.sway_attribute_location < 0 or cube is None:
            return None
        if not (cube.name.startswith("leaves_") or cube.name == "tall_grass"):
            return None

        base = cube.p[1] - 0.5
        weights = []
        for index in range(4):
            y = face_vertices[index * 3 + 1]
            height = max(0.0, min(1.0, y - base))
            if cube.name == "tall_grass":
                weights.append(height * 1.35)
            else:
                weights.append(0.35 + height * 0.65)
        return f"{self.sway_attribute_location}g1f", tuple(weights)

    def begin_render(self):
        if not self.enabled:
            glUseProgram(0)
            return False
        if self.shader is None:
            self.initialize()
        if not self.shader:
            return False
        glUseProgram(self.shader)
        glUniform1f(self.sky_uniform, self.sky_brightness)
        glUniform1i(self.texture_uniform, 0)
        glUniform3f(self.fog_color_uniform, *self.fog_color)
        glUniform1f(self.fog_start_uniform, self.fog_start)
        glUniform1f(self.fog_end_uniform, self.fog_end)
        glUniform1f(self.time_uniform, self.elapsed)
        modelview = self._matrix(GL_MODELVIEW_MATRIX)
        # The camera matrix is always a rigid transform, so its inverse has a
        # closed form: transpose the rotation and negate the rotated
        # translation. Replacing np.linalg.inv saves a LAPACK call per frame.
        inverse_view = self._invert_rigid(modelview)
        glUniformMatrix4fv(self.inverse_view_uniform, 1, GL_TRUE, inverse_view)
        glUniformMatrix4fv(self.shadow_matrix_uniform, 1, GL_TRUE, self.shadow_matrix)
        glUniform1i(self.shadows_enabled_uniform, 1 if self.shadow_ready else 0)
        glUniform2f(self.shadow_texel_uniform, 1.0 / self.SHADOW_SIZE, 1.0 / self.SHADOW_SIZE)
        quality_index = 0 if self.SHADOW_SIZE <= 512 else 1 if self.SHADOW_SIZE <= 1024 else 2
        glUniform1i(self.shadow_quality_uniform, quality_index)
        glUniform2f(self.cloud_offset_uniform, *self.cloud_offset)
        glUniform1f(self.cloud_coverage_uniform, self.cloud_coverage)
        glUniform1f(self.weather_uniform, self.weather_strength)
        glUniform1f(self.dynamic_lighting_uniform, 1.0 if settings.DYNAMIC_LIGHTING else 0.0)
        glUniform1f(self.leaves_sway_uniform, 1.0 if settings.LEAVES_SWAY else 0.0)

        if self.shadow_ready:
            glActiveTexture(GL_TEXTURE1)
            glBindTexture(GL_TEXTURE_2D, self.shadow_texture)
            glUniform1i(self.shadow_sampler_uniform, 1)
            glActiveTexture(GL_TEXTURE0)
        return True

    def end_render(self):
        if self.shader:
            glUseProgram(0)
        glActiveTexture(GL_TEXTURE0)

    def update(self, dt=0.0):
        self.elapsed += max(0.0, dt)

    def begin_shadow_pass(self, center, light_direction):
        if not self.enabled or not self.shadow_texture:
            self.shadow_ready = False
            return False

        self._saved_viewport = tuple(int(value) for value in glGetIntegerv(GL_VIEWPORT))
        glPushAttrib(GL_ENABLE_BIT | GL_COLOR_BUFFER_BIT | GL_DEPTH_BUFFER_BIT | GL_VIEWPORT_BIT)
        glUseProgram(0)
        glBindFramebuffer(GL_FRAMEBUFFER, self.shadow_fbo)
        glViewport(0, 0, self.SHADOW_SIZE, self.SHADOW_SIZE)
        glColorMask(GL_FALSE, GL_FALSE, GL_FALSE, GL_FALSE)
        glDepthMask(GL_TRUE)
        glClear(GL_DEPTH_BUFFER_BIT)
        glEnable(GL_DEPTH_TEST)
        glEnable(GL_ALPHA_TEST)
        glAlphaFunc(GL_GREATER, 0.5)
        glDisable(GL_BLEND)

        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        radius = self.SHADOW_RADIUS
        glOrtho(-radius, radius, -radius, radius, 1.0, radius * 4.0)

        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        cx, cy, cz = center
        lx, ly, lz = light_direction
        eye = (cx + lx * radius * 2, cy + ly * radius * 2, cz + lz * radius * 2)
        up = (0, 0, 1) if abs(ly) > 0.92 else (0, 1, 0)
        gluLookAt(*eye, cx, cy, cz, *up)

        bias = np.array((
            (0.5, 0.0, 0.0, 0.5),
            (0.0, 0.5, 0.0, 0.5),
            (0.0, 0.0, 0.5, 0.5),
            (0.0, 0.0, 0.0, 1.0),
        ), dtype=np.float32)
        # Single GL query per matrix, avoiding the redundant second read of
        # the modelview that the previous version performed.
        projection = self._matrix(GL_PROJECTION_MATRIX)
        modelview = self._matrix(GL_MODELVIEW_MATRIX)
        self.shadow_matrix = bias @ projection @ modelview
        self.shadow_ready = True
        return True

    def should_update_shadow(self, center, light_direction):
        """Update shadows at a quality-dependent rate or after meaningful movement."""
        if not self.enabled or not self.shadow_texture:
            return False
        if not self.shadow_ready:
            should_update = True
        else:
            rate = {512: 4.0, 1024: 6.0, 2048: 8.0}.get(self.SHADOW_SIZE, 6.0)
            interval = 1.0 / rate
            should_update = self.elapsed - self.last_shadow_time >= interval

        center = tuple(float(value) for value in center)
        direction = tuple(float(value) for value in light_direction)
        if self.last_shadow_center is not None:
            moved = sum((center[i] - self.last_shadow_center[i]) ** 2 for i in range(3))
            should_update = should_update or moved >= 4.0
        if self.last_shadow_direction is not None:
            changed = sum((direction[i] - self.last_shadow_direction[i]) ** 2 for i in range(3))
            should_update = should_update or changed >= 0.0004

        if should_update:
            self.last_shadow_time = self.elapsed
            self.last_shadow_center = center
            self.last_shadow_direction = direction
        return should_update

    def end_shadow_pass(self):
        glMatrixMode(GL_MODELVIEW)
        glPopMatrix()
        glMatrixMode(GL_PROJECTION)
        glPopMatrix()
        glMatrixMode(GL_MODELVIEW)
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        glColorMask(GL_TRUE, GL_TRUE, GL_TRUE, GL_TRUE)
        if self._saved_viewport:
            glViewport(*self._saved_viewport)
        glPopAttrib()

    def _initialize_shadow_map(self):
        try:
            self.shadow_fbo = glGenFramebuffers(1)
            self.shadow_texture = glGenTextures(1)
            glBindTexture(GL_TEXTURE_2D, self.shadow_texture)
            glTexImage2D(GL_TEXTURE_2D, 0, GL_DEPTH_COMPONENT24,
                         self.SHADOW_SIZE, self.SHADOW_SIZE, 0,
                         GL_DEPTH_COMPONENT, GL_FLOAT, None)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_BORDER)
            glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_BORDER)
            glTexParameterfv(GL_TEXTURE_2D, GL_TEXTURE_BORDER_COLOR, (1.0, 1.0, 1.0, 1.0))

            glBindFramebuffer(GL_FRAMEBUFFER, self.shadow_fbo)
            glFramebufferTexture2D(GL_FRAMEBUFFER, GL_DEPTH_ATTACHMENT,
                                   GL_TEXTURE_2D, self.shadow_texture, 0)
            glDrawBuffer(GL_NONE)
            glReadBuffer(GL_NONE)
            complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
            if not complete:
                raise RuntimeError("depth framebuffer is incomplete")
        except Exception as error:
            print(f"Warning: real-time shadows unavailable ({error})")
            self._delete_shadow_map()
        finally:
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

    @staticmethod
    def _matrix(which):
        # PyOpenGL exposes OpenGL's column-major matrix transposed.
        return np.asarray(glGetFloatv(which), dtype=np.float32).reshape(4, 4).T

    @staticmethod
    def _invert_rigid(modelview):
        """Closed-form inverse for a rotation + translation matrix."""
        rotation = modelview[:3, :3]
        translation = modelview[:3, 3]
        rotation_t = rotation.T
        inverse = np.identity(4, dtype=np.float32)
        inverse[:3, :3] = rotation_t
        inverse[:3, 3] = -rotation_t @ translation
        return inverse

    def _dirty_light_region(self, source):
        cubes = getattr(self.gl, "cubes", None)
        if cubes is None:
            return
        size_x, size_y, size_z = cubes.RENDER_CHUNK_SIZE
        radius = int(self.TORCH_RADIUS)
        x, y, z = source
        min_chunk = cubes._get_chunk_key((x - radius, y - radius, z - radius))
        max_chunk = cubes._get_chunk_key((x + radius, y + radius, z + radius))
        for cx in range(min_chunk[0], max_chunk[0] + 1):
            for cy in range(min_chunk[1], max_chunk[1] + 1):
                for cz in range(min_chunk[2], max_chunk[2] + 1):
                    chunk = cubes.render_chunks.get((cx, cy, cz))
                    if chunk is not None:
                        chunk.mark_dirty()