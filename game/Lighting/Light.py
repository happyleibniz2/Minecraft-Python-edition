"""Smooth skylight and torch lighting for the compatibility renderer."""

import math

from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader


VERTEX_SHADER = """
#version 120
varying vec4 vertexColor;
varying float torchLight;

void main() {
    gl_Position = ftransform();
    gl_TexCoord[0] = gl_MultiTexCoord0;
    vertexColor = gl_Color;
    torchLight = gl_MultiTexCoord0.z;
}
"""


FRAGMENT_SHADER = """
#version 120
uniform sampler2D texture0;
uniform float skyLight;
varying vec4 vertexColor;
varying float torchLight;

void main() {
    vec4 texel = texture2D(texture0, gl_TexCoord[0].xy);
    float brightness = max(skyLight, torchLight);
    vec3 neutral = vec3(brightness);
    vec3 warm = vec3(brightness * 1.08, brightness * 0.88, brightness * 0.68);
    vec3 lightColor = mix(neutral, warm, clamp(torchLight * 0.45, 0.0, 0.45));
    gl_FragColor = vec4(texel.rgb * vertexColor.rgb * lightColor,
                        texel.a * vertexColor.a);
}
"""


class Light:
    TORCH_RADIUS = 15.0

    def __init__(self, gl):
        self.gl = gl
        self.lightSources = set()
        self.sky_brightness = 1.0
        self.shader = None
        self.sky_uniform = None
        self.texture_uniform = None

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
        if self.shader is None:
            self.initialize()
        if not self.shader:
            return False
        glUseProgram(self.shader)
        glUniform1f(self.sky_uniform, self.sky_brightness)
        glUniform1i(self.texture_uniform, 0)
        return True

    def end_render(self):
        if self.shader:
            glUseProgram(0)

    def update(self):
        """Kept for the Scene API; shader uniforms update in begin_render."""

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
