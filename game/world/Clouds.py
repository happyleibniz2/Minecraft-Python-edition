"""Volumetric clouds with a layered-puff compatibility fallback.

The volume pass is a physically-inspired approximation of in-scattering in a
participating medium, in the spirit of Unreal Engine's volumetric clouds:

* **Density field**: a Perlin-ish FBM base shape blended with Worley cell
  structure, eroded by a high-frequency detail noise at the edges
  (``1 - density`` weighting) so cores stay thick and edges turn wispy.
* **Lighting**: Beer-Lambert transmittance toward the sun computed by a
  secondary, lower-sample light march (true self-shadowing), a dual-lobe
  Henyey-Greenstein phase function (strong forward scatter + softer backward
  lobe), a powder term that keeps cloud cores from flattening out, and an
  ambient term approximating one octave of multiple scattering.
* **Sampling discipline**: interleaved-gradient-noise jittering converts
  banding into high-frequency noise, adaptive stepping takes large strides
  through empty space and fine ones inside cloud, and the march early-outs
  once transmittance falls below threshold.

Quality tiers (``settings.CLOUD_QUALITY``) scale the sample counts and the
feature set. ``POTATO`` is the cheapest practical march (4 steps, one light
sample); the billboard puffs remain only as the fallback for contexts where
the volume shader is unavailable.
"""

import logging
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
uniform float sunHeight;      /* sin(sun_angle): the SAME sun driving the
                                  sky and the shadow map; the twilight tint
                                  is derived from its elevation */
uniform float drawDistance;
uniform float cloudBase;
uniform float cloudTop;
uniform float uSteps;        /* view-march step cap        */
uniform float uSunSamples;   /* light-march sample cap     */
uniform float uDetail;       /* erosion detail: 0..2       */
uniform float uPowder;       /* powder sugar term: 0/1     */
uniform float uAdaptive;     /* adaptive step sizes: 0/1   */
uniform float uDualLobe;     /* dual-lobe HG phase: 0/1    */

// Hash / value noise ------------------------------------------------
float hash31(vec3 p) {
    p = fract(p * vec3(0.1031, 0.1030, 0.0973));
    p += dot(p, p.yzx + 33.33);
    return fract((p.x + p.y) * p.z);
}

float valueNoise3(vec3 p) {
    vec3 cell = floor(p);
    vec3 local = fract(p);
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

// Density field: Perlin-Worley base with edge erosion ---------------
float cloudDensity(vec3 world) {
    float height = clamp((world.y - cloudBase) / (cloudTop - cloudBase), 0.0, 1.0);
    float bottom = smoothstep(0.0, 0.18, height);
    float top = 1.0 - smoothstep(0.55, 1.0, height);
    // Top-heavy cumulus: billowing volume above a flat base.
    float anvil = mix(0.7, 1.3, smoothstep(0.1, 0.75, height));

    // Height gradient for volumetric depth (bottom darker, top brighter).
    // NOTE: written as (1 - smoothstep(0.65, 1.0, height)); the previous
    // reversed form smoothstep(1.0, 0.65, height) is UNDEFINED in GLSL for
    // edge0 >= edge1 even though common drivers happen to compute it.
    float heightGradient = smoothstep(0.0, 0.25, height)
                        * (1.0 - smoothstep(0.65, 1.0, height));

    vec3 samplePosition = vec3(
        (world.x + windOffset.x) * 0.006,
        height * 1.6,
        (world.z + windOffset.y) * 0.006);

    // Perlin-ish base shape blended with Worley cell structure. Larger
    // horizontal cells make distant clouds read as puffy masses rather than
    // a flat haze sheet.
    float baseShape = fbm(samplePosition) * anvil;
    float cellStructure = worleyNoise(samplePosition * 2.0 + vec3(gameTime * 0.002, 0, 0));
    float shape = mix(baseShape, cellStructure, 0.3);

    float threshold = 0.65 - coverage * 0.35 - weatherStrength * 0.1;
    // Stronger core/edge contrast is what makes clouds look volumetric:
    // wide empty gaps, compact thick cores.
    float density = (shape - threshold) * 3.4;
    density = clamp(density, 0.0, 1.0);
    density = pow(density, 1.2);

    float detailNoise = valueNoise3(samplePosition * 5.0 + vec3(0, gameTime * 0.003, 0));
    density = density * (0.85 + 0.15 * detailNoise);

    // Erosion: high-frequency Worley carves the cloud boundary where the
    // base density is thin, turning smooth blobs into wispy edges.
    if (uDetail > 0.5) {
        float erode = worleyNoise(samplePosition * 4.0
            + vec3(windOffset.x, gameTime * 0.004, windOffset.y) * 0.05);
        density -= erode * 0.3 * (1.0 - density);
        if (uDetail > 1.5) {
            float fine = valueNoise3(samplePosition * 9.0
                + vec3(0.0, gameTime * 0.006, 0.0));
            density -= fine * 0.10 * (1.0 - density);
        }
    }

    return clamp(density * bottom * top * heightGradient, 0.0, 1.0);
}

// Phase functions ---------------------------------------------------
float hgPhase(float cosTheta, float g) {
    float denom = max(pow(1.0 + g * g - 2.0 * g * cosTheta, 1.5), 0.0001);
    return (1.0 - g * g) / (12.566 * denom);
}

// Light transmittance: secondary march toward the sun --------------
float lightTransmittance(vec3 pos) {
    if (uSunSamples < 0.5) {
        return 1.0;
    }
    float sunStep = 36.0 / max(uSunSamples, 1.0);
    float opticalDepth = 0.0;
    for (int j = 0; j < 8; j++) {
        if (float(j) >= uSunSamples) {
            break;
        }
        vec3 samplePos = pos + sunDirection * (float(j) + 0.5) * sunStep;
        opticalDepth += cloudDensity(samplePos) * sunStep;
        if (opticalDepth > 2.0) {
            break;  // transmittance already below ~10 %, further samples are noise
        }
    }
    return exp(-opticalDepth * 0.12);
}

void main() {
    vec2 screen = screenUv * 2.0 - 1.0;
    screen.x *= aspectRatio;
    vec3 rayDirection = normalize(cameraForward
        + cameraRight * screen.x * tanHalfFov
        + cameraUp * screen.y * tanHalfFov);

    // Skip nearly horizontal rays.
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

    float baseStep = (farDistance - nearDistance) / max(uSteps, 1.0);

    // Interleaved gradient noise jitter: banding becomes high-frequency
    // noise. The offset is STATIC per pixel - a per-frame term made the
    // grain crawl frame-to-frame; temporal averaging would need a history
    // buffer this renderer does not have.
    vec2 pixel = screenUv * vec2(512.0);
    float jitter = fract(52.9829189 * fract(dot(pixel, vec2(0.06711056, 0.00583715)))) * baseStep;
    float distanceAlongRay = nearDistance + jitter;

    float transmittance = 1.0;
    vec3 accumulated = vec3(0.0);
    float cosTheta = dot(rayDirection, sunDirection);
    float phase = hgPhase(cosTheta, 0.55);
    if (uDualLobe > 0.5) {
        // Dual-lobe Mie: strong forward scattering plus the dim backward lobe
        // that gives backlit clouds their bright drop-shadowed rim.
        phase = max(phase, hgPhase(cosTheta, -0.25) * 0.7);
    }
    float stepLength = baseStep;

    for (int stepIndex = 0; stepIndex < 32; ++stepIndex) {
        if (float(stepIndex) >= uSteps) {
            break;
        }
        vec3 position = cameraPosition + rayDirection * distanceAlongRay;
        float density = cloudDensity(position);

        if (density > 0.003) {
            float shadowTransmittance = lightTransmittance(position);

            // Powder sugar term: keeps dense cores bright while thinning the
            // edges, fighting the flat "cotton ball" look of plain Beer.
            float powder = 1.0;
            if (uPowder > 0.5) {
                powder = 1.0 - exp(-density * stepLength * 0.8);
                powder = mix(0.45, 1.0, powder);
            }

            // Ambient term: one octave of multiple scattering so thick cloud
            // bodies stay luminous instead of grey; kept bot-heavy so the
            // undersides fall off into shadow and sell the volume.
            float topBias = clamp((position.y - cloudBase) / (cloudTop - cloudBase), 0.0, 1.0);
            vec3 ambient = skyColor * daylight * (0.24 + 0.24 * topBias);

            vec3 nightCloud = vec3(0.18, 0.22, 0.30);
            vec3 dayCloud = vec3(0.95, 0.93, 0.90);
            vec3 sunsetCloud = vec3(1.0, 0.78, 0.65);
            vec3 shadowColor = mix(
                mix(nightCloud, vec3(0.35, 0.40, 0.50), daylight),
                vec3(0.20, 0.24, 0.32), weatherStrength);
            /* Twilight tint follows the actual sun elevation (the previous
               form keyed off fract(gameTime/24.0) - elapsed SECONDS - which
               pulsed orange every 24 s of play and never fired at the real
               dusk). |sunHeight| < 0.28 is the same horizon band the
               DayNightCycle sky uses for its twilight colour. */
            float twilight = 1.0 - smoothstep(0.0, 0.28, abs(sunHeight));
            vec3 litBase = mix(dayCloud, sunsetCloud, twilight);

            float silverLining = pow(max(cosTheta, 0.0), 8.0) * shadowTransmittance;
            float lightTerm = shadowTransmittance * phase * 2.8 + silverLining * 0.8;
            vec3 sampleColor = shadowColor * (0.8 + 0.4 * ambient.r)
                + ambient * 0.35
                + litBase * lightTerm * powder * 1.15;

            float extinction = density * stepLength * 0.12;
            float alpha = 1.0 - exp(-extinction);
            accumulated += sampleColor * alpha * transmittance;
            transmittance *= 1.0 - alpha;

            stepLength = baseStep;
            if (transmittance < 0.02) {
                break;
            }
        } else if (uAdaptive > 0.5) {
            stepLength = baseStep * 3.0;  // large strides through empty air
        }
        distanceAlongRay += stepLength;
        if (distanceAlongRay > farDistance) {
            break;
        }
    }

    float alpha = 1.0 - transmittance;
    if (alpha < 0.005) {
        discard;
    }

    // Smooth horizon and distance fading.
    float horizonFade = smoothstep(0.0, 0.15, abs(rayDirection.y));
    float distanceFade = 1.0 - smoothstep(drawDistance * 0.65, drawDistance, farDistance);
    alpha *= mix(0.4, 1.0, horizonFade) * max(0.5, distanceFade);

    // Blend with atmospheric scattering.
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

    # Volumetric parameters per quality tier. Every preset raymarches;
    # POTATO is the cheapest practical march. The billboard puffs are only
    # the fallback when the volume shader is unavailable (measured: the
    # puff path costs ~6.3 ms/frame CPU on the dev iGPU - ~782 immediate-
    # mode quads dominate - while the cheapest march costs 0.68 ms GPU).
    # GPU is the cinematic tier: the full feature set (32 steps, 8 sun
    # samples, dual-lobe phase, powder) behind the half-resolution guard -
    # a 0.75 scale still measured 45 ms GPU/frame on integrated Radeon
    # graphics at a cloud-heavy view angle, so the tier keeps its maximum
    # sampling but not a pathological pixel count.
    QUALITY_PARAMS = {
        "POTATO": {"steps": 4,  "sun_samples": 1, "detail": 0,
                   "powder": 0, "adaptive": 1, "dual_lobe": 0,
                   "resolution_scale": 0.5},
        "LOW":    {"steps": 8,  "sun_samples": 1, "detail": 0,
                   "powder": 0, "adaptive": 1, "dual_lobe": 0,
                   "resolution_scale": 0.5},
        "MEDIUM": {"steps": 16, "sun_samples": 4, "detail": 1,
                   "powder": 1, "adaptive": 1, "dual_lobe": 1,
                   "resolution_scale": 0.5},
        "HIGH":   {"steps": 24, "sun_samples": 6, "detail": 2,
                   "powder": 1, "adaptive": 1, "dual_lobe": 1,
                   "resolution_scale": 0.5},
        "GPU":    {"steps": 32, "sun_samples": 8, "detail": 2,
                   "powder": 1, "adaptive": 1, "dual_lobe": 1,
                   "resolution_scale": 0.5},
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
        self.volume_shader = None
        self.volume_uniforms = {}
        self._quality = "MEDIUM"
        self._params = self.QUALITY_PARAMS[self._quality]
        # Off-screen buffer for the reduced-resolution cloud pass.
        self._cloud_fbo = 0
        self._cloud_texture = 0
        self._cloud_fbo_size = (0, 0)
        self._initialize_volume_shader()

    def close(self):
        """Release the half-res cloud framebuffer before a scene reset."""
        if self._cloud_fbo:
            try:
                glDeleteFramebuffers(1, [self._cloud_fbo])
            except Exception:
                pass
        if self._cloud_texture:
            try:
                glDeleteTextures([self._cloud_texture])
            except Exception:
                pass
        self._cloud_fbo = 0
        self._cloud_texture = 0
        self._cloud_fbo_size = (0, 0)

    @property
    def shadow_offset(self):
        return self.wind_x, self.wind_z

    @property
    def quality(self):
        return self._quality

    def set_quality(self, quality):
        """Select the cloud realism tier (POTATO/LOW/MEDIUM/HIGH/GPU)."""
        quality = str(quality).upper()
        if quality not in self.QUALITY_PARAMS:
            quality = "MEDIUM"
        self._quality = quality
        self._params = self.QUALITY_PARAMS[quality]

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
        can_raymarch = (self._params is not None
                        and self.volume_shader
                        and light is not None and light.enabled)
        if can_raymarch:
            self._render_volume(player, cycle)
        else:
            self._render_puffs(player, cycle)

    def _render_volume(self, player, cycle):
        scale = self._params["resolution_scale"]
        if scale < 1.0:
            self._render_volume_scaled(player, cycle, scale)
            return
        self._render_volume_direct(player, cycle)

    def _ensure_cloud_buffer(self, width, height):
        """(Re)create the reduced-resolution cloud framebuffer on demand."""
        if self._cloud_fbo_size == (width, height):
            return
        self.close()
        self._cloud_texture = glGenTextures(1)
        glBindTexture(GL_TEXTURE_2D, self._cloud_texture)
        glTexImage2D(GL_TEXTURE_2D, 0, GL_RGBA, width, height, 0,
                     GL_RGBA, GL_UNSIGNED_BYTE, None)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)

        self._cloud_fbo = glGenFramebuffers(1)
        glBindFramebuffer(GL_FRAMEBUFFER, self._cloud_fbo)
        glFramebufferTexture2D(GL_FRAMEBUFFER, GL_COLOR_ATTACHMENT0,
                               GL_TEXTURE_2D, self._cloud_texture, 0)
        complete = glCheckFramebufferStatus(GL_FRAMEBUFFER) == GL_FRAMEBUFFER_COMPLETE
        glBindFramebuffer(GL_FRAMEBUFFER, 0)
        if not complete:
            logging.warning("cloud framebuffer incomplete; falling back to full res")
            self.close()
            self._params = dict(self._params, resolution_scale=1.0)
            return
        self._cloud_fbo_size = (width, height)

    def _render_volume_scaled(self, player, cycle, scale):
        """Raymarch the clouds into a half-res buffer, then upscale.

        The soft, high-frequency nature of clouds makes bilinear upsampling
        nearly invisible while cutting the most expensive per-pixel pass by
        the square of the resolution scale.
        """
        width = max(2, int(self.gl.WIDTH * scale))
        height = max(2, int(self.gl.HEIGHT * scale))
        self._ensure_cloud_buffer(width, height)
        if not self._cloud_fbo:
            self._render_volume_direct(player, cycle)
            return

        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_COLOR_BUFFER_BIT
                     | GL_CURRENT_BIT | GL_VIEWPORT_BIT)
        try:
            glBindFramebuffer(GL_FRAMEBUFFER, self._cloud_fbo)
            glViewport(0, 0, width, height)
            glClearColor(0.0, 0.0, 0.0, 0.0)
            glClear(GL_COLOR_BUFFER_BIT)
            self._draw_cloud_quad(player, cycle)
            glBindFramebuffer(GL_FRAMEBUFFER, 0)

            # Composite the upscaled buffer over the sky at FULL window size;
            # the buffer pass above reduced the viewport for the FBO and it
            # must be restored before drawing the fullscreen quad.
            glViewport(0, 0, self.gl.WIDTH, self.gl.HEIGHT)

            # Composite the upscaled buffer over the sky, exactly where the
            # direct pass used to draw.
            glMatrixMode(GL_PROJECTION)
            glPushMatrix()
            glLoadIdentity()
            glMatrixMode(GL_MODELVIEW)
            glPushMatrix()
            glLoadIdentity()
            glDisable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glEnable(GL_BLEND)
            glBlendFunc(GL_SRC_ALPHA, GL_ONE_MINUS_SRC_ALPHA)
            glEnable(GL_TEXTURE_2D)
            glBindTexture(GL_TEXTURE_2D, self._cloud_texture)
            glBegin(GL_QUADS)
            glTexCoord2f(0.0, 0.0); glVertex2f(-1.0, -1.0)
            glTexCoord2f(1.0, 0.0); glVertex2f(1.0, -1.0)
            glTexCoord2f(1.0, 1.0); glVertex2f(1.0, 1.0)
            glTexCoord2f(0.0, 1.0); glVertex2f(-1.0, 1.0)
            glEnd()
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
        finally:
            glPopAttrib()

    def _render_volume_direct(self, player, cycle):
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
            self._draw_cloud_quad(player, cycle)
        finally:
            glUseProgram(0)
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
            glPopAttrib()

    def _draw_cloud_quad(self, player, cycle):
        """Bind the cloud shader, upload uniforms and draw the NDC quad."""
        glUseProgram(self.volume_shader)
        self._apply_volume_uniforms(player, cycle)
        glBegin(GL_QUADS)
        glTexCoord2f(0, 0); glVertex2f(-1, -1)
        glTexCoord2f(1, 0); glVertex2f(1, -1)
        glTexCoord2f(1, 1); glVertex2f(1, 1)
        glTexCoord2f(0, 1); glVertex2f(-1, 1)
        glEnd()
        glUseProgram(0)

    def _apply_volume_uniforms(self, player, cycle):
        yaw = math.radians(player.rotation[1])
        pitch = math.radians(player.rotation[0])
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        sin_yaw = math.sin(yaw)
        cos_yaw = math.cos(yaw)
        forward = (sin_yaw * cos_pitch, -sin_pitch, -cos_yaw * cos_pitch)
        right = (cos_yaw, 0.0, sin_yaw)
        up = (sin_yaw * sin_pitch, cos_pitch, -cos_yaw * sin_pitch)

        params = self._params
        self._uniform3("cameraPosition", player.position)
        self._uniform3("cameraForward", forward)
        self._uniform3("cameraRight", right)
        self._uniform3("cameraUp", up)
        self._uniform3("sunDirection", cycle.light_direction)
        # True sun elevation BEFORE the night flip light_direction gets: the
        # twilight tint must key off the sun, not the moon vector.
        self._uniform1("sunHeight", math.sin(cycle.sun_angle))
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
        self._uniform1("uSteps", params["steps"])
        self._uniform1("uSunSamples", params["sun_samples"])
        self._uniform1("uDetail", params["detail"])
        self._uniform1("uPowder", params["powder"])
        self._uniform1("uAdaptive", params["adaptive"])
        self._uniform1("uDualLobe", params["dual_lobe"])

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
                glTexCoord2f(0, 1); glVertex3f(cx - rx - ux, cy - ry - uy, cz - rz + uz)
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
                "sunDirection", "sunHeight", "skyColor", "horizonColor",
                "windOffset", "aspectRatio", "tanHalfFov", "coverage",
                "weatherStrength", "daylight", "gameTime", "drawDistance",
                "cloudBase", "cloudTop", "uSteps", "uSunSamples", "uDetail",
                "uPowder", "uAdaptive", "uDualLobe",
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
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MIN_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_MAG_FILTER, GL_LINEAR)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_S, GL_CLAMP_TO_EDGE)
        glTexParameteri(GL_TEXTURE_2D, GL_TEXTURE_WRAP_T, GL_CLAMP_TO_EDGE)
        return pyglet.graphics.TextureGroup(texture)
