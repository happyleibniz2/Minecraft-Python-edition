"""Volumetric cloud rendering with layered-puff compatibility fallback.

The ULTRA pipeline is deliberately uncompromising:
* 3D GLSL Perlin noise and 3D Worley/cellular noise
* 6-octave Perlin FBM for the base shape, 3-octave Worley FBM for billows
* Full volumetric ray marching (256 steps ULTRA, 384 INSANE)
* Beer-Lambert extinction
* Dual-lobe Henyey-Greenstein phase function (silver lining)
* Powder effect plus a secondary light sample for internal glow
* Height-gradient cloud slab and atmospheric ambient tint

If GLSL 330 compilation fails, or the shaders option is disabled, the module
falls back to the original 2D billboard puff system.
"""

import ctypes
import math
import random

import numpy as np

# Must run before pyglet.gl is imported: pyglet 2.x otherwise creates a hidden
# 1x1 shadow window and a second GL context, and the game must own exactly one
# window/context.
import pyglet
pyglet.options['shadow_window'] = False
from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

import settings


# ---------------------------------------------------------------------------
# GLSL 330 core full-screen triangle
# ---------------------------------------------------------------------------
CLOUD_VERTEX_SHADER = """
#version 330 core

layout(location = 0) in vec2 aPosition;
layout(location = 1) in vec2 aTexCoord;
out vec2 screenUv;

void main() {
    gl_Position = vec4(aPosition, 0.0, 1.0);
    screenUv = aTexCoord;
}
"""


CLOUD_FRAGMENT_SHADER = """
#version 330 core

in vec2 screenUv;
out vec4 fragColor;

uniform vec3 cameraPosition;
uniform vec3 cameraForward;
uniform vec3 cameraRight;
uniform vec3 cameraUp;
uniform vec3 sunDirection;
uniform vec3 sunColor;
uniform vec3 skyColor;
uniform vec3 horizonColor;
uniform vec3 cloudBoxMin;
uniform vec3 cloudBoxMax;
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
uniform int qualityLevel; // 0 LOW, 1 MEDIUM, 2 HIGH, 3 ULTRA, 4 INSANE

const int MAX_STEPS = 256;       // ULTRA
const int INSANE_STEPS = 384;
const float PI = 3.14159265359;

// ---------------------------------------------------------------------------
// Hashes
// ---------------------------------------------------------------------------
float hash12(vec2 p) {
    vec3 p3 = fract(vec3(p.xyx) * 0.1031);
    p3 += dot(p3, p3.yzx + 33.33);
    return fract((p3.x + p3.y) * p3.z);
}

vec3 hash33(vec3 p3) {
    p3 = fract(p3 * vec3(0.1031, 0.1030, 0.0973));
    p3 += dot(p3, p3.yxz + 33.33);
    return fract((p3.xxy + p3.yxx) * p3.zyx);
}

// ---------------------------------------------------------------------------
// Classic 3D Perlin noise (Stefan Gustavson / webgl-noise style)
// ---------------------------------------------------------------------------
vec3 mod289(vec3 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 mod289(vec4 x) { return x - floor(x * (1.0 / 289.0)) * 289.0; }
vec4 permute(vec4 x) { return mod289(((x * 34.0) + 1.0) * x); }
vec4 taylorInvSqrt(vec4 r) {
    return 1.79284291400159 - 0.85373472095314 * r;
}

float perlinNoise3(vec3 P) {
    vec3 Pi0 = floor(P);
    vec3 Pi1 = Pi0 + vec3(1.0);
    Pi0 = mod289(Pi0);
    Pi1 = mod289(Pi1);

    vec3 Pf0 = fract(P);
    vec3 Pf1 = Pf0 - vec3(1.0);

    vec4 ix = vec4(Pi0.x, Pi1.x, Pi0.x, Pi1.x);
    vec4 iy = vec4(Pi0.yy, Pi1.yy);
    vec4 iz0 = Pi0.zzzz;
    vec4 iz1 = Pi1.zzzz;

    vec4 ixy = permute(permute(ix) + iy);
    vec4 ixy0 = permute(ixy + iz0);
    vec4 ixy1 = permute(ixy + iz1);

    vec4 gx0 = ixy0 * (1.0 / 7.0);
    vec4 gy0 = fract(floor(gx0) * (1.0 / 7.0)) - 0.5;
    gx0 = fract(gx0);
    vec4 gz0 = vec4(0.5) - abs(gx0) - abs(gy0);
    vec4 sz0 = step(gz0, vec4(0.0));
    gx0 -= sz0 * (step(0.0, gx0) - 0.5);
    gy0 -= sz0 * (step(0.0, gy0) - 0.5);

    vec4 gx1 = ixy1 * (1.0 / 7.0);
    vec4 gy1 = fract(floor(gx1) * (1.0 / 7.0)) - 0.5;
    gx1 = fract(gx1);
    vec4 gz1 = vec4(0.5) - abs(gx1) - abs(gy1);
    vec4 sz1 = step(gz1, vec4(0.0));
    gx1 -= sz1 * (step(0.0, gx1) - 0.5);
    gy1 -= sz1 * (step(0.0, gy1) - 0.5);

    vec3 g000 = vec3(gx0.x, gy0.x, gz0.x);
    vec3 g100 = vec3(gx0.y, gy0.y, gz0.y);
    vec3 g010 = vec3(gx0.z, gy0.z, gz0.z);
    vec3 g110 = vec3(gx0.w, gy0.w, gz0.w);
    vec3 g001 = vec3(gx1.x, gy1.x, gz1.x);
    vec3 g101 = vec3(gx1.y, gy1.y, gz1.y);
    vec3 g011 = vec3(gx1.z, gy1.z, gz1.z);
    vec3 g111 = vec3(gx1.w, gy1.w, gz1.w);

    vec4 norm0 = taylorInvSqrt(vec4(
        dot(g000, g000), dot(g100, g100),
        dot(g010, g010), dot(g110, g110)));
    g000 *= norm0.x;
    g100 *= norm0.y;
    g010 *= norm0.z;
    g110 *= norm0.w;

    vec4 norm1 = taylorInvSqrt(vec4(
        dot(g001, g001), dot(g101, g101),
        dot(g011, g011), dot(g111, g111)));
    g001 *= norm1.x;
    g101 *= norm1.y;
    g011 *= norm1.z;
    g111 *= norm1.w;

    float n000 = dot(g000, Pf0);
    float n100 = dot(g100, vec3(Pf1.x, Pf0.yz));
    float n010 = dot(g010, vec3(Pf0.x, Pf1.y, Pf0.z));
    float n110 = dot(g110, vec3(Pf1.xy, Pf0.z));
    float n001 = dot(g001, vec3(Pf0.xy, Pf1.z));
    float n101 = dot(g101, vec3(Pf1.x, Pf0.y, Pf1.z));
    float n011 = dot(g011, vec3(Pf0.x, Pf1.yz));
    float n111 = dot(g111, Pf1);

    vec3 fadeXYZ = Pf0 * Pf0 * Pf0 * (Pf0 * (Pf0 * 6.0 - 15.0) + 10.0);
    vec4 nZ = mix(
        vec4(n000, n100, n010, n110),
        vec4(n001, n101, n011, n111),
        fadeXYZ.z);
    vec2 nYZ = mix(nZ.xy, nZ.zw, fadeXYZ.y);
    float nXYZ = mix(nYZ.x, nYZ.y, fadeXYZ.x);
    return 2.2 * nXYZ;
}

// ---------------------------------------------------------------------------
// 3D Worley / cellular noise
// ---------------------------------------------------------------------------
float worleyNoise(vec3 p, float cellularScale) {
    vec3 scaled = p * cellularScale;
    vec3 cell = floor(scaled);
    vec3 local = fract(scaled);
    float minDist = 1.0;

    for (int x = -1; x <= 1; ++x) {
        for (int y = -1; y <= 1; ++y) {
            for (int z = -1; z <= 1; ++z) {
                vec3 neighbor = vec3(float(x), float(y), float(z));
                vec3 point = hash33(cell + neighbor);
                float dist = length(local - neighbor - point);
                minDist = min(minDist, dist);
            }
        }
    }
    return minDist;
}

// ---------------------------------------------------------------------------
// FBM (fixed loop bounds with early break so every GLSL 330 driver accepts it)
// ---------------------------------------------------------------------------
float fbmPerlin(vec3 p, int octaves) {
    float value = 0.0;
    float amplitude = 0.5;
    float frequency = 1.0;
    for (int i = 0; i < 8; ++i) {
        if (i >= octaves) break;
        value += amplitude * perlinNoise3(p * frequency);
        amplitude *= 0.5;
        frequency *= 2.02;
    }
    return value;
}

float fbmWorley(vec3 p, int octaves) {
    float value = 0.0;
    float amplitude = 0.5;
    float frequency = 1.0;
    for (int i = 0; i < 5; ++i) {
        if (i >= octaves) break;
        value += amplitude * worleyNoise(p, frequency);
        amplitude *= 0.5;
        frequency *= 2.0;
    }
    return value;
}

// ---------------------------------------------------------------------------
// Density field
// ---------------------------------------------------------------------------
// A low-frequency warp keeps the cloud base from reading as a perfectly flat
// sheet while the height gradient still gives it a defined slab shape.
float cloudHeight(vec3 world) {
    vec2 horizontal = vec2(
        world.x + windOffset.x, world.z + windOffset.y);
    float baseWarp = perlinNoise3(vec3(horizontal * 0.030, 0.0));
    float topWarp = perlinNoise3(
        vec3(horizontal * 0.022 + vec2(31.7, -17.3), 0.0));
    float localBase = cloudBase + (baseWarp * 0.5 + 0.5) * 8.0;
    float localTop = cloudTop - (topWarp * 0.5 + 0.5) * 22.0;
    return (world.y - localBase) / max(localTop - localBase, 1.0);
}

float cloudDensity(vec3 world) {
    float height = cloudHeight(world);
    if (height <= 0.0 || height >= 1.0) {
        return 0.0;
    }

    // Flat cloud base, fluffy top, thin anvil edge.
    float bottom = smoothstep(0.0, 0.06, height);
    float top = 1.0 - smoothstep(0.94, 1.0, height);
    float heightGradient = bottom * top;

    vec3 samplePosition = vec3(
        (world.x + windOffset.x) * 0.025,
        height * 2.4,
        (world.z + windOffset.y) * 0.025
    );

    // 6-octave Perlin FBM: base billowy mass.
    float baseShape = fbmPerlin(samplePosition, 6);

    // 3-octave Worley FBM: cauliflower / cellular erosion.
    float billow = 1.0 - fbmWorley(
        samplePosition * 4.0 + vec3(gameTime * 0.0004, 0.0, gameTime * 0.0003),
        3
    );

    float shape = mix(baseShape * 0.5 + 0.5, billow, 0.65);
    float threshold = 0.60 - coverage * 0.30 - weatherStrength * 0.12;
    float density = smoothstep(threshold, threshold + 0.25, shape) * 1.8;

    // 3-octave high-frequency detail breaks up the silhouette.
    float detail = fbmPerlin(
        samplePosition * 7.0 + vec3(gameTime * 0.0008, 0.0, gameTime * 0.0006),
        3
    );
    density *= 0.75 + 0.25 * (detail * 0.5 + 0.5);

    return clamp(density * heightGradient, 0.0, 1.0);
}

// Cheap density used only inside the light march.
float cloudDensityLight(vec3 world) {
    float height = cloudHeight(world);
    if (height <= 0.0 || height >= 1.0) {
        return 0.0;
    }
    float heightGradient = smoothstep(0.0, 0.06, height)
                         * (1.0 - smoothstep(0.94, 1.0, height));

    vec3 samplePosition = vec3(
        (world.x + windOffset.x) * 0.025,
        height * 2.4,
        (world.z + windOffset.y) * 0.025
    );
    float baseShape = fbmPerlin(samplePosition, 2);
    float billow = 1.0 - worleyNoise(samplePosition * 4.0, 1.0);
    float shape = mix(baseShape * 0.5 + 0.5, billow, 0.65);
    float threshold = 0.60 - coverage * 0.30 - weatherStrength * 0.12;
    return clamp(
        smoothstep(threshold, threshold + 0.25, shape)
        * 1.8 * heightGradient, 0.0, 1.0);
}

// ---------------------------------------------------------------------------
// Scattering
// ---------------------------------------------------------------------------
float henyeyGreenstein(float cosTheta, float g) {
    float g2 = g * g;
    float denom = max(1e-4, 1.0 + g2 - 2.0 * g * cosTheta);
    return (1.0 - g2) / (4.0 * PI * pow(denom, 1.5));
}

float dualLobePhase(float cosTheta) {
    // Strong forward lobe -> silver lining, weak backward lobe -> soft body.
    return henyeyGreenstein(cosTheta, 0.76) * 0.80
         + henyeyGreenstein(cosTheta, -0.35) * 0.20;
}

// ---------------------------------------------------------------------------
// Robust ray/AABB intersection
// ---------------------------------------------------------------------------
vec3 safeDirection(vec3 dir) {
    // sign(0.0) is 0.0 in GLSL, which would turn invDir into inf. Bias the
    // sign test so an exactly axis-aligned ray still gets a finite slab test.
    vec3 magnitude = max(abs(dir), vec3(1e-6));
    return sign(dir + vec3(1e-9)) * magnitude;
}

void main() {
    vec2 screen = screenUv * 2.0 - 1.0;
    screen.x *= aspectRatio;

    vec3 rayDir = normalize(
        cameraForward
        + cameraRight * screen.x * tanHalfFov
        + cameraUp * screen.y * tanHalfFov
    );

    vec3 invDir = 1.0 / safeDirection(rayDir);
    vec3 t0 = (cloudBoxMin - cameraPosition) * invDir;
    vec3 t1 = (cloudBoxMax - cameraPosition) * invDir;
    vec3 tMin = min(t0, t1);
    vec3 tMax = max(t0, t1);

    float tNear = max(max(tMin.x, tMin.y), max(tMin.z, 0.0));
    float tFar = min(min(tMax.x, tMax.y), min(tMax.z, drawDistance));

    if (tFar <= tNear) {
        fragColor = vec4(0.0);
        return;
    }

    int maxSteps;
    float emptyMultiplier;
    if (qualityLevel >= 4) {         // INSANE
        maxSteps = INSANE_STEPS;
        emptyMultiplier = 1.0;
    } else if (qualityLevel >= 3) {  // ULTRA
        maxSteps = MAX_STEPS;
        emptyMultiplier = 1.0;
    } else if (qualityLevel >= 2) {  // HIGH
        maxSteps = 128;
        emptyMultiplier = 1.5;
    } else if (qualityLevel >= 1) {  // MEDIUM
        maxSteps = 64;
        emptyMultiplier = 2.0;
    } else {                         // LOW
        maxSteps = 48;
        emptyMultiplier = 2.5;
    }

    float stepSize = (tFar - tNear) / float(maxSteps);

    // Hash jitter kills banding without any temporal history buffer.
    float jitter = hash12(gl_FragCoord.xy + vec2(gameTime * 17.0)) * stepSize;
    float t = tNear + jitter;

    float transmittance = 1.0;
    vec3 scattered = vec3(0.0);
    float extinctionCoefficient = 0.24;
    float ambientStrength = 0.18 + 0.30 * daylight;

    for (int i = 0; i < maxSteps; ++i) {
        if (t >= tFar || transmittance < 0.01) {
            break;
        }

        vec3 position = cameraPosition + rayDir * t;
        float density = cloudDensity(position);

        if (density > 0.003) {
            // Beer-Lambert extinction for this segment.
            float extinction = density * stepSize * extinctionCoefficient;
            float stepAlpha = 1.0 - exp(-extinction);

            // Secondary light march with exponentially growing samples.
            float lightDensity = 0.0;
            float lightDistance = 1.5;
            for (int j = 0; j < 5; ++j) {
                lightDensity += cloudDensityLight(
                    position + sunDirection * lightDistance) * lightDistance;
                lightDistance *= 1.9;
            }
            float lightTransmittance = exp(-lightDensity * 0.12);

            // Dual-lobe Henyey-Greenstein phase.
            float cosTheta = dot(rayDir, sunDirection);
            float phase = dualLobePhase(cosTheta);

            // Powder effect: thin fringes receive less multiply-scattered
            // light, keeping the silhouette soft instead of flat.
            float powder = 1.0 - exp(-density * 2.5);
            float powderFactor = mix(0.62, 1.0, powder);

            // Cheap multiple-scattering approximation: internal glow.
            float multipleScatter = (1.0 - lightTransmittance) * 0.35
                                  + lightTransmittance * 0.10;

            float heightFraction = clamp(
                (position.y - cloudBase) / (cloudTop - cloudBase), 0.0, 1.0);
            vec3 ambientColor = mix(horizonColor, skyColor, heightFraction);
            ambientColor = mix(ambientColor, vec3(0.85, 0.90, 1.0), 0.45);
            vec3 ambient = ambientColor * ambientStrength
                         + vec3(0.020, 0.025, 0.040);
            // The constant term is a cheap diffuse/multiple-scattering base;
            // the phase term adds the forward-scattered silver lining.
            vec3 direct = sunColor * lightTransmittance
                        * (phase * 1.35 + 0.45) * powderFactor;
            vec3 cloudColor = direct
                            + ambient
                            + sunColor * multipleScatter * 0.22;

            scattered += cloudColor * stepAlpha * transmittance;
            transmittance *= 1.0 - stepAlpha;
            t += stepSize;
        } else {
            // Empty-space acceleration only below ULTRA; ULTRA takes the
            // uncompromising uniform-step path.
            t += stepSize * emptyMultiplier;
        }
    }

    float alpha = 1.0 - transmittance;
    if (alpha < 0.005) {
        fragColor = vec4(0.0);
        return;
    }

    float horizonFade = smoothstep(0.0, 0.10, abs(rayDir.y));
    float distanceFade = 1.0 - smoothstep(drawDistance * 0.75, drawDistance, tFar);
    alpha *= mix(0.55, 1.0, horizonFade) * distanceFade;

    // Convert the premultiplied scattering integral to straight alpha.
    vec3 color = scattered / max(alpha, 1e-4);
    vec3 atmospheric = mix(
        horizonColor, skyColor, clamp(rayDir.y * 2.5, 0.0, 1.0));
    color = mix(atmospheric, color, clamp(alpha * 1.5, 0.0, 1.0));

    fragColor = vec4(color, alpha);
}
"""


class Clouds:
    CLOUD_BASE = 88.0
    CLOUD_TOP = 128.0
    CLOUD_HEIGHT = 96.0
    DRAW_DISTANCE = 360.0
    GRID_RADIUS = 7
    GRID_SPACING = 40.0
    WIND_SPEED = 1.5

    QUALITY_LEVELS = {
        "LOW": 0,
        "MEDIUM": 1,
        "HIGH": 2,
        "ULTRA": 3,
        "INSANE": 4,
    }

    def __init__(self, gl):
        self.gl = gl
        self.wind_x = 0.0
        self.wind_z = 0.0
        self.base_coverage = 0.56
        self.coverage = self.base_coverage
        self.weather_strength = 0.0
        self.clusters = self._build_clusters()
        self.texture = self._build_puff_texture()
        self.volume_shader = 0
        self.volume_uniforms = {}
        self.volume_vao = 0
        self.volume_vbo = 0
        self.volume_quality = self._resolve_quality()
        self._initialize_volume_shader()

    def _resolve_quality(self):
        quality = str(getattr(settings, "CLOUD_QUALITY", "ULTRA")).upper()
        return self.QUALITY_LEVELS.get(quality, 3)

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

    def set_quality(self, quality):
        """Switch cloud quality at runtime. Unknown values select LOW."""
        level = self.QUALITY_LEVELS.get(str(quality).upper(), 0)
        self.volume_quality = level

    def render(self, player, cycle):
        light = getattr(self.gl, "light", None)
        if self.volume_shader and light is not None and light.enabled:
            try:
                self._render_volume(player, cycle)
                return
            except Exception as error:
                # Driver lost the context, VAO unsupported at runtime, etc.
                print(f"Warning: volumetric clouds disabled ({error})")
                self.volume_shader = 0
        self._render_puffs(player, cycle)

    def _render_volume(self, player, cycle):
        yaw = math.radians(player.rotation[1])
        pitch = math.radians(player.rotation[0])
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        sin_yaw = math.sin(yaw)
        cos_yaw = math.cos(yaw)

        # Camera basis vectors matching the player's yaw/pitch.
        forward = (sin_yaw * cos_pitch, -sin_pitch, -cos_yaw * cos_pitch)
        right = (cos_yaw, 0.0, sin_yaw)
        up = (sin_yaw * sin_pitch, cos_pitch, -cos_yaw * sin_pitch)

        px, _, pz = player.position
        # The vertical slab is the real volume. A generous horizontal extent
        # keeps the AABB from cutting the cloud layer off at a visible square
        # edge; drawDistance still bounds the actual ray march.
        half_extent = self.DRAW_DISTANCE * 2.0
        box_min = (px - half_extent, self.CLOUD_BASE, pz - half_extent)
        box_max = (px + half_extent, self.CLOUD_TOP, pz + half_extent)

        # Neutral white at noon, warm at sunset, dim blue-grey at night.
        daylight = float(cycle.sky_brightness)
        horizon = np.asarray(cycle.horizon_color, dtype=np.float32)
        warmth = max(0.0, min(
            1.0, (float(horizon[0]) - float(horizon[2])) * 2.0 + 0.15))
        neutral = (
            np.array((0.10, 0.11, 0.14), dtype=np.float32)
            + np.array((0.90, 0.86, 0.72), dtype=np.float32) * daylight
        )
        warm = np.array((1.0, 0.45, 0.18), dtype=np.float32)
        sun_color = neutral * (1.0 - warmth * 0.45) + warm * (warmth * 0.45)
        sun_color = tuple(
            float(component)
            for component in np.clip(sun_color, 0.0, 1.0))

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT
                     | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
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
            self._uniform3("sunColor", sun_color)
            self._uniform3("skyColor", cycle.zenith_color)
            self._uniform3("horizonColor", cycle.horizon_color)
            self._uniform3("cloudBoxMin", box_min)
            self._uniform3("cloudBoxMax", box_max)
            self._uniform2("windOffset", self.shadow_offset)
            self._uniform1("aspectRatio", self.gl.WIDTH / self.gl.HEIGHT)
            self._uniform1("tanHalfFov",
                           math.tan(math.radians(self.gl.fov) / 2))
            self._uniform1("coverage", self.coverage)
            self._uniform1("weatherStrength", self.weather_strength)
            self._uniform1("daylight", cycle.sky_brightness)
            self._uniform1(
                "gameTime",
                getattr(getattr(self.gl, "light", None), "elapsed", 0.0))
            self._uniform1("drawDistance", self.DRAW_DISTANCE)
            self._uniform1("cloudBase", self.CLOUD_BASE)
            self._uniform1("cloudTop", self.CLOUD_TOP)
            glUniform1i(
                self.volume_uniforms["qualityLevel"], self.volume_quality)

            glBindVertexArray(self.volume_vao)
            glDrawArrays(GL_TRIANGLES, 0, 3)
            glBindVertexArray(0)
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

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT
                     | GL_COLOR_BUFFER_BIT | GL_CURRENT_BIT)
        try:
            # TextureGroup binds on unit 0; select it before enabling the
            # target in case the lighting pass left another unit active.
            glActiveTexture(GL_TEXTURE0)
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
                glTexCoord2f(0, 0)
                glVertex3f(cx - rx - ux, cy - ry - uy, cz - rz - uz)
                glTexCoord2f(1, 0)
                glVertex3f(cx + rx - ux, cy + ry - uy, cz + rz - uz)
                glTexCoord2f(1, 1)
                glVertex3f(cx + rx + ux, cy + ry + uy, cz + rz + uz)
                glTexCoord2f(0, 1)
                glVertex3f(cx - rx + ux, cy - ry + uy, cz - rz + uz)
            glEnd()
            self.texture.unset_state_recursive()
        finally:
            glDepthMask(GL_TRUE)
            glPopAttrib()

    def _initialize_volume_shader(self):
        try:
            shader = compileProgram(
                compileShader(CLOUD_VERTEX_SHADER, GL_VERTEX_SHADER),
                compileShader(CLOUD_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
            )
            names = (
                "cameraPosition", "cameraForward", "cameraRight", "cameraUp",
                "sunDirection", "sunColor", "skyColor", "horizonColor",
                "cloudBoxMin", "cloudBoxMax", "windOffset",
                "aspectRatio", "tanHalfFov", "coverage", "weatherStrength",
                "daylight", "gameTime", "drawDistance", "cloudBase", "cloudTop",
                "qualityLevel",
            )
            self.volume_uniforms = {
                name: glGetUniformLocation(shader, name) for name in names
            }

            # Full-screen triangle: three vertices cover the clip-space quad.
            # Each vertex is (x, y, u, v).
            vertices = np.array([
                -1.0, -1.0, 0.0, 0.0,
                 3.0, -1.0, 2.0, 0.0,
                -1.0,  3.0, 0.0, 2.0,
            ], dtype=np.float32)

            vao = GLuint()
            vbo = GLuint()
            glGenVertexArrays(1, vao)
            glGenBuffers(1, vbo)
            glBindVertexArray(vao)
            glBindBuffer(GL_ARRAY_BUFFER, vbo)
            glBufferData(GL_ARRAY_BUFFER, vertices.nbytes, vertices,
                         GL_STATIC_DRAW)
            glEnableVertexAttribArray(0)
            glVertexAttribPointer(
                0, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(0))
            glEnableVertexAttribArray(1)
            glVertexAttribPointer(
                1, 2, GL_FLOAT, GL_FALSE, 16, ctypes.c_void_p(8))
            glBindVertexArray(0)
            glBindBuffer(GL_ARRAY_BUFFER, 0)

            self.volume_shader = shader
            self.volume_vao = vao.value
            self.volume_vbo = vbo.value
        except Exception as error:
            print(f"Warning: volumetric clouds unavailable ({error})")
            self.volume_shader = 0
            self.volume_uniforms = {}

    def _uniform1(self, name, value):
        glUniform1f(self.volume_uniforms[name], float(value))

    def _uniform2(self, name, values):
        glUniform2f(self.volume_uniforms[name],
                    float(values[0]), float(values[1]))

    def _uniform3(self, name, values):
        glUniform3f(self.volume_uniforms[name],
                    float(values[0]), float(values[1]), float(values[2]))

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
                    puffs.append((
                        math.cos(angle) * radius,
                        rng.uniform(-2.5, 3.5),
                        math.sin(angle) * radius,
                        rng.uniform(8, 15),
                        rng.uniform(0.22, 0.42),
                    ))
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
                pixels[offset:offset + 4] = bytes(
                    (255, 255, 255, round(alpha * 255)))
        image = pyglet.image.ImageData(
            size, size, "RGBA", bytes(pixels), pitch=size * 4)
        texture = image.get_texture()
        glBindTexture(texture.target, texture.id)
        glTexParameteri(texture.target, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(texture.target, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return pyglet.graphics.TextureGroup(texture)
