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
uniform mat4 inverseViewMatrix;
uniform mat4 shadowMatrix;

void main() {
    gl_Position = ftransform();
    gl_TexCoord[0] = gl_MultiTexCoord0;
    vertexColor = gl_Color;
    torchLight = gl_MultiTexCoord0.z;
    vec4 viewPosition = gl_ModelViewMatrix * gl_Vertex;
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
uniform vec2 cloudOffset;
uniform float cloudCoverage;
uniform float weatherStrength;
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
    float value = 0.0;
    float amplitude = 0.55;
    for (int i = 0; i < 4; ++i) {
        value += noise21(p) * amplitude;
        p = p * 2.03 + vec2(19.1, 7.7);
        amplitude *= 0.5;
    }
    return value;
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

    float lit = 0.0;
    float bias = 0.0018;
    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            float depth = texture2D(shadowMap,
                projected.xy + vec2(float(x), float(y)) * shadowTexel).r;
            lit += projected.z - bias <= depth ? 1.0 : 0.0;
        }
    }
    return mix(0.38, 1.0, lit / 9.0);
}

void main() {
    vec4 texel = texture2D(texture0, gl_TexCoord[0].xy);
    float dayAmount = smoothstep(0.12, 0.85, skyLight);

    // Complementary-inspired cool shadows and warm daylight.
    vec3 nightSky = vec3(0.34, 0.42, 0.72) * skyLight;
    vec3 daySky = vec3(1.04, 1.00, 0.91) * skyLight;
    vec3 skylight = mix(nightSky, daySky, dayAmount);

    // Smooth warm torch light with a subtle non-disruptive flame flicker.
    float flicker = 0.975 + 0.025 * sin(gameTime * 8.0
                     + worldPosition.x * 1.7 + worldPosition.z * 2.3);
    vec3 torchColor = vec3(1.18, 0.73, 0.38) * torchLight * flicker;
    vec3 illumination = max(skylight, torchColor);

    float sunShadowStrength = dayAmount * 0.82 * (1.0 - weatherStrength * 0.72);
    float sunShadow = mix(1.0, realtimeShadow(), sunShadowStrength);
    float cloudField = cloudNoise((worldPosition.xz + cloudOffset) * 0.018);
    float cloudThreshold = 0.82 - cloudCoverage * 0.45;
    float cloudDensity = smoothstep(cloudThreshold, cloudThreshold + 0.16, cloudField);
    float cloudShadow = 1.0 - cloudDensity * 0.24 * dayAmount;
    illumination *= min(sunShadow, cloudShadow);

    vec3 color = texel.rgb * vertexColor.rgb * illumination;

    // Gentle saturation and contrast grading, avoiding crushed blacks.
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
    SHADOW_SIZE = 1024
    SHADOW_RADIUS = 48.0

    def __init__(self, gl):
        self.gl = gl
        self.enabled = settings.SHADERS
        self.lightSources = set()
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
        self.cloud_offset_uniform = None
        self.cloud_coverage_uniform = None
        self.weather_uniform = None
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
            self.cloud_offset_uniform = glGetUniformLocation(self.shader, "cloudOffset")
            self.cloud_coverage_uniform = glGetUniformLocation(self.shader, "cloudCoverage")
            self.weather_uniform = glGetUniformLocation(self.shader, "weatherStrength")
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
        self._dirty_light_region(source)

    def removeLightSource(self, x, y, z):
        source = (round(x), round(y), round(z))
        if source not in self.lightSources:
            return
        self.lightSources.remove(source)
        self._dirty_light_region(source)

    def set_sky_brightness(self, brightness):
        self.sky_brightness = max(0.06, min(1.0, float(brightness)))

    def set_enabled(self, enabled):
        self.enabled = bool(enabled)
        if not self.enabled:
            glUseProgram(0)
        elif self.shader is None:
            self.initialize()

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
        x, y, z = vertex
        brightest = 0.0
        for lx, ly, lz in self.lightSources:
            dx = x - lx
            dy = y - (ly + 0.35)
            dz = z - lz
            distance = math.sqrt(dx * dx + dy * dy + dz * dz)
            light = 1.0 - distance / self.TORCH_RADIUS
            if light > brightest:
                brightest = light
        return max(0.0, min(1.0, brightest))

    def texture_coordinates(self, face_vertices):
        """UV plus per-vertex torch light encoded in texture-coordinate Z."""
        uv = ((0, 0), (1, 0), (1, 1), (0, 1))
        coords = []
        for index, (u, v) in enumerate(uv):
            vertex = face_vertices[index * 3:index * 3 + 3]
            coords.extend((u, v, self.get_vertex_light(vertex)))
        return 't3f', tuple(coords)

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
        try:
            inverse_view = np.linalg.inv(modelview).astype(np.float32)
        except np.linalg.LinAlgError:
            inverse_view = np.identity(4, dtype=np.float32)
        glUniformMatrix4fv(self.inverse_view_uniform, 1, GL_TRUE, inverse_view)
        glUniformMatrix4fv(self.shadow_matrix_uniform, 1, GL_TRUE, self.shadow_matrix)
        glUniform1i(self.shadows_enabled_uniform, 1 if self.shadow_ready else 0)
        glUniform2f(self.shadow_texel_uniform, 1.0 / self.SHADOW_SIZE, 1.0 / self.SHADOW_SIZE)
        glUniform2f(self.cloud_offset_uniform, *self.cloud_offset)
        glUniform1f(self.cloud_coverage_uniform, self.cloud_coverage)
        glUniform1f(self.weather_uniform, self.weather_strength)

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
        glAlphaFunc(GL_GREATER, 0.1)
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
        self.shadow_matrix = bias @ self._matrix(GL_PROJECTION_MATRIX) @ self._matrix(GL_MODELVIEW_MATRIX)
        self.shadow_ready = True
        return True

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
            glBindFramebuffer(GL_FRAMEBUFFER, 0)
            if not complete:
                raise RuntimeError("depth framebuffer is incomplete")
        except Exception as error:
            print(f"Warning: real-time shadows unavailable ({error})")
            self.shadow_fbo = 0
            self.shadow_texture = 0

    @staticmethod
    def _matrix(which):
        # PyOpenGL exposes OpenGL's column-major matrix transposed.
        return np.asarray(glGetFloatv(which), dtype=np.float32).reshape(4, 4).T

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
                        chunk.dirty = True
