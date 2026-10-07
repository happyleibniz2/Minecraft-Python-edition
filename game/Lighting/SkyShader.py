"""GLSL sky shader rendering a Gargantua-style black hole night sky.

The shader is **world-anchored**: every frame the Python side passes the
camera basis (forward/right/up) and the black hole's direction on the
celestial sphere, and the fragment shader reconstructs a real view ray per
pixel.  Turning the camera therefore moves the black hole across the sky
exactly like the fixed-function stars do — it is glued to the heavens, not
to the screen.

When the day/night cycle reports a dark sky (``star_brightness > 0``) the
shader activates and draws a black hole inspired by Gargantua from
*Interstellar*:

* A **thin, bright accretion disk** seen nearly edge-on.  Emission follows a
  ``r^-3/4`` temperature law (white-hot inner edge fading to deep orange) and
  a ``r^-2`` intensity falloff, with relativistic beaming brightening and
  blue-shifting the approaching side.
* **Gravitational wrap-around**: light from the far side of the disk bends
  over (and under) the event horizon, so the disk is visibly mirrored into
  arcs hugging the photon sphere above and below the shadow — the signature
  Gargantua silhouette, including the bright line of the near-side disk
  crossing in front of the lower half of the sphere.
* A **dark event horizon**: rays whose impact parameter is sub-critical are
  absorbed; the shadow boundary is ringed by a thin photon-sphere glow.
* Background stars are lensed with the exact point-mass (Einstein) map
  applied in the tangent plane around the hole, so the far field stays
  undistorted and the caustic at the shadow edge forms a true Einstein ring.
  The star field itself is sampled from the ray's *direction* via an
  octahedral mapping, so it rotates with the sky.

Quality levels (``settings.BLACKHOLE_QUALITY``):
* ``OFF``   — the pass is skipped entirely; the vanilla fixed-function stars
  show through.
* ``LOW``   — straight stars (no lens mapping) and only the bright top wrap.
* ``HIGH``  — full lensing, both wrap arcs and the photon ring.

The module degrades gracefully: compilation failures or an OpenGL context
that does not support shaders fall back to the fixed-function rendering.
"""

import math
import logging

from OpenGL.GL import *
from OpenGL.GL.shaders import compileProgram, compileShader

from game.world.DayNightCycle import DayNightCycle


BLACK_HOLE_VERTEX_SHADER = """
#version 120

void main() {
    gl_Position = gl_Vertex;
    gl_TexCoord[0] = gl_Vertex;
}
"""

BLACK_HOLE_FRAGMENT_SHADER = """
#version 120

uniform float gameTime;
uniform float starBrightness;
uniform float aspectRatio;
uniform float tanHalfFov;
uniform float weatherStrength;
uniform float uQuality;          /* 1 = LOW, 2 = HIGH */
uniform vec3 cameraForward;
uniform vec3 cameraRight;
uniform vec3 cameraUp;
uniform vec3 blackHoleDirection; /* unit vector toward the hole */
uniform float shadowSin;         /* sin of the shadow's angular radius */

/* 2D hash / noise helpers ---------------------------------------------- */
float hash21(vec2 p) {
    p = fract(p * vec2(123.34, 456.21));
    p += dot(p, p + 45.32);
    return fract(p.x * p.y);
}

float hash11(float p) {
    return fract(sin(p * 127.1) * 43758.5453);
}

/* Background star field ------------------------------------------------- */
vec3 starField(vec2 uv) {
    uv = mod(uv, 100.0);
    vec2 cell = floor(uv);
    vec2 f = fract(uv);
    float stars = 0.0;
    for (int x = -1; x <= 1; x++) {
        for (int y = -1; y <= 1; y++) {
            vec2 neighbor = vec2(float(x), float(y));
            vec2 p = cell + neighbor;
            float id = hash21(p);
            vec2 pos = p + vec2(hash21(p + 1.0), hash21(p + 2.0));
            vec2 diff = neighbor + pos - f;
            float dist = length(diff);
            float strength = smoothstep(0.7, 0.0, dist);
            stars += id * id * strength;
        }
    }
    return vec3(stars);
}

/* Octahedral mapping: direction -> 2D sky coordinates.  Sampling the star
   field from the *direction* (instead of raw screen coordinates) glues the
   stars to the celestial sphere so they rotate with the camera. */
vec2 skyUv(vec3 d) {
    vec3 a = abs(d);
    vec2 p = d.xy / (a.x + a.y + a.z);
    if (d.z < 0.0) {
        p = (1.0 - abs(p.yx)) * sign(p.xy + 0.000001);
    }
    return p;
}

/* Gargantua accretion disk ------------------------------------------------
   All disk maths happen in shadow-radius units around the hole: rho == 1 is
   the photon-capture boundary.  The disk plane is fixed in world space via
   ``diskNormal``; the near side of the disk passes in front of the shadow,
   and light from the far side wraps over and under the photon sphere.  */
float ringMask(float r, float rIn, float rOut) {
    return smoothstep(rIn, rIn + 0.045, r)
         * (1.0 - smoothstep(rOut * 0.72, rOut, r));
}

vec3 diskColor(float r, float azim, float fade, float rIn) {
    /* Temperature law T ~ r^-3/4 normalised so T = 1 at the inner edge. */
    float t = pow(rIn / max(r, 0.0001), 0.75);
    /* Intensity law I ~ r^-2. */
    float glow = pow(rIn / max(r, 0.0001), 2.0);
    /* Blackbody-ish ramp: white-hot inner edge -> orange -> deep red. */
    vec3 hot = vec3(1.30, 1.14, 0.92);
    vec3 mid = vec3(1.18, 0.62, 0.24);
    vec3 cold = vec3(0.55, 0.16, 0.03);
    vec3 colour = mix(cold, mix(mid, hot, smoothstep(0.55, 0.95, t)),
                      smoothstep(0.30, 0.70, t));
    /* Doppler beaming: approaching side brighter and bluer. */
    float doppler = clamp(-cos(azim), -1.0, 1.0);
    float beam = 1.0 + 0.55 * doppler;
    colour *= beam;
    colour.b *= 1.0 + 0.18 * max(doppler, 0.0);
    /* Faint ring striations, slowly shimmering. */
    float band = hash11(floor(r * 7.0) * 3.7 + floor(gameTime * 2.0) * 0.13);
    glow *= 0.85 + 0.30 * band;
    return colour * glow * fade;
}

void main() {
    vec2 ndc = gl_TexCoord[0].xy;

    /* Reconstruct the world-space view ray for this pixel. */
    vec3 ray = normalize(cameraForward
        + cameraRight * ndc.x * tanHalfFov * aspectRatio
        + cameraUp * ndc.y * tanHalfFov);

    /* Disk frame: the Interstellar look reads as a nearly edge-on band
       crossing the hole horizontally with wrap-arcs above and below it.
       Build the sky-plane frame from the camera's up vector rather than a
       fixed world normal, so the band stays visually horizontal and the
       near-side streak always crosses the shadow's front. */
    vec3 zAxis = blackHoleDirection;
    vec3 rawUp = cameraUp - zAxis * dot(cameraUp, zAxis);
    float vLen = length(rawUp);
    if (vLen < 0.0001) {
        rawUp = vec3(0.0, 1.0, 0.0)
              - zAxis * dot(vec3(0.0, 1.0, 0.0), zAxis);
        vLen = max(length(rawUp), 0.0001);
    }
    vec3 vUp = rawUp / vLen;
    vec3 uRight = cross(vUp, zAxis);

    /* Fixed small inclination (~8 degrees), matching the movie's tilt. */
    float camSide = 0.14;

    float a1 = dot(ray, uRight);
    float a2 = dot(ray, vUp);
    vec2 t = vec2(a1, a2);
    float rho = length(t) / shadowSin;
    /* side > 0 is the half of the sky containing the disk's near side. */
    float side = a2 * camSide;

    /* The tangent-plane projection is mirror-symmetric about the hole: a
       ray looking AT the hole and its antipodal ray share the same plane
       components, which would draw a second, mirrored black hole. Gate
       every hole-local effect to the hemisphere that actually faces it. */
    float forwardness = dot(ray, zAxis);

    /* --- background stars -------------------------------------------
       Exact point-lens (Einstein) map in the tangent plane: the far field
       stays undistorted and the caustic at rho = 1 forms the Einstein ring.
       Inside the capture radius no star light reaches the camera. */
    vec3 stars = vec3(0.0);
    if (forwardness <= 0.0) {
        // behind the hole: an ordinary, unlensed sky
        stars = starField(skyUv(ray) * 90.0);
    } else if (rho > 1.0) {
        vec3 sourceDir = ray;
        if (uQuality > 1.5) {
            float r2 = max(dot(t, t), 0.000001);
            vec2 src = t * (1.0 - (shadowSin * shadowSin) / r2);
            sourceDir = normalize(ray - uRight * a1 - vUp * a2
                                  + uRight * src.x + vUp * src.y);
        }
        stars = starField(skyUv(sourceDir) * 90.0);
    }
    stars = clamp(stars, 0.0, 1.0);

    vec3 night_base = vec3(0.34, 0.42, 0.72) * starBrightness;
    vec3 colour = night_base * 0.3 + stars * starBrightness;

    float visible = smoothstep(0.02, 0.35, starBrightness);

    float R_IN = 1.15;
    float R_OUT = 3.20;
    float sinI = clamp(abs(camSide), 0.05, 1.0);
    float LAMBDA_OVER = 0.42;
    float LAMBDA_UNDER = 0.26;

    vec2 p = t / shadowSin;

    /* --- direct disk image -------------------------------------------
       Lift the ray back onto the disk plane; the projected ellipse becomes
       a circle so ring membership is a plain radial test.  Inside the
       shadow only the near side (side >= 0) is visible in front of the
       sphere; the far side there is absorbed. */
    vec2 q = vec2(p.x, p.y / sinI);
    float r_d = length(q);
    float azim_d = atan(q.y, q.x);
    float ring = ringMask(r_d, R_IN, R_OUT);
    float nearMask = step(0.0, side);
    float directMask = ring * max(step(1.0, rho), nearMask);
    vec3 disk = diskColor(r_d, azim_d, directMask, R_IN);

    /* --- far side wrapped over the shadow ---------------------------- */
    float r_over = R_IN + (rho - 1.0) / LAMBDA_OVER;
    float overMask = ringMask(r_over, R_IN, R_OUT)
                   * step(1.0, rho) * step(0.0, side);
    disk += diskColor(r_over, atan(-a2, a1), overMask * 0.95, R_IN);

    /* --- far side wrapped under the shadow (HIGH quality only) -------- */
    if (uQuality > 1.5) {
        float r_under = R_IN + (rho - 1.0) / LAMBDA_UNDER;
        float underMask = ringMask(r_under, R_IN, R_OUT)
                        * step(1.0, rho) * step(side, 0.0);
        disk += diskColor(r_under, atan(a2, a1), underMask * 0.55, R_IN);
    }

    /* Saturate so the overlapping images do not blow out near the
       shadow edge, where the direct sheet and both wrapped arcs meet. */
    disk = vec3(1.0) - exp(-disk * 1.25);

    /* --- photon ring: caustic at the capture boundary ----------------- */
    float photonD = (rho - 1.0) / 0.04;
    float photon = exp(-photonD * photonD);
    disk += vec3(1.15, 0.75, 0.45) * photon * 0.5;

    /* the disk and the shadow exist only on the hemisphere facing the hole */
    float onSky = step(0.0, forwardness);
    disk *= onSky;

    colour += disk * visible;

    /* --- event horizon: absorbed region, unless the near-side disk
           passes in front of the sphere -------------------------------- */
    float inShadow = (1.0 - smoothstep(0.985, 1.0, rho)) * onSky;
    colour *= 1.0 - inShadow * (1.0 - directMask);

    /* Weather reduces brightness and adds a blue-grey veil. */
    colour *= (1.0 - weatherStrength * 0.4);
    colour += vec3(0.0, 0.0, 0.02) * weatherStrength;

    gl_FragColor = vec4(colour, 1.0);
}
"""


class SkyShader:
    """Renders the black-hole night sky using a GLSL 1.20 shader.

    The shader draws a fullscreen quad behind the world whenever the sky is
    dark enough for stars to be visible (``DayNightCycle.star_brightness``).
    During daylight the existing fixed-function rendering in
    ``Scene.drawCelestialSky`` is used instead, so the sun and moon remain
    drawn as textures.
    """

    QUALITIES = ("OFF", "LOW", "HIGH")
    # the disk frame is built from the camera's up vector in the shader, so
    # the accretion band stays visually horizontal like the Interstellar shot
    SHADOW_ANGULAR_RADIUS = 14.0

    def __init__(self, light):
        self._light = light
        self._day_night = None
        self.shader = 0
        self._uniforms = {}
        self._enabled = False
        self._initialized = False
        self._quality = "HIGH"

    @property
    def day_night(self):
        return self._day_night

    @day_night.setter
    def day_night(self, cycle):
        """Bind the day/night cycle so the shader can read star brightness."""
        if cycle is None or isinstance(cycle, DayNightCycle):
            self._day_night = cycle

    @property
    def quality(self):
        return self._quality

    def set_quality(self, quality):
        """Set the black-hole quality: OFF, LOW or HIGH."""
        quality = str(quality).upper()
        self._quality = quality if quality in self.QUALITIES else "HIGH"

    def initialize(self):
        """Compile the sky shader.  Safe to call multiple times."""
        if self._initialized:
            return self.shader != 0
        if self._light is None or not self._light.enabled:
            return False
        try:
            self.shader = compileProgram(
                compileShader(BLACK_HOLE_VERTEX_SHADER, GL_VERTEX_SHADER),
                compileShader(BLACK_HOLE_FRAGMENT_SHADER, GL_FRAGMENT_SHADER),
            )
            self._uniforms = {
                name: glGetUniformLocation(self.shader, name)
                for name in (
                    "gameTime", "starBrightness", "aspectRatio",
                    "tanHalfFov", "weatherStrength", "uQuality",
                    "cameraForward", "cameraRight", "cameraUp",
                    "blackHoleDirection", "shadowSin",
                )
            }
            self._enabled = True
        except Exception as error:
            logging.warning("Sky black-hole shader unavailable: %s", error)
            self.shader = 0
            self._enabled = False
        self._initialized = True
        return self.shader != 0

    def close(self):
        """Release GPU resources."""
        if self.shader:
            try:
                glDeleteProgram(self.shader)
            except Exception:
                pass
            self.shader = 0
        self._initialized = False
        self._enabled = False

    @staticmethod
    def _bh_direction(sun_angle):
        """Direction of the black hole on the celestial sphere.

        The hole hangs at the anti-solar point of the sun's orbit, so it
        sweeps from the horizon up through the zenith and back down during
        the night, exactly opposite the sun's path.
        """
        return (0.0, -math.sin(sun_angle), math.cos(sun_angle))

    @staticmethod
    def _camera_basis(rotation):
        """Forward/right/up camera vectors from (pitch, yaw) in degrees."""
        yaw = math.radians(rotation[1])
        pitch = math.radians(rotation[0])
        cos_pitch = math.cos(pitch)
        sin_pitch = math.sin(pitch)
        sin_yaw = math.sin(yaw)
        cos_yaw = math.cos(yaw)
        forward = (sin_yaw * cos_pitch, -sin_pitch, -cos_yaw * cos_pitch)
        right = (cos_yaw, 0.0, sin_yaw)
        up = (sin_yaw * sin_pitch, cos_pitch, -cos_yaw * sin_pitch)
        return forward, right, up

    def render(self, scene, dt=0.0):
        """Draw the black-hole sky if stars are visible.

        Returns ``True`` if the shader handled rendering, ``False`` if the
        caller should fall back to the classic star points.
        """
        if self._quality == "OFF":
            return False
        if not self._enabled or not self.shader:
            return False
        if self._day_night is None:
            return False

        star_brightness = self._day_night.star_brightness
        if star_brightness <= 0.01:
            return False

        # glPushAttrib does NOT save the current program or the matrix
        # stacks, so both are pushed before the try and restored in finally.
        glPushAttrib(GL_ENABLE_BIT | GL_DEPTH_BUFFER_BIT | GL_CURRENT_BIT)
        glMatrixMode(GL_PROJECTION)
        glPushMatrix()
        glLoadIdentity()
        glMatrixMode(GL_MODELVIEW)
        glPushMatrix()
        glLoadIdentity()
        try:
            forward, right, up = self._camera_basis(scene.player.rotation)

            glUseProgram(self.shader)
            glUniform1f(self._uniforms["gameTime"], self._light.elapsed)
            glUniform1f(self._uniforms["starBrightness"], star_brightness)
            glUniform1f(self._uniforms["aspectRatio"],
                        scene.WIDTH / scene.HEIGHT)
            glUniform1f(self._uniforms["tanHalfFov"],
                        math.tan(math.radians(scene.fov * 0.5)))
            glUniform1f(self._uniforms["weatherStrength"],
                        self._day_night.weather_strength)
            glUniform1f(self._uniforms["uQuality"],
                        2.0 if self._quality == "HIGH" else 1.0)
            glUniform3f(self._uniforms["cameraForward"], *forward)
            glUniform3f(self._uniforms["cameraRight"], *right)
            glUniform3f(self._uniforms["cameraUp"], *up)
            glUniform3f(self._uniforms["blackHoleDirection"],
                        *self._bh_direction(self._day_night.sun_angle))
            glUniform1f(self._uniforms["shadowSin"],
                        math.sin(math.radians(self.SHADOW_ANGULAR_RADIUS)))

            glDisable(GL_DEPTH_TEST)
            glDepthMask(GL_FALSE)
            glDisable(GL_FOG)
            glDisable(GL_BLEND)
            glDisable(GL_TEXTURE_2D)

            # Identity projection: NDC coords map directly to the screen.
            # The vertex shader reads gl_Vertex, so immediate mode supplies
            # the position directly in the compatibility profile.
            glBegin(GL_TRIANGLE_STRIP)
            glVertex2f(-1.0, -1.0)
            glVertex2f(1.0, -1.0)
            glVertex2f(-1.0, 1.0)
            glVertex2f(1.0, 1.0)
            glEnd()
        finally:
            glUseProgram(0)
            glMatrixMode(GL_PROJECTION)
            glPopMatrix()
            glMatrixMode(GL_MODELVIEW)
            glPopMatrix()
            glDepthMask(GL_TRUE)
            glPopAttrib()

        return True
