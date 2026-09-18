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

// Improved hash function for better noise distribution
float hash31(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
}

// Smooth 3D value noise with proper interpolation
float valueNoise3(vec3 p) {
    vec3 cell = floor(p);
    vec3 local = fract(p);
    // Quintic interpolation for smoother results (reduces itching)
    local = local * local * local * (local * (local * 6.0 - 15.0) + 10.0);
    
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

// Fractal Brownian Motion with improved octave blending
float fbm(vec3 p) {
    float value = 0.0;
    float amplitude = 0.5;
    float frequency = 1.0;
    
    for (int i = 0; i < 5; i++) {
        value += amplitude * valueNoise3(p * frequency);
        amplitude *= 0.5;
        frequency *= 2.02;
    }
    return value;
}

// Worley noise for cloud cell structure (reduces repetitive patterns)
float worleyNoise(vec3 p) {
    vec3 cell = floor(p);
    vec3 local = fract(p);
    
    float minDist = 1.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            for (int z = -1; z <= 1; z++) {
                vec3 neighbor = vec3(float(x), float(y), float(z));
                vec3 point = vec3(hash31(cell + neighbor + vec3(0.0, 100.0, 200.0)),
                                  hash31(cell + neighbor + vec3(100.0, 0.0, 300.0)),
                                  hash31(cell + neighbor + vec3(200.0, 300.0, 0.0)));
                float dist = length(local - neighbor - point);
                minDist = min(minDist, dist);
            }
        }
    }
    return minDist;
}

float cloudDensity(vec3 world) {
    float height = clamp((world.y - cloudBase) / (cloudTop - cloudBase), 0.0, 1.0);
    float bottom = smoothstep(0.0, 0.2, height);
    float top = 1.0 - smoothstep(0.55, 1.0, height);
    float anvil = mix(0.75, 1.15, smoothstep(0.1, 0.75, height));

    // Animate cloud movement over time
    vec3 samplePosition = vec3(
        (world.x + windOffset.x) * 0.008,
        height * 1.6,
        (world.z + windOffset.y) * 0.008);
    
    // Combine FBM and Worley noise for more realistic cloud shapes
    float baseShape = fbm(samplePosition) * anvil;
    float cellStructure = worleyNoise(samplePosition * 2.5 + vec3(gameTime * 0.002, 0, 0));
    
    // Blend noises for varied cloud appearance
    float shape = mix(baseShape, cellStructure, 0.3);
    
    float threshold = 0.65 - coverage * 0.35 - weatherStrength * 0.1;
    float density = (shape - threshold) * 2.8;
    
    // Add fine detail without causing itching
    float detail = valueNoise3(samplePosition * 5.0 + vec3(0, gameTime * 0.003, 0));
    density = density * (0.85 + 0.15 * detail);
    
    return clamp(density * bottom * top, 0.0, 1.0);
}

void main() {
    vec2 screen = screenUv * 2.0 - 1.0;
    screen.x *= aspectRatio;
    vec3 rayDirection = normalize(cameraForward
        + cameraRight * screen.x * tanHalfFov
        + cameraUp * screen.y * tanHalfFov);

    // Skip nearly horizontal rays
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

    // Increased steps for smoother cloud rendering
    const int STEPS = 16;
    float stepLength = (farDistance - nearDistance) / float(STEPS);
    
    // Temporal reprojection for anti-aliasing (reduces itching)
    float jitter = hash31(vec3(gl_FragCoord.xy, fract(gameTime * 0.1))) * stepLength * 0.5;
    float distanceAlongRay = nearDistance + jitter;
    
    float transmittance = 1.0;
    vec3 accumulated = vec3(0.0);

    for (int stepIndex = 0; stepIndex < STEPS; ++stepIndex) {
        vec3 position = cameraPosition + rayDirection * distanceAlongRay;
        float density = cloudDensity(position);
        
        if (density > 0.003) {
            // Self-shadowing: sample towards the sun
            float towardSun = density;
            if (stepIndex % 3 == 0) {
                towardSun = cloudDensity(position + sunDirection * 6.0);
            }
            
            float lightTransmission = exp(-towardSun * 2.5);
            float forwardScatter = pow(max(dot(rayDirection, sunDirection), 0.0), 8.0);
            float silverLining = forwardScatter * lightTransmission * 0.7;

            // Time-based cloud coloring (BSL style)
            vec3 nightCloud = vec3(0.18, 0.22, 0.30);
            vec3 dayCloud = vec3(0.95, 0.93, 0.90);
            vec3 sunsetCloud = vec3(1.0, 0.78, 0.65);
            
            vec3 shadowColor = mix(
                mix(nightCloud, vec3(0.35, 0.40, 0.50), daylight),
                vec3(0.20, 0.24, 0.32), weatherStrength);
            vec3 litColor = mix(dayCloud, sunsetCloud, 
                smoothstep(0.75, 0.85, fract(gameTime / 24.0)) * 
                (1.0 - smoothstep(0.83, 0.92, fract(gameTime / 24.0))));
            
            vec3 sampleColor = mix(shadowColor, litColor,
                clamp(lightTransmission * 0.7 + silverLining, 0.0, 1.0));

            float extinction = density * stepLength * 0.045;
            float alpha = 1.0 - exp(-extinction);
            accumulated += sampleColor * alpha * transmittance;
            transmittance *= 1.0 - alpha;
            
            if (transmittance < 0.02) {
                break;
            }
        }
        distanceAlongRay += stepLength;
    }

    float alpha = 1.0 - transmittance;
    if (alpha < 0.005) {
        discard;
    }

    // Smooth horizon and distance fading
    float horizonFade = smoothstep(0.0, 0.15, abs(rayDirection.y));
    float distanceFade = 1.0 - smoothstep(drawDistance * 0.65, drawDistance, farDistance);
    alpha *= mix(0.4, 1.0, horizonFade) * max(0.5, distanceFade);

    // Blend with atmospheric scattering
    vec3 atmospheric = mix(horizonColor, skyColor, clamp(rayDirection.y * 2.5, 0.0, 1.0));
    accumulated = mix(atmospheric * alpha * 0.3, accumulated, clamp(alpha * 1.3, 0.0, 1.0));
    
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
