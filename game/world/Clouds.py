"""Volumetric clouds with a layered-puff compatibility fallback."""

import math
import random

import pyglet
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader


CLOUD_VERTEX_SHADER = """
#version 120
varying vec2 screenUv;

void main() {
    gl_Position = gl_Vertex;
    screenUv = gl_MultiTexCoord0.xy;
}
"""


CLOUD_FRAGMENT_SHADER = """
#version 120
varying vec2 screenUv;

uniform vec3 cameraPosition;
uniform vec3 cameraForward;
uniform vec3 cameraRight;
uniform vec3 cameraUp;
uniform vec3 sunDirection;
uniform vec3 skyColor;
uniform vec3 horizonColor;
uniform vec2 windOffset;
uniform float aspectRatio;
uniform float tanHalfFov;
uniform float coverage;
uniform float weatherStrength;
uniform float daylight;
uniform float gameTime;
uniform float drawDistance;
uniform float cloudBase;
uniform float cloudTop;

float hash31(vec3 p) {
    p = fract(p * 0.1031);
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
}

float valueNoise3(vec3 p) {
    vec3 cell = floor(p);
    vec3 local = fract(p);
    local = local * local * (3.0 - 2.0 * local);
    float n000 = hash31(cell);
    float n100 = hash31(cell + vec3(1, 0, 0));
    float n010 = hash31(cell + vec3(0, 1, 0));
    float n110 = hash31(cell + vec3(1, 1, 0));
    float n001 = hash31(cell + vec3(0, 0, 1));
    float n101 = hash31(cell + vec3(1, 0, 1));
    float n011 = hash31(cell + vec3(0, 1, 1));
    float n111 = hash31(cell + vec3(1, 1, 1));
    float lower = mix(mix(n000, n100, local.x), mix(n010, n110, local.x), local.y);
    float upper = mix(mix(n001, n101, local.x), mix(n011, n111, local.x), local.y);
    return mix(lower, upper, local.z);
}

float fbm(vec3 p) {
    float value = valueNoise3(p) * 0.57;
    p = p * 2.03 + vec3(13.1, 7.7, 19.3);
    value += valueNoise3(p) * 0.28;
    p = p * 2.07 + vec3(5.2, 17.4, 3.1);
    value += valueNoise3(p) * 0.15;
    return value;
}

float cloudDensity(vec3 world) {
    float height = clamp((world.y - cloudBase) / (cloudTop - cloudBase), 0.0, 1.0);
    float bottom = smoothstep(0.0, 0.16, height);
    float top = 1.0 - smoothstep(0.62, 1.0, height);
    float anvil = mix(0.78, 1.12, smoothstep(0.15, 0.72, height));

    vec3 samplePosition = vec3(
        (world.x + windOffset.x) * 0.010,
        height * 1.8,
        (world.z + windOffset.y) * 0.010);
    float shape = fbm(samplePosition) * anvil;
    float threshold = 0.71 - coverage * 0.38 - weatherStrength * 0.08;

    // Higher-frequency noise erodes edges into distinct fluffy lobes.
    float detail = valueNoise3(samplePosition * 4.1 + vec3(0, gameTime * 0.004, 0));
    float density = (shape - threshold) * 3.2;
    density -= (1.0 - detail) * 0.24 * (1.0 - clamp(density, 0.0, 1.0));
    return clamp(density * bottom * top, 0.0, 1.0);
}

void main() {
    vec2 screen = screenUv * 2.0 - 1.0;
    screen.x *= aspectRatio;
    vec3 rayDirection = normalize(cameraForward
        + cameraRight * screen.x * tanHalfFov
        + cameraUp * screen.y * tanHalfFov);

    if (abs(rayDirection.y) < 0.0001) {
        discard;
    }

    float first = (cloudBase - cameraPosition.y) / rayDirection.y;
    float second = (cloudTop - cameraPosition.y) / rayDirection.y;
    float nearDistance = max(0.0, min(first, second));
    float farDistance = min(drawDistance, max(first, second));
    if (farDistance <= nearDistance) {
        discard;
    }

    const int STEPS = 20;
    float stepLength = (farDistance - nearDistance) / float(STEPS);
    float jitter = hash31(vec3(gl_FragCoord.xy, gameTime * 0.01));
    float distanceAlongRay = nearDistance + stepLength * jitter;
    float transmittance = 1.0;
    vec3 accumulated = vec3(0.0);

    for (int stepIndex = 0; stepIndex < STEPS; ++stepIndex) {
        vec3 position = cameraPosition + rayDirection * distanceAlongRay;
        float density = cloudDensity(position);
        if (density > 0.005) {
            // One short probe toward the sun gives self-shadowing and bright
            // silver edges without doubling the full ray-march cost.
            float towardSun = cloudDensity(position + sunDirection * 7.0);
            float lightTransmission = exp(-towardSun * 2.8);
            float forwardScatter = pow(max(dot(rayDirection, sunDirection), 0.0), 10.0);
            float silverLining = forwardScatter * lightTransmission * 0.85;

            vec3 shadowColor = mix(vec3(0.31, 0.36, 0.48),
                                   vec3(0.16, 0.19, 0.27), weatherStrength);
            vec3 sunColor = mix(vec3(0.60, 0.66, 0.78),
                                vec3(1.08, 0.96, 0.78), daylight);
            vec3 sampleColor = mix(shadowColor, sunColor,
                                   clamp(lightTransmission + silverLining, 0.0, 1.0));

            float extinction = density * stepLength * 0.055;
            float alpha = 1.0 - exp(-extinction);
            accumulated += sampleColor * alpha * transmittance;
            transmittance *= 1.0 - alpha;
            if (transmittance < 0.025) {
                break;
            }
        }
        distanceAlongRay += stepLength;
    }

    float alpha = 1.0 - transmittance;
    if (alpha < 0.008) {
        discard;
    }

    float horizonFade = smoothstep(0.0, 0.12, abs(rayDirection.y));
    float distanceFade = 1.0 - smoothstep(drawDistance * 0.72, drawDistance, farDistance);
    alpha *= mix(0.35, 1.0, horizonFade) * max(0.45, distanceFade);

    vec3 atmospheric = mix(horizonColor, skyColor, clamp(rayDirection.y * 2.0, 0.0, 1.0));
    accumulated = mix(atmospheric * alpha, accumulated, clamp(alpha * 1.4, 0.0, 1.0));
    gl_FragColor = vec4(accumulated, alpha);
}
"""


class Clouds:
    CLOUD_BASE = 88.0
    CLOUD_TOP = 112.0
    CLOUD_HEIGHT = 96.0
    DRAW_DISTANCE = 360.0
    GRID_RADIUS = 7
    GRID_SPACING = 40.0
    WIND_SPEED = 1.5

    def __init__(self, gl):
        self.gl = gl
        self.wind_x = 0.0
        self.wind_z = 0.0
        self.base_coverage = 0.56
        self.coverage = self.base_coverage
        self.weather_strength = 0.0
        self.clusters = self._build_clusters()
        self.texture = self._build_puff_texture()
        self.volume_shader = None
        self.volume_uniforms = {}
        self._initialize_volume_shader()

    @property
    def shadow_offset(self):
        return self.wind_x, self.wind_z

    def update(self, dt):
        self.wind_x += self.WIND_SPEED * max(0.0, dt)
        self.wind_z += self.WIND_SPEED * 0.28 * max(0.0, dt)
        light = getattr(self.gl, "light", None)
        if light is not None:
            light.set_clouds(self.shadow_offset, self.coverage)

    def set_weather(self, strength):
        self.weather_strength = max(0.0, min(1.0, float(strength)))
        self.coverage = min(0.82, self.base_coverage + self.weather_strength * 0.24)

    def render(self, player, cycle):
        light = getattr(self.gl, "light", None)
        if self.volume_shader and light is not None and light.enabled:
            self._render_volume(player, cycle)
        else:
            self._render_puffs(player, cycle)

    def _render_volume(self, player, cycle):
        yaw = math.radians(player.rotation[1])
        pitch = math.radians(player.rotation[0])
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        sin_yaw = math.sin(yaw)
        cos_yaw = math.cos(yaw)
        forward = (sin_yaw * cos_pitch, -sin_pitch, -cos_yaw * cos_pitch)
        right = (cos_yaw, 0.0, sin_yaw)
        up = (sin_yaw * sin_pitch, cos_pitch, -cos_yaw * sin_pitch)

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        try:
            glDisable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glUseProgram(self.volume_shader)

            self._uniform3("cameraPosition", player.position)
            self._uniform3("cameraForward", forward)
            self._uniform3("cameraRight", right)
            self._uniform3("cameraUp", up)
            self._uniform3("sunDirection", cycle.light_direction)
            self._uniform3("skyColor", cycle.zenith_color)
            self._uniform3("horizonColor", cycle.horizon_color)
            self._uniform2("windOffset", self.shadow_offset)
            self._uniform1("aspectRatio", self.gl.WIDTH / self.gl.HEIGHT)
            self._uniform1("tanHalfFov", math.tan(math.radians(self.gl.fov) / 2))
            self._uniform1("coverage", self.coverage)
            self._uniform1("weatherStrength", self.weather_strength)
            self._uniform1("daylight", cycle.sky_brightness)
            self._uniform1("gameTime", getattr(getattr(self.gl, "light", None), "elapsed", 0.0))
            self._uniform1("drawDistance", self.DRAW_DISTANCE)
            self._uniform1("cloudBase", self.CLOUD_BASE)
            self._uniform1("cloudTop", self.CLOUD_TOP)

            glBegin(GL_QUADS)
            glTexCoord2f(0, 0); glVertex2f(-1, -1)
            glTexCoord2f(1, 0); glVertex2f(1, -1)
            glTexCoord2f(1, 1); glVertex2f(1, 1)
            glTexCoord2f(0, 1); glVertex2f(-1, 1)
            glEnd()
        finally:
            glUseProgram(0)
            glDepthMask(GL_TRUE)
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopAttrib()

    def _render_puffs(self, player, cycle):
        if self.texture is None:
            return
        px, _, pz = player.position
        yaw = math.radians(player.rotation[1])
        pitch = math.radians(player.rotation[0])
        right = (math.cos(yaw), 0.0, math.sin(yaw))
        up = (-math.sin(yaw) * math.sin(pitch),
              math.cos(pitch),
              math.cos(yaw) * math.sin(pitch))

        puffs = []
        wrap = (self.GRID_RADIUS * 2 + 1) * self.GRID_SPACING
        for base_x, base_z, height, cluster in self.clusters:
            x = base_x + self.wind_x
            z = base_z + self.wind_z
            x += round((px - x) / wrap) * wrap
            z += round((pz - z) / wrap) * wrap
            dx, dz = x - px, z - pz
            if dx * dx + dz * dz > self.DRAW_DISTANCE * self.DRAW_DISTANCE:
                continue
            for ox, oy, oz, size, opacity in cluster:
                cx, cy, cz = x + ox, height + oy, z + oz
                distance = (cx - px) ** 2 + (cz - pz) ** 2
                puffs.append((distance, cx, cy, cz, size, opacity))

        puffs.sort(reverse=True)
        daylight = cycle.sky_brightness
        color = (
            0.20 + daylight * (0.80 - self.weather_strength * 0.28),
            0.23 + daylight * (0.75 - self.weather_strength * 0.30),
            0.31 + daylight * (0.69 - self.weather_strength * 0.32),
        )

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
        try:
            glEnable(GL_TEXTURE_2D)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glDisable(GL_CULL_FACE)
            glDepthMask(GL_FALSE)
            self.texture.set_state_recursive()
            glBegin(GL_QUADS)
            for _, cx, cy, cz, size, opacity in puffs:
                rx, ry, rz = (component * size for component in right)
                ux, uy, uz = (component * size * 0.62 for component in up)
                glColor4f(*color, opacity)
                glTexCoord2f(0, 0); glVertex3f(cx - rx - ux, cy - ry - uy, cz - rz - uz)
                glTexCoord2f(1, 0); glVertex3f(cx + rx - ux, cy + ry - uy, cz + rz - uz)
                glTexCoord2f(1, 1); glVertex3f(cx + rx + ux, cy + ry + uy, cz + rz + uz)
                glTexCoord2f(0, 1); glVertex3f(cx - rx + ux, cy - ry + uy, cz - rz + uz)
            glEnd()
            self.texture.unset_state_recursive()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    def _initialize_volume_shader(self):
        try:
            self.volume_shader = compileProgram(
                compileShader(CLOUD_VERTEX_SHADER, GL_VERTEX_SHADER),
                compileShader(CLOUD_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
            )
            names = (
                "cameraPosition", "cameraForward", "cameraRight", "cameraUp",
                "sunDirection", "skyColor", "horizonColor", "windOffset",
                "aspectRatio", "tanHalfFov", "coverage", "weatherStrength",
                "daylight", "gameTime", "drawDistance", "cloudBase", "cloudTop",
            )
            self.volume_uniforms = {
                name: glGetUniformLocation(self.volume_shader, name) for name in names
            }
        except Exception as error:
            print(f"Warning: volumetric clouds unavailable ({error})")
            self.volume_shader = 0

    def _uniform1(self, name, value):
        glUniform1f(self.volume_uniforms[name], float(value))

    def _uniform2(self, name, values):
        glUniform2f(self.volume_uniforms[name], float(values[0]), float(values[1]))

    def _uniform3(self, name, values):
        glUniform3f(self.volume_uniforms[name], float(values[0]), float(values[1]), float(values[2]))

    def _build_clusters(self):
        rng = random.Random(32917)
        clusters = []
        for gx in range(-self.GRID_RADIUS, self.GRID_RADIUS + 1):
            for gz in range(-self.GRID_RADIUS, self.GRID_RADIUS + 1):
                if rng.random() > self.coverage:
                    continue
                base_x = gx * self.GRID_SPACING + rng.uniform(-11, 11)
                base_z = gz * self.GRID_SPACING + rng.uniform(-11, 11)
                height = self.CLOUD_HEIGHT + rng.uniform(-3, 4)
                puffs = []
                for _ in range(rng.randint(5, 9)):
                    angle = rng.uniform(0, math.tau)
                    radius = rng.uniform(0, 13)
                    puffs.append((math.cos(angle) * radius, rng.uniform(-2.5, 3.5),
                                  math.sin(angle) * radius, rng.uniform(8, 15),
                                  rng.uniform(0.22, 0.42)))
                clusters.append((base_x, base_z, height, tuple(puffs)))
        return tuple(clusters)

    @staticmethod
    def _build_puff_texture(size=64):
        pixels = bytearray(size * size * 4)
        for y in range(size):
            for x in range(size):
                nx = (x + 0.5) / size * 2 - 1
                ny = (y + 0.5) / size * 2 - 1
                radius = math.sqrt(nx * nx + ny * ny)
                edge = max(0.0, min(1.0, (1.0 - radius) * 3.0))
                noise = (math.sin(x * 0.73 + y * 0.31)
                         + math.sin(x * 0.19 - y * 0.57)) * 0.035
                alpha = max(0.0, min(1.0, edge + noise))
                offset = (y * size + x) * 4
                pixels[offset:offset + 4] = bytes((255, 255, 255, round(alpha * 255)))
        image = pyglet.image.ImageData(size, size, "RGBA", bytes(pixels), pitch=size * 4)
        texture = image.get_texture()
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return pyglet.graphics.TextureGroup(texture)
